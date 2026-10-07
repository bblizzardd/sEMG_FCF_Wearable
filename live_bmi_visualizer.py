"""BMI160 dashboard with a local USB Serial -> HTTP/SSE bridge."""
import argparse
import functools
import json
import queue
import secrets
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import webbrowser

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None

USB_VENDORS = {0x1A86, 0x10C4, 0x0403, 0x303A}


def port_identity(port):
    return (port.get("vid"), port.get("pid"), port.get("serial_number"))


def choose_port(ports, requested=None, remembered=None):
    if requested:
        return next((p for p in ports if p["device"] == requested), None)
    candidates = [p for p in ports if p.get("vid") in USB_VENDORS]
    if remembered:
        candidates = [p for p in candidates if port_identity(p) == remembered]
    return candidates[0] if len(candidates) == 1 else None


class SerialBridge:
    def __init__(self, requested=None, port_provider=None, serial_factory=None):
        self.port_provider = port_provider or list_ports.comports
        self.serial_factory = serial_factory or serial.Serial
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.clients = set()
        self.commands = queue.Queue(maxsize=16)
        self.requested = requested
        self.enabled = True
        self.generation = 0
        self.remembered = None
        self.state = {"connected": False, "device": None, "ports": [], "error": "Đang tìm cổng USB-UART…", "automatic": True}
        self.thread = threading.Thread(target=self.run, daemon=True, name="bmi160-serial")

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def emit(self, kind, data):
        with self.lock:
            for client in tuple(self.clients):
                try:
                    client.put_nowait((kind, data))
                except queue.Full:
                    # Close this stream explicitly; do not silently lose recording data.
                    self.clients.discard(client)
                    while not client.empty():
                        client.get_nowait()
                    client.put_nowait(("overflow", {"error": "Trình duyệt nhận chậm: luồng bị gián đoạn. CSV đã ghi sẽ được tách."}))

    def update(self, **changes):
        with self.lock:
            self.state.update(changes)
            self.emit("state", dict(self.state))

    def subscribe(self):
        client = queue.Queue(maxsize=256)
        with self.lock:
            self.clients.add(client)
            client.put_nowait(("state", dict(self.state)))
        return client

    def configure(self, requested=None, enabled=True):
        with self.lock:
            if requested and requested not in {p["device"] for p in self.state["ports"]}:
                raise ValueError("Cổng đã rút hoặc chưa được tìm thấy. Tải lại danh sách cổng.")
            self.requested, self.enabled = requested, enabled
            self.generation += 1
            while not self.commands.empty():
                self.commands.get_nowait()
            self.update(automatic=enabled)

    def command(self, command):
        if command not in {"s", "?", "k", "r"}:
            raise ValueError("Lệnh không hợp lệ")
        with self.lock:
            if not self.state["connected"]:
                raise ValueError("Chưa kết nối cảm biến")
            try:
                self.commands.put_nowait(command.encode("ascii"))
            except queue.Full:
                raise ValueError("Hàng đợi lệnh đang đầy")

    def scan(self):
        return [{"device": p.device, "description": p.description, "vid": p.vid, "pid": p.pid,
                 "serial_number": p.serial_number} for p in self.port_provider()]

    def run(self):
        connection = None
        active_generation = -1
        retry_at = 0
        scan_at = 0
        ports = []
        pending = b""
        discarding = False
        try:
            while not self.stop_event.is_set():
                with self.lock:
                    generation, enabled, requested = self.generation, self.enabled, self.requested
                if generation != active_generation:
                    if connection:
                        connection.close()
                    connection = None
                    pending = b""
                    discarding = False
                    active_generation, retry_at = generation, 0
                    self.update(connected=False, device=None, error="Đang tìm cổng…" if enabled else "Đã ngắt kết nối")
                now = time.monotonic()
                if now >= scan_at:
                    try:
                        ports = self.scan()
                        self.update(ports=ports)
                    except Exception as error:
                        self.update(error="Không dò được cổng: " + str(error))
                    scan_at = now + 2
                if not enabled:
                    self.stop_event.wait(0.1)
                    continue
                if connection is None:
                    if now < retry_at:
                        self.stop_event.wait(0.1)
                        continue
                    candidate = choose_port(ports, requested, self.remembered)
                    retry_at = now + 2
                    if not candidate:
                        message = "Chưa thấy ESP32. Cắm USB hoặc chọn cổng COM trên web."
                        if len([p for p in ports if p.get("vid") in USB_VENDORS]) > 1:
                            message = "Có nhiều cổng USB-UART. Chọn cổng ESP32 trên web rồi bấm Kết nối."
                        self.update(error=message)
                        self.stop_event.wait(0.1)
                        continue
                    try:
                        connection = self.serial_factory(port=None, baudrate=460800, timeout=0.1, write_timeout=0.5)
                        connection.dtr = False
                        connection.rts = False
                        connection.port = candidate["device"]
                        connection.open()
                        self.remembered = port_identity(candidate)
                        pending = b""
                        discarding = False
                        connection.write(b"s")
                        self.update(connected=True, device=candidate["device"], error="")
                    except Exception as error:
                        if connection:
                            connection.close()
                        connection = None
                        self.update(connected=False, device=None, error="Không mở được " + candidate["device"] + ": " + str(error) + ". Đóng Serial Monitor rồi thử lại.")
                        continue
                try:
                    # Writes and reads have one owner, including during reconnects.
                    with self.lock:
                        if active_generation != self.generation:
                            continue
                        while not self.commands.empty():
                            connection.write(self.commands.get_nowait())
                    chunk = connection.read(max(1, min(connection.in_waiting, 4096)))
                    if not chunk:
                        continue
                    pending += chunk
                    lines = []
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        if not discarding and len(line) <= 4096:
                            lines.append(line.rstrip(b"\r").decode("ascii", errors="replace"))
                        else:
                            self.emit("lines", ["# Bridge: dropped oversized Serial line"])
                        discarding = False
                    if len(pending) > 4096:
                        pending = b""
                        discarding = True
                    if lines:
                        self.emit("lines", lines)
                except Exception as error:
                    connection.close()
                    connection = None
                    pending = b""
                    discarding = False
                    self.update(connected=False, device=None, error="USB Serial bị ngắt: " + str(error))
                    retry_at = time.monotonic() + 2
        finally:
            if connection:
                connection.close()

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=2)


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".mjs": "text/javascript"}

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def local_request(self):
        return self.headers.get("Host") in {f"localhost:{self.server.server_port}", f"127.0.0.1:{self.server.server_port}"}

    def json_response(self, value, code=200):
        data = json.dumps(value, ensure_ascii=False).encode("utf8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self.local_request():
            self.send_error(403)
            return
        if self.path == "/api/status":
            self.json_response({**self.server.bridge.snapshot(), "token": self.server.token})
        elif self.path == "/api/events":
            client = self.server.bridge.subscribe()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Connection", "close")
            self.end_headers()
            self.connection.settimeout(5)
            try:
                while not self.server.bridge.stop_event.is_set():
                    try:
                        kind, value = client.get(timeout=1)
                        if kind == "state":
                            value = {**value, "token": self.server.token}
                        event = f"event: {kind}\ndata: {json.dumps(value, ensure_ascii=False)}\n\n"
                    except queue.Empty:
                        event = ": heartbeat\n\n"
                        kind = "heartbeat"
                    self.wfile.write(event.encode("utf8"))
                    self.wfile.flush()
                    if kind == "overflow":
                        break
            except (OSError, TimeoutError):
                pass
            finally:
                with self.server.bridge.lock:
                    self.server.bridge.clients.discard(client)
                self.close_connection = True
        elif self.path.startswith("/api/"):
            self.send_error(404)
        else:
            super().do_GET()

    def do_POST(self):
        origin = self.headers.get("Origin")
        valid_origins = {f"http://localhost:{self.server.server_port}", f"http://127.0.0.1:{self.server.server_port}"}
        if (not self.local_request() or (origin and origin not in valid_origins)
                or self.headers.get("X-BMI-Token") != self.server.token
                or self.headers.get("Content-Type", "").split(";")[0] != "application/json"):
            self.send_error(403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024:
                raise ValueError("Yêu cầu không hợp lệ")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Yêu cầu không hợp lệ")
            if self.path == "/api/connect":
                requested = payload.get("port") or None
                if requested is not None and not isinstance(requested, str):
                    raise ValueError("Cổng không hợp lệ")
                self.server.bridge.configure(requested=requested)
            elif self.path == "/api/disconnect":
                self.server.bridge.configure(enabled=False)
            elif self.path == "/api/command":
                self.server.bridge.command(payload.get("command"))
            else:
                self.send_error(404)
                return
            self.json_response({"ok": True})
        except (ValueError, TypeError) as error:
            self.json_response({"error": str(error)}, 400)


def main():
    parser = argparse.ArgumentParser(description="BMI160 live dashboard: Python reads USB Serial, browser receives HTTP/SSE")
    parser.add_argument("--port", type=int, default=8765, help="Local HTTP port")
    parser.add_argument("--serial-port", help="Force a Serial port, e.g. COM10; default: auto-detect USB-UART")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if serial is None:
        parser.exit(1, "Install pyserial: python -m pip install pyserial\n")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    root = Path(__file__).resolve().parent / "web"
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), functools.partial(Handler, directory=str(root)))
    except OSError as error:
        parser.exit(1, f"Cannot open local server: {error}. Try --port 8766.\n")
    server.bridge = SerialBridge(requested=args.serial_port)
    server.token = secrets.token_urlsafe(32)
    server.bridge.start()
    url = f"http://localhost:{args.port}"
    print(f"BMI160 dashboard: {url}\nUSB Serial: automatic, 460800 baud. Close Serial Monitor.\nCtrl+C to stop.", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.bridge.stop()
        server.server_close()


if __name__ == "__main__":
    main()
