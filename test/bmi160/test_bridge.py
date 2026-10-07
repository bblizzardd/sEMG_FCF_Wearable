"""Serial bridge tests with fake USB ports; no device required."""
import functools
import http.client
import importlib.util
import json
from pathlib import Path
import queue
import threading
import time
import unittest

spec = importlib.util.spec_from_file_location("bridge", Path(__file__).resolve().parents[2] / "live_bmi_visualizer.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def info(device="COM10", vid=0x1A86, serial_number="ESP32-1"):
    return {"device": device, "description": "CH343", "vid": vid, "pid": 0x55D3, "serial_number": serial_number}


def wait_for(predicate, timeout=4):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for bridge")


class FakeSerial:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False
        self.opened = False
        self.chunks = queue.Queue()
        self.writes = []

    def open(self):
        assert self.dtr is False and self.rts is False
        assert self.kwargs["baudrate"] == 460800
        self.opened = True

    def close(self):
        self.closed = True

    @property
    def in_waiting(self):
        return 4096

    def read(self, size):
        try:
            value = self.chunks.get(timeout=0.02)
        except queue.Empty:
            return b""
        if isinstance(value, Exception):
            raise value
        return value

    def write(self, value):
        self.writes.append(value)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.ports = [type("Port", (), info())()]
        self.instances = []

        def factory(**kwargs):
            instance = FakeSerial(**kwargs)
            self.instances.append(instance)
            return instance

        self.service = bridge.SerialBridge(port_provider=lambda: self.ports, serial_factory=factory)
        self.service.start()
        wait_for(lambda: self.service.snapshot()["connected"])

    def tearDown(self):
        self.service.stop()
        self.assertFalse(self.service.thread.is_alive())

    def test_fragmented_csv_and_commands(self):
        client = self.service.subscribe()
        self.assertEqual(client.get()[0], "state")
        port = self.instances[0]
        port.chunks.put(b"1,0,100")
        port.chunks.put(b"0000\r\n# SPS=100\n")
        kind, lines = client.get(timeout=2)
        self.assertEqual(kind, "lines")
        self.assertEqual(lines, ["1,0,1000000", "# SPS=100"])
        self.service.command("k")
        wait_for(lambda: b"k" in port.writes)
        self.assertEqual(port.writes[0], b"s")
        with self.assertRaises(ValueError):
            self.service.command("erase")

    def test_disconnect_disables_auto_and_releases_port(self):
        self.service.configure(enabled=False)
        wait_for(lambda: self.instances[0].closed)
        self.assertFalse(self.service.snapshot()["connected"])
        self.assertFalse(self.service.snapshot()["automatic"])
        with self.assertRaises(ValueError):
            self.service.command("s")
        self.service.configure(requested="COM10")
        wait_for(lambda: len(self.instances) == 2 and self.service.snapshot()["connected"])
        self.assertEqual(self.service.snapshot()["device"], "COM10")

    def test_unplug_and_reconnect(self):
        self.instances[0].chunks.put(OSError("USB removed"))
        wait_for(lambda: not self.service.snapshot()["connected"])
        self.assertTrue(self.instances[0].closed)
        wait_for(lambda: len(self.instances) >= 2 and self.service.snapshot()["connected"])

    def test_oversized_line_recovers(self):
        client = self.service.subscribe()
        client.get()
        self.instances[0].chunks.put(b"x" * 5000)
        self.instances[0].chunks.put(b"trailing\nvalid\n")
        messages = [client.get(timeout=2), client.get(timeout=2)]
        self.assertEqual(messages[-1], ("lines", ["valid"]))

    def test_slow_client_is_not_silently_dropped(self):
        client = self.service.subscribe()
        for _ in range(260):
            self.service.emit("lines", ["sample"])
        self.assertEqual(client.get()[0], "overflow")
        self.assertNotIn(client, self.service.clients)

    def test_http_status_stream_and_control(self):
        server = bridge.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(bridge.Handler, directory=str(Path(__file__).resolve().parents[2] / "web")))
        server.bridge = self.service
        server.token = "test-token"
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        try:
            connection.request("GET", "/api/status")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["device"], "COM10")
            connection.request("POST", "/api/command", body=json.dumps({"command": "k"}), headers={"Content-Type": "application/json", "X-BMI-Token": server.token})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            wait_for(lambda: b"k" in self.instances[0].writes)
            connection.request("POST", "/api/disconnect", body="{}", headers={"Content-Type": "application/json", "X-BMI-Token": server.token, "Origin": "https://other.example"})
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            connection.request("GET", "/api/events")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.readline(), b"event: state\n")
            initial = json.loads(response.readline().decode()[6:])
            self.assertEqual(initial["token"], server.token)
            self.assertTrue(initial["connected"])
            response.readline()
            self.instances[0].chunks.put(b"complete frame\n")
            while response.readline() != b"event: lines\n":
                pass
            self.assertEqual(json.loads(response.readline().decode()[6:]), ["complete frame"])
            response.close()
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


class SelectionTests(unittest.TestCase):
    def test_selection_and_ambiguity(self):
        first = info()
        bluetooth = info("COM5", vid=None)
        second = info("COM11", serial_number="ESP32-2")
        self.assertEqual(bridge.choose_port([first, bluetooth]), first)
        self.assertIsNone(bridge.choose_port([first, second]))
        self.assertEqual(bridge.choose_port([first, second], remembered=bridge.port_identity(second)), second)
        self.assertIsNone(bridge.choose_port([first, info("COM11")], remembered=bridge.port_identity(first)))
        self.assertIsNone(bridge.choose_port([second], remembered=bridge.port_identity(first)))
        self.assertEqual(bridge.choose_port([first, second], requested="COM11"), second)
        self.assertIsNone(bridge.choose_port([first], requested="COM99"))
        self.assertIsNone(bridge.choose_port([bluetooth]))


if __name__ == "__main__":
    unittest.main()
