"""
Combined ESP32 Dual-Sensor Dashboard: ADS1292R (sEMG) + GY-BMI160 (IMU).
Cả 2 cảm biến cùng cắm trên 1 board ESP32-S3, truyền qua 1 cổng Serial @ 460800 baud.
"""
import argparse
import functools
import json
import os
import queue
import secrets
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import webbrowser

# Đảm bảo terminal Windows không bị lỗi Unicode
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None

# Hằng số
USB_VENDORS = {0x1A86, 0x10C4, 0x0403, 0x303A}
SERIAL_BAUD = 2000000
BUCKET_SIZE = 10


# ===========================================================================
# ADS sEMG State
# ===========================================================================
class AdsState:
    """Trạng thái và bộ đệm dữ liệu ADS1292R sEMG."""

    def __init__(self):
        self.lock = threading.Lock()
        self.connected = False
        self.port = ""
        self.total_received = 0
        self.total_dropped = 0
        self.clipped = 0
        self.last_seq = None
        self.last_ts_us = 0
        self.max_gap_us = 500
        self.lead_off = False
        self.measured_sps = 0.0

        # Bucket decimation
        self._bucket_n = 0
        self._b_min_raw = float("inf")
        self._b_max_raw = float("-inf")
        self._b_min_filt = float("inf")
        self._b_max_filt = float("-inf")
        self.latest_qc_raw = 0
        self.latest_qc_filt = 0

        # SPS window
        self._sps_t0 = time.perf_counter()
        self._sps_n = 0

        # UI telemetry (50 Hz)
        self.raw = 0
        self.filt = 0
        self.env = 0
        self.base = 0
        self.sensitivity = "x1.00"
        self.percent = 0
        self.status_str = "THA LONG"
        self.dsp = "DSP:ON"

        # Recording
        self.recording = False
        self.record_file = None
        self.record_count = 0

    def snapshot(self):
        with self.lock:
            h = {
                "sps": round(self.measured_sps, 1),
                "received": self.total_received,
                "dropped": self.total_dropped,
                "max_gap_us": self.max_gap_us,
                "clipping_pct": round(
                    (self.clipped / max(1, self.total_received)) * 100, 2
                ),
                "lead_off": self.lead_off,
                "recording": self.recording,
                "record_count": self.record_count,
                "healthy": (
                    self.total_dropped == 0
                    and self.measured_sps >= 1800
                    and not self.lead_off
                ),
            }
            return {
                "connected": self.connected,
                "port": self.port,
                "raw": self.raw,
                "filt": self.filt,
                "env": self.env,
                "base": self.base,
                "sens": self.sensitivity,
                "percent": self.percent,
                "status": self.status_str,
                "dsp": self.dsp,
                "health": h,
            }

    def process_dataset_line(self, parts):
        """Xử lý dòng $D,... (mẫu sEMG)."""
        if len(parts) < 7:
            return
        try:
            s_idx = int(parts[0])
            hw_us = int(parts[1])
            ch1_24 = int(parts[2])
            ch2_24 = int(parts[3])
            raw16 = int(parts[4])
            filt16 = int(parts[5])
            loff = int(parts[6])
        except (ValueError, IndexError):
            return

        with self.lock:
            if self.last_seq is not None:
                diff = s_idx - (self.last_seq + 1)
                if diff > 0:
                    self.total_dropped += diff
            self.last_seq = s_idx
            self.total_received += 1
            self._sps_n += 1

            if self.last_ts_us > 0:
                gap = hw_us - self.last_ts_us
                if gap < 0:
                    gap += 4294967296
                if gap > self.max_gap_us and self.total_received > 200:
                    self.max_gap_us = gap
            self.last_ts_us = hw_us

            if abs(raw16) >= 32700 or abs(ch2_24) >= 8388000:
                self.clipped += 1

            self.lead_off = (loff == 1)

            if self.total_received % 500 == 0:
                now = time.perf_counter()
                elapsed = now - self._sps_t0
                if elapsed >= 0.8:
                    self.measured_sps = self._sps_n / elapsed
                    self._sps_n = 0
                    self._sps_t0 = now

            if self.recording and self.record_file:
                self.record_file.write(
                    f"{s_idx},{hw_us},{ch1_24},{ch2_24},{raw16},{filt16},{loff}\n"
                )
                self.record_count += 1
                if self.record_count % 500 == 0:
                    self.record_file.flush()

            # Bucket decimation
            self._bucket_n += 1
            if raw16 < self._b_min_raw:
                self._b_min_raw = raw16
            if raw16 > self._b_max_raw:
                self._b_max_raw = raw16
            if filt16 < self._b_min_filt:
                self._b_min_filt = filt16
            if filt16 > self._b_max_filt:
                self._b_max_filt = filt16

            if self._bucket_n >= BUCKET_SIZE:
                self.latest_qc_raw = (
                    self._b_max_raw
                    if abs(self._b_max_raw) > abs(self._b_min_raw)
                    else self._b_min_raw
                )
                self.latest_qc_filt = (
                    self._b_max_filt
                    if abs(self._b_max_filt) > abs(self._b_min_filt)
                    else self._b_min_filt
                )
                self.raw = self.latest_qc_raw
                self.filt = self.latest_qc_filt
                self._bucket_n = 0
                self._b_min_raw, self._b_max_raw = float("inf"), float("-inf")
                self._b_min_filt, self._b_max_filt = float("inf"), float("-inf")

    def process_telemetry_line(self, line):
        """Xử lý dòng telemetry UI 50 Hz."""
        parts = [p.strip() for p in line.split("|")]
        with self.lock:
            raw_val = self.latest_qc_raw
            filt_val = self.latest_qc_filt
            env_val = self.env
            base_val = self.base
            sensitivity_str = self.sensitivity
            percent_val = self.percent
            status_val = self.status_str
            dsp_val = self.dsp

            for p in parts:
                if p.startswith("Raw:") and self.total_received == 0:
                    try:
                        raw_val = int(p.replace("Raw:", "").strip())
                    except Exception:
                        pass
                elif p.startswith("Filt:") and self.total_received == 0:
                    try:
                        filt_val = int(p.replace("Filt:", "").strip())
                    except Exception:
                        pass
                elif p.startswith("Env:"):
                    try:
                        env_val = int(p.replace("Env:", "").strip())
                    except Exception:
                        pass
                elif p.startswith("Base:"):
                    try:
                        base_val = int(p.replace("Base:", "").strip())
                    except Exception:
                        pass
                elif p.startswith("x") and len(p) <= 6:
                    sensitivity_str = p
                elif "%" in p:
                    try:
                        pct_idx = p.find("%")
                        num_str = p[:pct_idx].split()[-1]
                        percent_val = int(num_str)
                    except Exception:
                        pass
                elif any(k in p for k in ["THA LONG", "GONG NHE", "GONG VUA", "GONG MANH"]):
                    status_val = p
                elif "DSP:ON" in p:
                    dsp_val = "DSP:ON"
                elif "DSP:OFF" in p:
                    dsp_val = "DSP:OFF"

            self.raw = raw_val
            self.filt = filt_val
            self.env = env_val
            self.base = base_val
            self.sensitivity = sensitivity_str
            self.percent = percent_val
            self.status_str = status_val
            self.dsp = dsp_val

    def reset_qc(self):
        with self.lock:
            self.total_dropped = 0
            self.total_received = 0
            self.max_gap_us = 500
            self.clipped = 0


# ===========================================================================
# Cầu nối Serial Đơn cho ESP32 Dual-Sensor
# ===========================================================================
def port_identity(port):
    return (port.get("vid"), port.get("pid"), port.get("serial_number"))


def choose_port(ports, requested=None, remembered=None):
    if requested:
        return next((p for p in ports if p["device"] == requested), None)
    candidates = [p for p in ports if p.get("vid") in USB_VENDORS]
    if not candidates and len(ports) == 1:
        return ports[0]
    if remembered:
        matched = [p for p in (candidates or ports) if port_identity(p) == remembered]
        if matched:
            return matched[0]
    return candidates[0] if len(candidates) == 1 else None


class Esp32DualBridge:
    """Cầu nối Serial kết nối với 1 board ESP32-S3 phát cả BMI160 và ADS1292R."""

    def __init__(self, ads_state, requested=None, port_provider=None, serial_factory=None):
        self.ads_state = ads_state
        self.port_provider = port_provider or (list_ports.comports if list_ports else lambda: [])
        self.serial_factory = serial_factory or (serial.Serial if serial else None)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.clients = set()
        self.commands = queue.Queue(maxsize=16)
        self.requested = requested
        self.enabled = True
        self.generation = 0
        self.remembered = None
        self.connection = None
        self.state = {
            "connected": False,
            "device": None,
            "ports": [],
            "error": "Đang tìm cổng USB-UART ESP32…",
            "automatic": True,
        }
        self.thread = threading.Thread(target=self.run, daemon=True, name="esp32-serial")

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def emit(self, kind, data):
        with self.lock:
            for client in tuple(self.clients):
                try:
                    client.put_nowait((kind, data))
                except queue.Full:
                    self.clients.discard(client)
                    while not client.empty():
                        client.get_nowait()
                    client.put_nowait(
                        ("overflow", {"error": "Trình duyệt nhận chậm: luồng bị gián đoạn."})
                    )

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

    def command(self, cmd):
        with self.lock:
            if not self.state["connected"]:
                raise ValueError("Chưa kết nối ESP32")
            try:
                self.commands.put_nowait(cmd.encode("ascii", errors="ignore"))
            except queue.Full:
                raise ValueError("Hàng đợi lệnh đang đầy")

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=2)

    def scan(self):
        return [
            {"device": p.device, "description": p.description, "vid": p.vid,
             "pid": p.pid, "serial_number": p.serial_number}
            for p in self.port_provider()
        ]

    def run(self):
        connection = None
        active_generation = -1
        retry_at = 0
        scan_at = 0
        ports = []
        byte_buf = bytearray()
        last_ads_stat = time.perf_counter()

        try:
            while not self.stop_event.is_set():
                with self.lock:
                    generation, enabled, requested = self.generation, self.enabled, self.requested

                if generation != active_generation:
                    if connection:
                        try:
                            connection.close()
                        except Exception:
                            pass
                    connection = None
                    self.connection = None
                    byte_buf.clear()
                    active_generation, retry_at = generation, 0
                    self.update(
                        connected=False,
                        device=None,
                        error="Đang tìm cổng…" if enabled else "Đã ngắt kết nối",
                    )
                    with self.ads_state.lock:
                        self.ads_state.connected = False
                        self.ads_state.port = ""

                now = time.monotonic()
                if now >= scan_at:
                    try:
                        ports = self.scan()
                        self.update(ports=ports)
                    except Exception as err:
                        self.update(error="Không dò được cổng: " + str(err))
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
                        message = "Chưa thấy ESP32. Cắm cáp USB hoặc chọn cổng trên web."
                        if len([p for p in ports if p.get("vid") in USB_VENDORS]) > 1:
                            message = "Có nhiều cổng USB-UART. Chọn đúng cổng ESP32 trên web."
                        self.update(error=message)
                        with self.ads_state.lock:
                            self.ads_state.connected = False
                            self.ads_state.port = message
                        self.stop_event.wait(0.1)
                        continue

                    try:
                        conn = self.serial_factory(
                            port=candidate["device"],
                            baudrate=SERIAL_BAUD,
                            timeout=0.05,
                            write_timeout=0.5,
                        )
                        conn.dtr = False
                        conn.rts = False
                        connection = conn
                        self.connection = conn
                        self.remembered = port_identity(candidate)
                        byte_buf.clear()
                        conn.write(b"s")
                        self.update(connected=True, device=candidate["device"], error="")
                        with self.ads_state.lock:
                            self.ads_state.connected = True
                            self.ads_state.port = candidate["device"]
                        print(f"[ESP32] Kết nối thành công: {candidate['device']} @ {SERIAL_BAUD}")
                    except Exception as exc:
                        if connection:
                            try:
                                connection.close()
                            except Exception:
                                pass
                        connection = None
                        self.connection = None
                        self.update(
                            connected=False,
                            device=None,
                            error=f"Không mở được {candidate['device']}: {exc}. Đóng Serial Monitor.",
                        )
                        with self.ads_state.lock:
                            self.ads_state.connected = False
                            self.ads_state.port = f"Lỗi: {exc}"
                        continue

                # Đọc dữ liệu từ Serial và gửi các lệnh đang chờ
                try:
                    with self.lock:
                        if active_generation != self.generation:
                            continue
                        while not self.commands.empty():
                            cmd = self.commands.get_nowait()
                            connection.write(cmd)

                    waiting = connection.in_waiting
                    chunk = connection.read(max(waiting, 1024))
                    if not chunk:
                        time.sleep(0.002)
                        continue

                    byte_buf.extend(chunk)
                    bmi_lines = []

                    while True:
                        nl = byte_buf.find(b"\n")
                        if nl < 0:
                            break
                        raw_line = byte_buf[:nl]
                        del byte_buf[:nl + 1]
                        if not raw_line:
                            continue
                        line = raw_line.rstrip(b"\r").decode("utf-8", errors="ignore").strip()
                        if not line:
                            continue

                        # 1. ADS1292R dataset: $D,...
                        if line.startswith("$D,"):
                            with self.ads_state.lock:
                                _is_first = (self.ads_state.total_received == 0)
                            if _is_first:
                                print(f"[sEMG] Nhận mẫu đầu tiên: {line[:60]}")
                            try:
                                self.ads_state.process_dataset_line(line[3:].split(","))
                            except Exception as _e:
                                print(f"[sEMG] Lỗi parse $D: {_e} | line: {line[:60]}")
                            continue

                        # 2. ADS1292R telemetry: Raw:... | Env:...
                        if "Raw:" in line and "Env:" in line:
                            now_t = time.perf_counter()
                            if now_t - last_ads_stat > 3.0:
                                last_ads_stat = now_t
                                with self.ads_state.lock:
                                    sps = self.ads_state.measured_sps
                                    dropped = self.ads_state.total_dropped
                                print(f"[sEMG] {line[:80]} | SPS:{sps:.0f} | Drop:{dropped}")
                            try:
                                self.ads_state.process_telemetry_line(line)
                            except Exception:
                                pass
                            continue

                        # 3. BMI160 sample hoặc status log (# ...)
                        if line.startswith("#") or line.startswith("session,") or ("," in line and line[0].isdigit()):
                            bmi_lines.append(line)

                    if len(byte_buf) > 8192:
                        byte_buf.clear()

                    if bmi_lines:
                        self.emit("lines", bmi_lines)

                except Exception as error:
                    print(f"[ESP32] Lỗi Serial: {error}")
                    if connection:
                        try:
                            connection.close()
                        except Exception:
                            pass
                    connection = None
                    self.connection = None
                    byte_buf.clear()
                    self.update(
                        connected=False,
                        device=None,
                        error="USB Serial bị ngắt: " + str(error),
                    )
                    with self.ads_state.lock:
                        self.ads_state.connected = False
                        self.ads_state.port = ""
                    retry_at = time.monotonic() + 2
        finally:
            if connection:
                try:
                    connection.close()
                except Exception:
                    pass


# ===========================================================================
# HTTP Handler
# ===========================================================================
class CombinedHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".mjs": "text/javascript"}

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def local_request(self):
        return self.headers.get("Host") in {
            f"localhost:{self.server.server_port}",
            f"127.0.0.1:{self.server.server_port}",
        }

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

        # BMI / ESP32 status
        if self.path == "/api/status":
            self.json_response({**self.server.bridge.snapshot(), "token": self.server.token})
            return

        # BMI SSE stream
        if self.path == "/api/events":
            client = self.server.bridge.subscribe()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Connection", "close")
            self.end_headers()
            self.connection.settimeout(5)
            try:
                while not self.server.stop_event.is_set():
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
            return

        # ADS endpoints
        if self.path == "/api/ads/status":
            self.json_response(self.server.ads_state.snapshot())
            return

        if self.path == "/api/ads/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Connection", "close")
            self.end_headers()
            self.connection.settimeout(5)
            try:
                while not self.server.stop_event.is_set():
                    snap = self.server.ads_state.snapshot()
                    event = f"event: ads\ndata: {json.dumps(snap, ensure_ascii=False)}\n\n"
                    self.wfile.write(event.encode("utf8"))
                    self.wfile.flush()
                    time.sleep(0.04)
            except (OSError, TimeoutError, BrokenPipeError):
                pass
            self.close_connection = True
            return

        if self.path == "/api/ads/reset":
            self.server.ads_state.reset_qc()
            self.json_response({"ok": True})
            return

        if self.path.startswith("/api/"):
            self.send_error(404)
            return

        # Static files (./web)
        super().do_GET()

    def do_POST(self):
        origin = self.headers.get("Origin")
        valid_origins = {
            f"http://localhost:{self.server.server_port}",
            f"http://127.0.0.1:{self.server.server_port}",
        }
        if (
            not self.local_request()
            or (origin and origin not in valid_origins)
            or self.headers.get("X-BMI-Token") != self.server.token
            or self.headers.get("Content-Type", "").split(";")[0] != "application/json"
        ):
            self.send_error(403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024:
                raise ValueError("Yêu cầu không hợp lệ")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Yêu cầu không hợp lệ")

            # Kết nối / Ngắt kết nối ESP32
            if self.path == "/api/connect":
                requested = payload.get("port") or None
                if requested is not None and not isinstance(requested, str):
                    raise ValueError("Cổng không hợp lệ")
                self.server.bridge.configure(requested=requested, enabled=True)
            elif self.path == "/api/disconnect":
                self.server.bridge.configure(enabled=False)
            elif self.path == "/api/command":
                self.server.bridge.command(payload.get("command", ""))

            # ADS commands
            elif self.path == "/api/ads/command":
                key = payload.get("command", "")
                self.server.bridge.command(key)

            # ADS recording start
            elif self.path == "/api/ads/record/start":
                ads = self.server.ads_state
                os.makedirs("data", exist_ok=True)
                fn = os.path.join("data", f"sEMG_2000SPS_{time.strftime('%Y%m%d_%H%M%S')}.csv")
                with ads.lock:
                    ads.record_file = open(fn, "w", encoding="utf-8")
                    ads.record_file.write(
                        "sample_idx,timestamp_us,ch1_raw24,ch2_raw24,ch2_raw16,ch2_filtered16,lead_off\n"
                    )
                    ads.recording = True
                    ads.record_count = 0
                    ads.total_dropped = 0
                    ads.max_gap_us = 500
                self.json_response({"ok": True, "filename": fn})
                return

            # ADS recording stop
            elif self.path == "/api/ads/record/stop":
                ads = self.server.ads_state
                with ads.lock:
                    ads.recording = False
                    fn = "N/A"
                    cnt = ads.record_count
                    if ads.record_file:
                        fn = ads.record_file.name
                        ads.record_file.close()
                        ads.record_file = None
                self.json_response({"ok": True, "filename": fn, "samples": cnt})
                return

            else:
                self.send_error(404)
                return

            self.json_response({"ok": True})
        except (ValueError, TypeError) as error:
            self.json_response({"error": str(error)}, 400)

    def log_message(self, fmt, *args):
        pass


# ===========================================================================
# main()
# ===========================================================================
def main():
    parser = argparse.ArgumentParser(description="Combined ESP32 Dual-Sensor Dashboard (ADS1292R + BMI160)")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port (default: 8765)")
    parser.add_argument("--serial-port", default=None, help="Cổng ESP32 (vd COM13). Mặc định: tự tìm.")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    if serial is None:
        parser.exit(1, "Cài pyserial: python -m pip install pyserial\n")
    if not 1 <= args.port <= 65535:
        parser.error("--port phải từ 1 đến 65535")

    root = Path(__file__).resolve().parent / "web"
    if not root.is_dir():
        parser.exit(1, f"Không tìm thấy thư mục web: {root}\n")

    ads_state = AdsState()
    bridge = Esp32DualBridge(ads_state, requested=args.serial_port)
    stop_event = threading.Event()

    try:
        server = ThreadingHTTPServer(
            ("127.0.0.1", args.port),
            functools.partial(CombinedHandler, directory=str(root)),
        )
    except OSError as error:
        parser.exit(1, f"Không thể mở server: {error}. Thử --port 8766.\n")

    server.bridge = bridge
    server.ads_state = ads_state
    server.stop_event = stop_event
    server.token = secrets.token_urlsafe(32)

    bridge.start()

    url = f"http://localhost:{args.port}"
    print(
        f"\n{'='*60}\n"
        f"  Combined ESP32 Dual-Sensor Dashboard\n"
        f"  Sensors : BMI160 (IMU) + ADS1292R (sEMG)\n"
        f"  URL     : {url}\n"
        f"  ESP32   : {'auto-detect' if not args.serial_port else args.serial_port} @ {SERIAL_BAUD} baud\n"
        f"  Ctrl+C để dừng\n"
        f"{'='*60}\n",
        flush=True,
    )

    if not args.no_browser:
        webbrowser.open(url)

    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        print("\n[*] Đang dừng…")
        stop_event.set()
        bridge.stop()
        server.server_close()


if __name__ == "__main__":
    main()
