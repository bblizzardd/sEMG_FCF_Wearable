"""
Combined ADS sEMG + BMI160 IMU dual-sensor dashboard.
- ADS bridge  : đọc cổng ADS1292R (115200 baud, protocol $D, / telemetry)
- BMI bridge  : đọc cổng BMI160   (460800 baud, CSV protocol)
- HTTP/SSE    : phục vụ web từ thư mục ./web
Chạy: python live_combined_visualizer.py [--ads-port COM14] [--bmi-port COM10]
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

# ---------------------------------------------------------------------------
# Hằng số
# ---------------------------------------------------------------------------
USB_VENDORS = {0x1A86, 0x10C4, 0x0403, 0x303A}
ADS_BAUD = 115200
BMI_BAUD = 460800
BUCKET_SIZE = 10   # 2000 SPS / 10 = 200 Hz preview


# ===========================================================================
# ADS sEMG State
# ===========================================================================
class AdsState:
    """Trạng thái và bộ đệm dữ liệu ADS1292R."""

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
        self.measured_sps = 2000.0
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
                    and 1500 <= self.measured_sps <= 2200
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
        """Xử lý dòng $D,... (2000 SPS dataset)."""
        if len(parts) < 7:
            return
        s_idx = int(parts[0])
        hw_us = int(parts[1])
        ch1_24 = int(parts[2])
        ch2_24 = int(parts[3])
        raw16 = int(parts[4])
        filt16 = int(parts[5])
        loff = int(parts[6])

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

            self.lead_off = loff == 1

            if self.total_received % 1000 == 0:
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
                if self.record_count % 1000 == 0:
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
# BMI Serial Bridge
# ===========================================================================
def port_identity(port):
    return (port.get("vid"), port.get("pid"), port.get("serial_number"))


def choose_bmi_port(ports, requested=None, remembered=None):
    if requested:
        return next((p for p in ports if p["device"] == requested), None)
    candidates = [p for p in ports if p.get("vid") in USB_VENDORS]
    if remembered:
        candidates = [p for p in candidates if port_identity(p) == remembered]
    return candidates[0] if len(candidates) == 1 else None


class BmiSerialBridge:
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
        self.state = {
            "connected": False,
            "device": None,
            "ports": [],
            "error": "Đang tìm cổng USB-UART…",
            "automatic": True,
        }
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
                    self.clients.discard(client)
                    while not client.empty():
                        client.get_nowait()
                    client.put_nowait(
                        ("overflow", {"error": "Trình duyệt nhận chậm: luồng bị gián đoạn. CSV đã ghi sẽ được tách."})
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
                    self.update(
                        connected=False,
                        device=None,
                        error="Đang tìm cổng…" if enabled else "Đã ngắt kết nối",
                    )
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
                    candidate = choose_bmi_port(ports, requested, self.remembered)
                    retry_at = now + 2
                    if not candidate:
                        message = "Chưa thấy ESP32 BMI160. Cắm USB hoặc chọn cổng trên web."
                        if len([p for p in ports if p.get("vid") in USB_VENDORS]) > 1:
                            message = "Có nhiều cổng USB-UART. Chọn cổng BMI160 trên web."
                        self.update(error=message)
                        self.stop_event.wait(0.1)
                        continue
                    try:
                        connection = self.serial_factory(
                            port=None, baudrate=BMI_BAUD, timeout=0.1, write_timeout=0.5
                        )
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
                        self.update(
                            connected=False,
                            device=None,
                            error="Không mở được " + candidate["device"] + ": " + str(error) + ". Đóng Serial Monitor.",
                        )
                        continue
                try:
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

        # --- BMI endpoints (dùng bởi app.mjs gốc) ---
        if self.path == "/api/status":
            self.json_response({**self.server.bmi_bridge.snapshot(), "token": self.server.token})
            return

        if self.path == "/api/events":
            client = self.server.bmi_bridge.subscribe()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Connection", "close")
            self.end_headers()
            self.connection.settimeout(5)
            try:
                while not self.server.bmi_bridge.stop_event.is_set():
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
                with self.server.bmi_bridge.lock:
                    self.server.bmi_bridge.clients.discard(client)
                self.close_connection = True
            return

        # --- ADS endpoints ---
        if self.path == "/api/ads/status":
            self.json_response(self.server.ads_state.snapshot())
            return

        if self.path == "/api/ads/stream":
            # SSE push 25 Hz
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

            # BMI commands
            if self.path == "/api/connect":
                requested = payload.get("port") or None
                if requested is not None and not isinstance(requested, str):
                    raise ValueError("Cổng không hợp lệ")
                self.server.bmi_bridge.configure(requested=requested)
            elif self.path == "/api/disconnect":
                self.server.bmi_bridge.configure(enabled=False)
            elif self.path == "/api/command":
                self.server.bmi_bridge.command(payload.get("command"))

            # ADS commands (gửi ký tự điều khiển qua serial ADS)
            elif self.path == "/api/ads/command":
                key = payload.get("command", "")
                with self.server.ads_serial_lock:
                    s = self.server.ads_ser_ref[0]
                    if s and s.is_open:
                        s.write(key.encode("utf-8"))
                        s.flush()
                    else:
                        raise ValueError("ADS chưa kết nối")

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
        pass  # tắt HTTP log


# ===========================================================================
# main()
# ===========================================================================
def main():
    parser = argparse.ArgumentParser(description="Combined ADS sEMG + BMI160 IMU dashboard")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port (default: 8765)")
    parser.add_argument("--ads-port", default="", help="Cổng ADS1292R, vd COM14. Mặc định: tự tìm.")
    parser.add_argument("--bmi-port", default=None, help="Cổng BMI160, vd COM10. Mặc định: tự tìm.")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    if serial is None:
        parser.exit(1, "Cài pyserial: python -m pip install pyserial\n")
    if not 1 <= args.port <= 65535:
        parser.error("--port phải từ 1 đến 65535")

    root = Path(__file__).resolve().parent / "web"
    if not root.is_dir():
        parser.exit(1, f"Không tìm thấy thư mục web: {root}\n")

    # --- ADS state ---
    ads_state = AdsState()
    ads_ser_ref = [None]          # mutable ref tới serial ADS (để POST command)
    ads_serial_lock = threading.Lock()
    stop_event = threading.Event()

    def ads_worker():
        requested = args.ads_port

        def find_port():
            if requested:
                return requested
            for p in list(list_ports.comports()):
                desc = (p.description or "").upper()
                hwid = (p.hwid or "").upper()
                if "303A" in hwid or "CH34" in desc or "CP210" in desc or "USB SERIAL" in desc:
                    return p.device
            return "COM14"

        while not stop_event.is_set():
            port_name = find_port()
            print(f"[ADS] Đang kết nối: {port_name} @ {ADS_BAUD}…")
            try:
                ser = serial.Serial(port_name, ADS_BAUD, timeout=0.05)
                ser.dtr = True
                ser.rts = True
                with ads_serial_lock:
                    ads_ser_ref[0] = ser
                with ads_state.lock:
                    ads_state.connected = True
                    ads_state.port = port_name
                print(f"[ADS] Kết nối thành công: {port_name}")

                byte_buf = bytearray()
                empty_cycles = 0
                last_stat = time.perf_counter()

                while not stop_event.is_set():
                    waiting = ser.in_waiting
                    chunk = ser.read(max(waiting, 1024))
                    if not chunk:
                        empty_cycles += 1
                        if empty_cycles > 50:
                            current_ports = [p.device for p in list_ports.comports()]
                            if port_name not in current_ports:
                                print(f"[ADS] Cổng {port_name} bị rút!")
                                break
                            empty_cycles = 0
                        time.sleep(0.002)
                        continue

                    empty_cycles = 0
                    byte_buf.extend(chunk)

                    while True:
                        nl = byte_buf.find(b"\n")
                        if nl < 0:
                            break
                        raw_line = byte_buf[:nl]
                        del byte_buf[:nl + 1]
                        if not raw_line:
                            continue
                        line = raw_line.decode("utf-8", errors="ignore").strip()
                        if not line:
                            continue

                        if line.startswith("$D,"):
                            try:
                                ads_state.process_dataset_line(line[3:].split(","))
                            except Exception:
                                pass
                            continue

                        if "Raw:" in line and "Env:" in line:
                            now = time.perf_counter()
                            if now - last_stat > 3.0:
                                last_stat = now
                                with ads_state.lock:
                                    sps = ads_state.measured_sps
                                    dropped = ads_state.total_dropped
                                print(f"[ADS] {line[:80]} | SPS:{sps:.0f} | Drop:{dropped}")
                            try:
                                ads_state.process_telemetry_line(line)
                            except Exception:
                                pass

            except Exception as exc:
                print(f"[ADS] Lỗi ({port_name}): {exc}. Thử lại sau 2s…")
            finally:
                with ads_serial_lock:
                    ads_ser_ref[0] = None
                with ads_state.lock:
                    ads_state.connected = False
            if not stop_event.is_set():
                stop_event.wait(2.0)

    ads_thread = threading.Thread(target=ads_worker, daemon=True, name="ads-serial")

    # --- BMI bridge ---
    bmi_bridge = BmiSerialBridge(requested=args.bmi_port)

    # --- HTTP server ---
    try:
        server = ThreadingHTTPServer(
            ("127.0.0.1", args.port),
            functools.partial(CombinedHandler, directory=str(root)),
        )
    except OSError as error:
        parser.exit(1, f"Không thể mở server: {error}. Thử --port 8766.\n")

    server.bmi_bridge = bmi_bridge
    server.ads_state = ads_state
    server.ads_ser_ref = ads_ser_ref
    server.ads_serial_lock = ads_serial_lock
    server.stop_event = stop_event
    server.token = secrets.token_urlsafe(32)

    ads_thread.start()
    bmi_bridge.start()

    url = f"http://localhost:{args.port}"
    print(
        f"\n{'='*60}\n"
        f"  Combined ADS sEMG + BMI160 Dashboard\n"
        f"  URL  : {url}\n"
        f"  ADS  : {'auto-detect' if not args.ads_port else args.ads_port} @ {ADS_BAUD} baud\n"
        f"  BMI  : {'auto-detect' if not args.bmi_port else args.bmi_port} @ {BMI_BAUD} baud\n"
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
        bmi_bridge.stop()
        server.server_close()


if __name__ == "__main__":
    main()
