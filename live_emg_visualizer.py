import os
import sys
import time
import json
import queue
import socket
import threading
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import serial
import serial.tools.list_ports

# Đảm bảo terminal Windows không bị lỗi Unicode khi in tiếng Việt
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PORT_HTTP = 8765
SERIAL_BAUD = 115200
DEFAULT_COM = sys.argv[1] if len(sys.argv) > 1 else "COM14"

# ==============================================================================
# TRẠNG THÁI TOÀN CỤC & BIẾN ĐO LƯỜNG CHẤT LƯỢNG DỮ LIỆU (DATA HEALTH)
# ==============================================================================
serial_status = "Đang kết nối..."
latest_data = {
    "raw": 0,
    "filt": 0,
    "env": 0,
    "base": 0,
    "sens": "x1.00",
    "percent": 0,
    "status": "ĐANG KẾT NỐI...",
    "port": DEFAULT_COM,
    "dsp": "DSP:ON",
    "connected": False,
    "timestamp": 0,
    "health": {
        "sps": 2000.0,
        "received": 0,
        "dropped": 0,
        "max_gap_us": 500,
        "clipping_pct": 0.0,
        "lead_off": False,
        "healthy": True
    }
}

clients_lock = threading.Lock()
connected_queues = []
ser_instance = None
ser_lock = threading.Lock()

recording = False
record_file = None
record_count = 0

# Biến theo dõi chất lượng dataset 2000 SPS
total_samples_received = 0
last_sample_seq = None
total_dropped_samples = 0
clipped_sample_count = 0
last_timestamp_ns = 0
max_gap_us = 500
lead_off_state = False

sps_window_start = time.perf_counter()
sps_sample_count = 0
current_measured_sps = 2000.0

# Min/Max bucket accumulator cho QC Preview (bảo toàn 100% gai nhiễu / spike)
BUCKET_SIZE = 10  # 2000 SPS / 10 = 200 Hz preview
bucket_counter = 0
b_min_raw = float('inf')
b_max_raw = float('-inf')
b_min_filt = float('inf')
b_max_filt = float('-inf')
latest_qc_raw = 0
latest_qc_filt = 0

def find_serial_port():
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        desc = (p.description or "").upper()
        hwid = (p.hwid or "").upper()
        if "303A" in hwid or "CH34" in desc or "CP210" in desc or "USB SERIAL" in desc:
            return p.device
    for p in ports:
        if p.device.upper() == DEFAULT_COM.upper():
            return p.device
    if ports:
        return ports[0].device
    return DEFAULT_COM

def broadcast_data(data_obj):
    json_str = f"data: {json.dumps(data_obj)}\n\n"
    with clients_lock:
        for q in connected_queues:
            try:
                q.put_nowait(json_str)
            except queue.Full:
                # Bỏ qua mẫu cũ để bộ đệm SSE luôn nhận dữ liệu thời gian thực mới nhất (Zero-lag)
                try:
                    q.get_nowait()
                    q.put_nowait(json_str)
                except Exception:
                    pass

def serial_worker():
    global ser_instance, latest_data, recording, record_file, record_count, serial_status
    global total_samples_received, last_sample_seq, total_dropped_samples, clipped_sample_count
    global last_timestamp_ns, max_gap_us, lead_off_state, sps_window_start, sps_sample_count, current_measured_sps
    global bucket_counter, b_min_raw, b_max_raw, b_min_filt, b_max_filt, latest_qc_raw, latest_qc_filt

    while True:
        port_name = find_serial_port()
        serial_status = f"Đang mở cổng {port_name}..."
        print(f"[*] Đang kết nối Serial: {port_name} @ {SERIAL_BAUD}...")

        try:
            ser = serial.Serial(port_name, SERIAL_BAUD, timeout=0.05)
            ser.dtr = True
            ser.rts = True
            with ser_lock:
                ser_instance = ser
            serial_status = f"Đã kết nối: {port_name}"
            print(f"[+] KẾT NỐI THÀNH CÔNG VỚI {port_name}! Tối ưu hóa bộ đệm I/O (Chunked buffer)...")

            byte_buf = bytearray()
            empty_cycles = 0
            last_stat_log = time.perf_counter()

            while True:
                # Đọc theo khối (chunk) thay vì đọc từng byte: giảm 99% overhead syscall và GIL
                waiting = ser.in_waiting
                chunk = ser.read(max(waiting, 1024))
                if not chunk:
                    empty_cycles += 1
                    if empty_cycles > 50:
                        current_ports = [p.device for p in serial.tools.list_ports.comports()]
                        if port_name not in current_ports:
                            print(f"[!] Cổng {port_name} đã bị rút cáp!")
                            break
                        empty_cycles = 0
                    time.sleep(0.002)
                    continue

                empty_cycles = 0
                byte_buf.extend(chunk)

                # Tách từng dòng trong bộ nhớ bytearray cực nhanh
                while True:
                    nl_pos = byte_buf.find(b'\n')
                    if nl_pos < 0:
                        break
                    raw_line = byte_buf[:nl_pos]
                    del byte_buf[:nl_pos + 1]
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue

                    # ==============================================================
                    # LUỒNG 1: MẪU DATASET GỐC 2000 SPS ($D,seq,ch1,ch2,raw16,filt16,loff)
                    # ==============================================================
                    if line.startswith("$D,"):
                        try:
                            parts = line[3:].split(",")
                            if len(parts) >= 7:
                                s_idx = int(parts[0])
                                hw_us = int(parts[1])
                                ch1_24 = int(parts[2])
                                ch2_24 = int(parts[3])
                                raw16 = int(parts[4])
                                filt16 = int(parts[5])
                                loff = int(parts[6])

                                # 1. Phát hiện mất mẫu bằng sample_idx liên tục
                                if last_sample_seq is not None:
                                    diff = s_idx - (last_sample_seq + 1)
                                    if diff > 0:
                                        total_dropped_samples += diff
                                last_sample_seq = s_idx
                                total_samples_received += 1
                                sps_sample_count += 1

                                # 2. Đo khoảng cách thời gian giữa 2 mẫu bằng Hardware Timestamp thực tế
                                if last_timestamp_ns > 0:
                                    gap_us = hw_us - last_timestamp_ns
                                    if gap_us < 0:
                                        gap_us += 4294967296
                                    if gap_us > max_gap_us and total_samples_received > 200:
                                        max_gap_us = gap_us
                                last_timestamp_ns = hw_us

                                # 3. Phát hiện bão hòa tín hiệu (Clipping / Saturation)
                                if abs(raw16) >= 32700 or abs(ch2_24) >= 8388000:
                                    clipped_sample_count += 1

                                lead_off_state = (loff == 1)

                                # 4. Tính toán tốc độ lấy mẫu thực tế (SPS) mỗi 1 giây
                                if total_samples_received % 1000 == 0:
                                    now_perf = time.perf_counter()
                                    elapsed_sps = now_perf - sps_window_start
                                    if elapsed_sps >= 0.8:
                                        current_measured_sps = sps_sample_count / elapsed_sps
                                        sps_sample_count = 0
                                        sps_window_start = now_perf

                                # 5. Ghi Dataset nghiên cứu 2000 SPS vào file CSV với Hardware Timestamp chuẩn xác
                                if recording and record_file:
                                    record_file.write(f"{s_idx},{hw_us},{ch1_24},{ch2_24},{raw16},{filt16},{loff}\n")
                                    record_count += 1
                                    if record_count % 1000 == 0:
                                        record_file.flush()

                                # 6. Min/Max QC Decimation (giữ 100% gai nhiễu cho preview UI)
                                bucket_counter += 1
                                if raw16 < b_min_raw: b_min_raw = raw16
                                if raw16 > b_max_raw: b_max_raw = raw16
                                if filt16 < b_min_filt: b_min_filt = filt16
                                if filt16 > b_max_filt: b_max_filt = filt16

                                if bucket_counter >= BUCKET_SIZE:
                                    rep_raw = b_max_raw if abs(b_max_raw) > abs(b_min_raw) else b_min_raw
                                    rep_filt = b_max_filt if abs(b_max_filt) > abs(b_min_filt) else b_min_filt
                                    latest_qc_raw = rep_raw
                                    latest_qc_filt = rep_filt
                                    bucket_counter = 0
                                    b_min_raw, b_max_raw = float('inf'), float('-inf')
                                    b_min_filt, b_max_filt = float('inf'), float('-inf')

                        except Exception:
                            pass
                        continue

                    # ==============================================================
                    # LUỒNG 2: TELEMETRY UI PREVIEW 50 SPS (Mỗi 20ms)
                    # Raw:%6ld | Filt:%6ld | Env:%4ld | Base:%4ld | x%.2f | Luc:[...] %3d% | ...
                    # ==============================================================
                    if "Raw:" in line and "Env:" in line:
                        now_log = time.perf_counter()
                        if now_log - last_stat_log > 3.0:
                            last_stat_log = now_log
                            print(f"[STATUS] {line} | SPS: {current_measured_sps:.0f} | Drop: {total_dropped_samples}")
                        try:
                            parts = [p.strip() for p in line.split("|")]
                            raw_val = latest_qc_raw
                            filt_val = latest_qc_filt
                            env_val = 0
                            base_val = 0
                            sensitivity_str = "x1.00"
                            percent_val = 0
                            status_val = "THA LONG"
                            dsp_val = "DSP:ON"

                            for p in parts:
                                if p.startswith("Raw:") and total_samples_received == 0:
                                    raw_val = int(p.replace("Raw:", "").strip())
                                elif p.startswith("Filt:") and total_samples_received == 0:
                                    filt_val = int(p.replace("Filt:", "").strip())
                                elif p.startswith("Env:"):
                                    env_val = int(p.replace("Env:", "").strip())
                                elif p.startswith("Base:"):
                                    base_val = int(p.replace("Base:", "").strip())
                                elif p.startswith("x") and len(p) <= 6:
                                    sensitivity_str = p
                                elif "%" in p:
                                    pct_idx = p.find("%")
                                    num_str = p[:pct_idx].split()[-1]
                                    percent_val = int(num_str)
                                elif any(k in p for k in ["THA LONG", "GONG NHE", "GONG VUA", "GONG MANH"]):
                                    status_val = p
                                elif "DSP:ON" in p:
                                    dsp_val = "DSP:ON"
                                elif "DSP:OFF" in p:
                                    dsp_val = "DSP:OFF"

                            is_healthy = (total_dropped_samples == 0 and 1500 <= current_measured_sps <= 2200 and not lead_off_state)

                            data_point = {
                                "raw": raw_val,
                                "filt": filt_val,
                                "env": env_val,
                                "base": base_val,
                                "sens": sensitivity_str,
                                "percent": percent_val,
                                "status": status_val,
                                "dsp": dsp_val,
                                "port": port_name,
                                "connected": True,
                                "timestamp": int(time.time() * 1000),
                                "health": {
                                    "sps": round(current_measured_sps, 1),
                                    "received": total_samples_received,
                                    "dropped": total_dropped_samples,
                                    "max_gap_us": max_gap_us,
                                    "clipping_pct": round((clipped_sample_count / max(1, total_samples_received)) * 100, 2),
                                    "lead_off": lead_off_state,
                                    "recording": recording,
                                    "record_count": record_count,
                                    "healthy": is_healthy
                                }
                            }

                            latest_data = data_point
                            broadcast_data(data_point)

                        except Exception:
                            pass
                    elif line.startswith("[") or "CÂN CHỈNH" in line or "ĐỘ NHẠY" in line:
                        print("[ESP32]", line)

        except Exception as e:
            serial_status = f"Lỗi cổng ({port_name}): {e}"
            print(f"[!] Lỗi Serial ({port_name}): {e}. Đang thử kết nối lại sau 2s...")
            with ser_lock:
                ser_instance = None
            time.sleep(2)

HTML_PAGE = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>sEMG Dual-Stream Visualizer & Dataset QC | 2000 SPS</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #07090e;
            --bg-card: rgba(15, 20, 32, 0.88);
            --border-card: rgba(255, 255, 255, 0.08);
            --neon-blue: #00f0ff;
            --neon-green: #00ff88;
            --neon-orange: #ff9900;
            --neon-red: #ff3366;
            --neon-purple: #b55fe6;
            --text-main: #f1f5f9;
            --text-dim: #94a3b8;
            --font-sans: 'Plus Jakarta Sans', sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background-color: var(--bg-dark);
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(0, 240, 255, 0.08) 0%, transparent 40%),
                radial-gradient(circle at 90% 80%, rgba(0, 255, 136, 0.06) 0%, transparent 40%);
            color: var(--text-main);
            font-family: var(--font-sans);
            min-height: 100vh;
            padding: 16px;
        }

        .container { max-width: 1440px; margin: 0 auto; }

        /* HEADER */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 16px;
            padding: 12px 20px;
            margin-bottom: 14px;
            backdrop-filter: blur(16px);
        }

        .title-group { display: flex; align-items: center; gap: 12px; }
        .logo-pulse {
            width: 12px; height: 12px; border-radius: 50%;
            background: var(--neon-green);
            box-shadow: 0 0 14px var(--neon-green);
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.85); } }

        h1 { font-size: 1.15rem; font-weight: 800; letter-spacing: -0.02em; }
        .subtitle { font-size: 0.78rem; color: var(--text-dim); margin-top: 2px; }

        .btn-group { display: flex; gap: 8px; align-items: center; }
        .btn {
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid var(--border-card);
            color: var(--text-main);
            padding: 7px 13px;
            border-radius: 10px;
            font-size: 0.82rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.08s ease, background 0.15s ease, border-color 0.15s ease;
            display: flex;
            align-items: center;
            gap: 6px;
            user-select: none;
        }
        .btn:hover { background: rgba(0, 240, 255, 0.15); border-color: var(--neon-blue); }
        .btn:active { transform: scale(0.94); background: rgba(0, 240, 255, 0.3) !important; }
        .btn-active { background: rgba(255, 51, 102, 0.25) !important; border-color: var(--neon-red) !important; color: #ff6b8b !important; }

        .port-pill {
            font-family: var(--font-mono);
            font-size: 0.78rem;
            padding: 4px 10px;
            border-radius: 20px;
            background: rgba(0, 255, 136, 0.1);
            color: var(--neon-green);
            border: 1px solid rgba(0, 255, 136, 0.3);
        }

        /* DATA QUALITY & HEALTH BAR */
        .health-card {
            background: rgba(12, 17, 29, 0.95);
            border: 1px solid rgba(0, 240, 255, 0.2);
            border-radius: 14px;
            padding: 12px 18px;
            margin-bottom: 16px;
            backdrop-filter: blur(16px);
        }
        .health-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
            padding-bottom: 6px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }
        .health-title {
            font-size: 0.8rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--neon-blue);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .health-badge {
            font-size: 0.78rem;
            font-weight: 800;
            padding: 3px 12px;
            border-radius: 20px;
            letter-spacing: 0.04em;
        }
        .health-badge.healthy {
            background: rgba(0, 255, 136, 0.15);
            color: var(--neon-green);
            border: 1px solid rgba(0, 255, 136, 0.4);
        }
        .health-badge.corrupted {
            background: rgba(255, 51, 102, 0.2);
            color: var(--neon-red);
            border: 1px solid rgba(255, 51, 102, 0.5);
            animation: pulse 1s infinite;
        }

        .health-grid {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 10px;
        }
        @media (max-width: 1100px) {
            .health-grid { grid-template-columns: repeat(4, 1fr); }
        }
        @media (max-width: 650px) {
            .health-grid { grid-template-columns: repeat(2, 1fr); }
        }
        .health-item {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-card);
            border-radius: 10px;
            padding: 8px 12px;
            display: flex;
            flex-direction: column;
            position: relative;
        }
        .health-label {
            font-size: 0.68rem;
            color: var(--text-dim);
            text-transform: uppercase;
            font-weight: 600;
            letter-spacing: 0.03em;
        }
        .health-value {
            font-family: var(--font-mono);
            font-size: 0.95rem;
            font-weight: 700;
            margin-top: 2px;
            color: var(--text-main);
        }
        .h-check {
            position: absolute;
            top: 6px;
            right: 8px;
            font-size: 0.75rem;
            font-weight: 800;
        }
        .h-ok { color: var(--neon-green); }
        .h-warn { color: var(--neon-red); }

        /* MAIN DASHBOARD LAYOUT */
        .dashboard-grid {
            display: grid;
            grid-template-columns: 1.55fr 1fr;
            gap: 16px;
        }
        @media (max-width: 980px) {
            .dashboard-grid { grid-template-columns: 1fr; }
        }

        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 16px;
            padding: 16px;
            backdrop-filter: blur(16px);
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--border-card);
        }
        .card-title {
            font-size: 0.88rem;
            font-weight: 700;
            letter-spacing: -0.01em;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* DUAL OSCILLOSCOPES */
        .scope-container {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .scope-box {
            background: rgba(4, 7, 12, 0.9);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 12px;
            padding: 8px 12px 10px;
            position: relative;
        }
        .scope-box-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }
        .scope-label {
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .scope-legend {
            font-size: 0.72rem;
            font-family: var(--font-mono);
            color: var(--text-dim);
        }
        canvas {
            display: block;
            width: 100%;
            height: 120px;
            border-radius: 8px;
            background: #04070c;
        }

        /* MUSCLE FORCE GAUGE */
        .gauge-section {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 10px 0 16px;
        }
        .gauge-wrapper {
            position: relative;
            width: 190px;
            height: 190px;
            margin-bottom: 14px;
        }
        .gauge-circle {
            width: 100%;
            height: 100%;
            transform: rotate(-90deg);
        }
        .gauge-bg {
            fill: none;
            stroke: rgba(255, 255, 255, 0.06);
            stroke-width: 14;
        }
        .gauge-fill {
            fill: none;
            stroke: var(--neon-green);
            stroke-width: 14;
            stroke-linecap: round;
            stroke-dasharray: 565.48;
            stroke-dashoffset: 565.48;
            transition: stroke-dashoffset 0.08s ease-out, stroke 0.2s ease;
        }
        .gauge-inner-val {
            position: absolute;
            top: 0; left: 0; width: 100%; height: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }
        .percent-number {
            font-family: var(--font-mono);
            font-size: 2.8rem;
            font-weight: 800;
            line-height: 1;
            letter-spacing: -0.04em;
        }
        .percent-unit {
            font-size: 0.72rem;
            font-weight: 700;
            color: var(--text-dim);
            margin-top: 4px;
            letter-spacing: 0.08em;
        }

        .status-badge {
            font-size: 0.88rem;
            font-weight: 800;
            padding: 5px 18px;
            border-radius: 20px;
            letter-spacing: 0.04em;
            background: rgba(0, 255, 136, 0.15);
            color: var(--neon-green);
            border: 1px solid rgba(0, 255, 136, 0.4);
            margin-top: 4px;
            transition: all 0.2s;
        }

        /* STATS & CONTROL BAR */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin-top: 10px;
        }
        .stat-item {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-card);
            border-radius: 10px;
            padding: 10px 12px;
            text-align: center;
        }
        .stat-name {
            font-size: 0.72rem;
            color: var(--text-dim);
            text-transform: uppercase;
            font-weight: 600;
        }
        .stat-val {
            font-family: var(--font-mono);
            font-size: 1.15rem;
            font-weight: 800;
            margin-top: 3px;
        }

        .quick-controls {
            display: flex;
            gap: 8px;
            margin-top: 12px;
            justify-content: center;
        }

        .keys-hint {
            font-size: 0.72rem;
            color: var(--text-dim);
            text-align: center;
            margin-top: 10px;
        }
        kbd {
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            padding: 2px 6px;
            border-radius: 4px;
            font-family: var(--font-mono);
            font-size: 0.72rem;
            color: var(--neon-blue);
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- HEADER -->
        <header>
            <div class="title-group">
                <div class="logo-pulse"></div>
                <div>
                    <h1>sEMG Dual-Stream Visualizer &amp; Dataset QC</h1>
                    <div class="subtitle">ADS1292R 2000 SPS Biopotential Acquisition &bull; Zero-Loss Engine</div>
                </div>
            </div>
            <div class="btn-group">
                <div class="port-pill" id="lblPortPill">COM14</div>
                <button class="btn" id="btnFilter" onclick="sendCmd('f')">🛡️ Giảm Nhiễu: BẬT (F)</button>
                <button class="btn" id="btnSensDown" onclick="sendCmd('-')">➖ Giảm Nhạy (-)</button>
                <button class="btn" id="btnSensUp" onclick="sendCmd('+')">➕ Tăng Nhạy (+)</button>
                <button class="btn" onclick="sendCmd('c')">⚡ Cân Chỉnh (C)</button>
                <button class="btn" id="btnRecord" onclick="toggleRecord()">🔴 Ghi CSV (2000 SPS)</button>
                <button class="btn" onclick="resetQC()">🔄 Reset QC</button>
            </div>
        </header>

        <!-- DATASET QUALITY CONTROL BAR (2000 SPS VERIFICATION) -->
        <div class="health-card">
            <div class="health-header">
                <div class="health-title">
                    <span>🔬 KIỂM CHỨNG CHẤT LƯỢNG DATASET 2000 SPS (SAMPLE CONTINUITY &amp; TIMING QC)</span>
                </div>
                <div class="health-badge healthy" id="badgeHealth">● DATASET HEALTHY</div>
            </div>
            <div class="health-grid">
                <div class="health-item">
                    <span class="health-label">Tốc độ thực tế</span>
                    <span class="health-value" id="valSps">2000.0 SPS</span>
                    <span class="h-check h-ok" id="chkSps">✓</span>
                </div>
                <div class="health-item">
                    <span class="health-label">Số mẫu thu nhận</span>
                    <span class="health-value" id="valReceived">0</span>
                    <span class="h-check h-ok">✓</span>
                </div>
                <div class="health-item">
                    <span class="health-label">Mất mẫu (Sequence Drop)</span>
                    <span class="health-value" id="valDropped" style="color: var(--neon-green);">0</span>
                    <span class="h-check h-ok" id="chkDropped">✓</span>
                </div>
                <div class="health-item">
                    <span class="health-label">Độ lệch chu kỳ (Max Gap)</span>
                    <span class="health-value" id="valGap">500 µs</span>
                    <span class="h-check h-ok" id="chkGap">✓</span>
                </div>
                <div class="health-item">
                    <span class="health-label">Bão hòa (Clipping)</span>
                    <span class="health-value" id="valClip">0.0%</span>
                    <span class="h-check h-ok" id="chkClip">✓</span>
                </div>
                <div class="health-item">
                    <span class="health-label">Tiếp xúc điện cực (Lead-Off)</span>
                    <span class="health-value" id="valLeadOff" style="color: var(--neon-green);">CONNECTED</span>
                    <span class="h-check h-ok" id="chkLeadOff">✓</span>
                </div>
                <div class="health-item">
                    <span class="health-label">Trạng thái Ghi CSV</span>
                    <span class="health-value" id="valRecStatus" style="color: var(--text-dim);">STANDBY</span>
                    <span class="h-check h-ok" id="chkRec">○</span>
                </div>
            </div>
        </div>

        <!-- MAIN DASHBOARD -->
        <div class="dashboard-grid">
            <!-- LEFT: 3 WAVEFORM CANVASES -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <span>📈 DUAL-STREAM WAVEFORM SCOPES</span>
                    </div>
                    <div style="display:flex; gap: 8px;">
                        <span class="port-pill" id="lblSensPill">x1.00</span>
                    </div>
                </div>

                <div class="scope-container">
                    <!-- Scope 1: RAW ADC QC PREVIEW -->
                    <div class="scope-box">
                        <div class="scope-box-header">
                            <div class="scope-label" style="color: var(--neon-blue);">
                                <span>■ Luồng 1: Raw ADC QC (Chưa lọc - Min/Max Decimation)</span>
                            </div>
                            <div class="scope-legend" id="txtRawVal">Raw ADC: 0</div>
                        </div>
                        <canvas id="canvasRaw"></canvas>
                    </div>

                    <!-- Scope 2: FILTERED sEMG BIOPOTENTIALS -->
                    <div class="scope-box">
                        <div class="scope-box-header">
                            <div class="scope-label" style="color: var(--neon-purple);">
                                <span>■ Luồng 2: Filtered sEMG (HPF 20Hz + Notch 50/100/150 + LPF 150Hz)</span>
                            </div>
                            <div class="scope-legend" id="txtFiltVal">Filt sEMG: 0</div>
                        </div>
                        <canvas id="canvasFilt"></canvas>
                    </div>

                    <!-- Scope 3: FORCE ENVELOPE & BASELINE -->
                    <div class="scope-box">
                        <div class="scope-box-header">
                            <div class="scope-label" style="color: var(--neon-green);">
                                <span>■ Bao hình lực cơ (Envelope) &amp; Mức nghỉ (Baseline)</span>
                            </div>
                            <div class="scope-legend" id="txtEnvVal">Env: 0 | Base: 0</div>
                        </div>
                        <canvas id="canvasEnv"></canvas>
                    </div>
                </div>
            </div>

            <!-- RIGHT: FORCE GAUGE & CALIBRATION METRICS -->
            <div class="card" style="display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <div class="card-header">
                        <div class="card-title">
                            <span>💪 MỨC CO CƠ THỜI GIAN THỰC (%MVC)</span>
                        </div>
                    </div>

                    <div class="gauge-section">
                        <div class="gauge-wrapper">
                            <svg class="gauge-circle" viewBox="0 0 200 200">
                                <circle class="gauge-bg" cx="100" cy="100" r="85"></circle>
                                <circle class="gauge-fill" id="gaugeProgress" cx="100" cy="100" r="85"></circle>
                            </svg>
                            <div class="gauge-inner-val">
                                <div class="percent-number" id="lblPercent">0</div>
                                <div class="percent-unit">PHẦN TRĂM (%)</div>
                            </div>
                        </div>
                        <div class="status-badge" id="lblStatus">THA LONG</div>
                    </div>

                    <div class="quick-controls">
                        <button class="btn" onclick="sendCmd('c')">⚡ Cân Chỉnh (C)</button>
                        <button class="btn" onclick="sendCmd('+')">➕ Tăng Nhạy (+)</button>
                        <button class="btn" onclick="sendCmd('-')">➖ Giảm Nhạy (-)</button>
                    </div>
                </div>

                <div>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <div class="stat-name">Mức Nghỉ (Base)</div>
                            <div class="stat-val" id="statBase" style="color: var(--neon-blue);">0</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-name">Bao Hình (Env)</div>
                            <div class="stat-val" id="statEnv" style="color: var(--neon-green);">0</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-name">Đỉnh Gồng (MVC)</div>
                            <div class="stat-val" id="statPeak" style="color: var(--neon-orange);">0</div>
                        </div>
                    </div>

                    <div class="keys-hint">
                        Phím tắt: <kbd>C</kbd> cân chỉnh zero &bull; <kbd>F</kbd> bật/tắt DSP &bull; <kbd>+</kbd>/<kbd>-</kbd> tăng/giảm nhạy
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const MAX_POINTS = 400;
        const rawHistory = new Array(MAX_POINTS).fill(0);
        const filtHistory = new Array(MAX_POINTS).fill(0);
        const envHistory = new Array(MAX_POINTS).fill(0);
        const baseHistory = new Array(MAX_POINTS).fill(0);

        const canvasRaw = document.getElementById('canvasRaw');
        const ctxRaw = canvasRaw.getContext('2d', { alpha: false });

        const canvasFilt = document.getElementById('canvasFilt');
        const ctxFilt = canvasFilt.getContext('2d', { alpha: false });

        const canvasEnv = document.getElementById('canvasEnv');
        const ctxEnv = canvasEnv.getContext('2d', { alpha: false });

        function resizeCanvases() {
            [canvasRaw, canvasFilt, canvasEnv].forEach(c => {
                if (c && c.parentElement) {
                    c.width = c.parentElement.clientWidth - 24;
                    c.height = 115;
                }
            });
        }
        window.addEventListener('resize', resizeCanvases);
        resizeCanvases();

        const gaugeCircle = document.getElementById('gaugeProgress');
        const circumference = 2 * Math.PI * 85; // r = 85 => 534.07
        gaugeCircle.style.strokeDasharray = circumference;

        function setGauge(pct) {
            pct = Math.max(0, Math.min(100, pct));
            const offset = circumference - (pct / 100) * circumference;
            gaugeCircle.style.strokeDashoffset = offset;

            if (pct >= 60) {
                gaugeCircle.style.stroke = 'var(--neon-red)';
            } else if (pct >= 25) {
                gaugeCircle.style.stroke = 'var(--neon-orange)';
            } else if (pct >= 8) {
                gaugeCircle.style.stroke = 'var(--neon-blue)';
            } else {
                gaugeCircle.style.stroke = 'var(--neon-green)';
            }
        }

        let maxFlexPeak = 100;
        let latestPacket = null;
        let smoothMaxE = 20;
        let smoothRangeF = 60;

        function drawGrid(ctx, w, h) {
            ctx.fillStyle = '#05080e';
            ctx.fillRect(0, 0, w, h);
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
            ctx.lineWidth = 1;
            for (let y = 25; y < h; y += 25) {
                ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
            }
        }

        // Tối ưu hóa cực đại vẽ Canvas: Dải động thích ứng thông minh (Adaptive Range)
        function drawWaveforms() {
            // 1. Raw ADC QC Canvas
            const wR = canvasRaw.width;
            const hR = canvasRaw.height;
            drawGrid(ctxRaw, wR, hR);

            let minR = rawHistory[0], maxR = rawHistory[0];
            for (let i = 1; i < MAX_POINTS; i++) {
                const v = rawHistory[i];
                if (v < minR) minR = v;
                if (v > maxR) maxR = v;
            }
            let rangeR = Math.max(1200, maxR - minR);
            let midR = (maxR + minR) / 2;

            ctxRaw.strokeStyle = '#00f0ff';
            ctxRaw.lineWidth = 1.6;
            ctxRaw.beginPath();
            for (let i = 0; i < MAX_POINTS; i++) {
                const x = (i / (MAX_POINTS - 1)) * wR;
                const normalized = (rawHistory[i] - midR) / rangeR;
                const y = hR / 2 - normalized * (hR * 0.42);
                if (i === 0) ctxRaw.moveTo(x, y); else ctxRaw.lineTo(x, y);
            }
            ctxRaw.stroke();

            // 2. Filtered sEMG Canvas (Tự động thích ứng biên độ sóng điện cơ)
            const wF = canvasFilt.width;
            const hF = canvasFilt.height;
            drawGrid(ctxFilt, wF, hF);

            let maxAbsF = 8;
            for (let i = 0; i < MAX_POINTS; i++) {
                const absV = Math.abs(filtHistory[i]);
                if (absV > maxAbsF) maxAbsF = absV;
            }
            let targetRangeF = Math.max(30, maxAbsF * 2.3);
            smoothRangeF += (targetRangeF - smoothRangeF) * 0.08;

            ctxFilt.strokeStyle = '#b55fe6';
            ctxFilt.lineWidth = 1.6;
            ctxFilt.beginPath();
            for (let i = 0; i < MAX_POINTS; i++) {
                const x = (i / (MAX_POINTS - 1)) * wF;
                const normalized = filtHistory[i] / (smoothRangeF / 2);
                const y = hF / 2 - normalized * (hF * 0.44);
                if (i === 0) ctxFilt.moveTo(x, y); else ctxFilt.lineTo(x, y);
            }
            ctxFilt.stroke();

            // 3. Envelope Canvas (Auto-scale thích ứng theo biên độ thực tế, không bị bẹp ở đáy)
            const wE = canvasEnv.width;
            const hE = canvasEnv.height;
            drawGrid(ctxEnv, wE, hE);

            let maxInHistory = 6;
            for (let i = 0; i < MAX_POINTS; i++) {
                if (envHistory[i] > maxInHistory) maxInHistory = envHistory[i];
                if (baseHistory[i] > maxInHistory) maxInHistory = baseHistory[i];
            }
            // Thang đo mượt: tối thiểu 16 để sóng nghỉ rõ ràng và không vỡ hình, 
            // tự động mở rộng theo đỉnh gồng để sóng luôn chiếm 60-80% chiều cao
            let targetMaxE = Math.max(16, maxInHistory * 1.35);
            smoothMaxE += (targetMaxE - smoothMaxE) * 0.08;

            // Baseline (xanh dương đứt nét)
            ctxEnv.strokeStyle = 'rgba(0, 240, 255, 0.6)';
            ctxEnv.lineWidth = 1.5;
            ctxEnv.setLineDash([4, 4]);
            ctxEnv.beginPath();
            for (let i = 0; i < MAX_POINTS; i++) {
                const x = (i / (MAX_POINTS - 1)) * wE;
                const normB = Math.min(1.0, Math.max(0, baseHistory[i] / smoothMaxE));
                const y = hE - normB * (hE * 0.82) - 8;
                if (i === 0) ctxEnv.moveTo(x, y); else ctxEnv.lineTo(x, y);
            }
            ctxEnv.stroke();
            ctxEnv.setLineDash([]);

            // Gradient dưới đường bao hình (Aesthetic Medical Fill)
            let gradEnv = ctxEnv.createLinearGradient(0, 0, 0, hE);
            gradEnv.addColorStop(0, 'rgba(0, 255, 136, 0.28)');
            gradEnv.addColorStop(1, 'rgba(0, 255, 136, 0.0)');

            ctxEnv.fillStyle = gradEnv;
            ctxEnv.beginPath();
            ctxEnv.moveTo(0, hE);
            for (let i = 0; i < MAX_POINTS; i++) {
                const x = (i / (MAX_POINTS - 1)) * wE;
                const normE = Math.min(1.0, Math.max(0, envHistory[i] / smoothMaxE));
                const y = hE - normE * (hE * 0.82) - 8;
                ctxEnv.lineTo(x, y);
            }
            ctxEnv.lineTo(wE, hE);
            ctxEnv.closePath();
            ctxEnv.fill();

            // Envelope line (xanh neon)
            ctxEnv.strokeStyle = '#00ff88';
            ctxEnv.lineWidth = 2.0;
            ctxEnv.beginPath();
            for (let i = 0; i < MAX_POINTS; i++) {
                const x = (i / (MAX_POINTS - 1)) * wE;
                const normE = Math.min(1.0, Math.max(0, envHistory[i] / smoothMaxE));
                const y = hE - normE * (hE * 0.82) - 8;
                if (i === 0) ctxEnv.moveTo(x, y); else ctxEnv.lineTo(x, y);
            }
            ctxEnv.stroke();

            requestAnimationFrame(drawWaveforms);
        }
        requestAnimationFrame(drawWaveforms);

        // Cập nhật DOM định kỳ 25 Hz (mỗi 40ms) để triệt tiêu tình trạng lag UI do DOM reflow
        setInterval(function updateDOM() {
            if (!latestPacket) return;
            const data = latestPacket;

            document.getElementById('txtRawVal').innerText = `Raw ADC: ${data.raw.toLocaleString()}`;
            document.getElementById('txtFiltVal').innerText = `Filt sEMG: ${data.filt.toLocaleString()} (±${Math.round(smoothRangeF / 2)})`;
            document.getElementById('txtEnvVal').innerText = `Env: ${data.env.toLocaleString()} | Base: ${data.base.toLocaleString()} (Thang: 0-${Math.round(smoothMaxE)})`;
            document.getElementById('lblPercent').innerText = data.percent;
            setGauge(data.percent);

            const badge = document.getElementById('lblStatus');
            badge.innerText = data.status;
            if (data.status.includes('MANH')) {
                badge.style.color = 'var(--neon-red)';
                badge.style.borderColor = 'rgba(255, 51, 102, 0.4)';
                badge.style.background = 'rgba(255, 51, 102, 0.15)';
            } else if (data.status.includes('VUA')) {
                badge.style.color = 'var(--neon-orange)';
                badge.style.borderColor = 'rgba(255, 153, 0, 0.4)';
                badge.style.background = 'rgba(255, 153, 0, 0.15)';
            } else if (data.status.includes('NHE')) {
                badge.style.color = 'var(--neon-blue)';
                badge.style.borderColor = 'rgba(0, 240, 255, 0.4)';
                badge.style.background = 'rgba(0, 240, 255, 0.15)';
            } else {
                badge.style.color = 'var(--neon-green)';
                badge.style.borderColor = 'rgba(0, 255, 136, 0.4)';
                badge.style.background = 'rgba(0, 255, 136, 0.15)';
            }

            document.getElementById('statBase').innerText = data.base.toLocaleString();
            document.getElementById('statEnv').innerText = data.env.toLocaleString();
            document.getElementById('statPeak').innerText = maxFlexPeak.toLocaleString();
            if (data.sens) document.getElementById('lblSensPill').innerText = data.sens;
            if (data.port) document.getElementById('lblPortPill').innerText = data.port;

            if (data.health) {
                const h = data.health;
                document.getElementById('valSps').innerText = `${h.sps} SPS`;
                document.getElementById('valReceived').innerText = h.received.toLocaleString();
                document.getElementById('valDropped').innerText = h.dropped.toLocaleString();
                document.getElementById('valGap').innerText = `${h.max_gap_us} µs`;
                document.getElementById('valClip').innerText = `${h.clipping_pct}%`;
                document.getElementById('valLeadOff').innerText = h.lead_off ? "LEAD-OFF" : "CONNECTED";

                const chkSps = document.getElementById('chkSps');
                if (chkSps) {
                    chkSps.innerText = h.sps >= 1500 ? "✓" : "✗";
                    chkSps.className = h.sps >= 1500 ? "h-check h-ok" : "h-check h-warn";
                }

                const chkDropped = document.getElementById('chkDropped');
                if (chkDropped) {
                    chkDropped.innerText = h.dropped === 0 ? "✓" : "✗";
                    chkDropped.className = h.dropped === 0 ? "h-check h-ok" : "h-check h-warn";
                }

                const chkGap = document.getElementById('chkGap');
                if (chkGap) {
                    chkGap.innerText = h.max_gap_us <= 2000 ? "✓" : "✗";
                    chkGap.className = h.max_gap_us <= 2000 ? "h-check h-ok" : "h-check h-warn";
                }

                const chkClip = document.getElementById('chkClip');
                if (chkClip) {
                    chkClip.innerText = h.clipping_pct < 1.0 ? "✓" : "✗";
                    chkClip.className = h.clipping_pct < 1.0 ? "h-check h-ok" : "h-check h-warn";
                }

                const chkLeadOff = document.getElementById('chkLeadOff');
                if (chkLeadOff) {
                    chkLeadOff.innerText = !h.lead_off ? "✓" : "✗";
                    chkLeadOff.className = !h.lead_off ? "h-check h-ok" : "h-check h-warn";
                }

                const valRec = document.getElementById('valRecStatus');
                const chkRec = document.getElementById('chkRec');
                if (valRec && chkRec) {
                    if (h.recording) {
                        valRec.innerText = `REC (${(h.record_count || 0).toLocaleString()})`;
                        valRec.style.color = "var(--neon-red)";
                        chkRec.innerText = "●";
                        chkRec.className = "h-check h-warn";
                    } else {
                        valRec.innerText = "STANDBY";
                        valRec.style.color = "var(--text-dim)";
                        chkRec.innerText = "○";
                        chkRec.className = "h-check h-ok";
                    }
                }

                const badgeH = document.getElementById('badgeHealth');
                if (h.healthy) {
                    badgeH.innerText = "● DATASET HEALTHY";
                    badgeH.className = "health-badge healthy";
                } else {
                    badgeH.innerText = "🔴 DATASET INVALID";
                    badgeH.className = "health-badge corrupted";
                }
            }

            if (data.dsp) {
                const btnF = document.getElementById('btnFilter');
                if (btnF) {
                    if (data.dsp === 'DSP:ON') {
                        btnF.innerHTML = '🛡️ Giảm Nhiễu: BẬT (F)';
                        btnF.style.borderColor = 'var(--neon-green)';
                        btnF.style.color = 'var(--neon-green)';
                        btnF.style.background = 'rgba(0, 255, 136, 0.15)';
                    } else {
                        btnF.innerHTML = '🛡️ Giảm Nhiễu: TẮT (F)';
                        btnF.style.borderColor = 'rgba(255, 153, 0, 0.4)';
                        btnF.style.color = 'var(--neon-orange)';
                        btnF.style.background = 'rgba(255, 153, 0, 0.15)';
                    }
                }
            }
        }, 40);

        // KẾT NỐI SSE THỜI GIAN THỰC
        let eventSource = null;
        function connectSSE() {
            if (eventSource) eventSource.close();
            eventSource = new EventSource('/stream');

            eventSource.onopen = function() {
                console.log("[SSE] Đã kết nối Web Visualizer thời gian thực");
            };

            eventSource.onmessage = function(event) {
                if (!event.data || event.data.trim() === "") return;
                try {
                    const data = JSON.parse(event.data);
                    rawHistory.push(data.raw); rawHistory.shift();
                    filtHistory.push(data.filt); filtHistory.shift();
                    envHistory.push(data.env); envHistory.shift();
                    baseHistory.push(data.base); baseHistory.shift();

                    if (data.env > maxFlexPeak) maxFlexPeak = data.env;
                    latestPacket = data;
                } catch (err) {
                    console.error("[JSON Parse Error]:", err);
                }
            };

            eventSource.onerror = function() {
                setTimeout(connectSSE, 1500);
            };
        }
        connectSSE();

        // GỬI LỆNH TỨC THÌ (ZERO-LATENCY HTTP CALL)
        function sendCmd(key) {
            console.log("[CMD SENT]", key);
            fetch(`/cmd?key=${encodeURIComponent(key)}`, { cache: 'no-store' })
                .then(r => r.json())
                .catch(e => console.error("[CMD ERR]", e));
        }

        function resetQC() {
            fetch('/reset', { cache: 'no-store' }).then(() => {
                const b = document.getElementById('badgeHealth');
                if (b) {
                    b.innerText = "● ĐÃ RESET QC";
                    b.className = "health-badge healthy";
                }
            });
        }

        let isRecording = false;
        function toggleRecord() {
            const btn = document.getElementById('btnRecord');
            if (!isRecording) {
                fetch('/record?action=start', { cache: 'no-store' })
                    .then(r => r.json())
                    .then(d => {
                        isRecording = true;
                        btn.classList.add('btn-active');
                        btn.innerHTML = '⏹️ Đang Ghi 2000 SPS...';
                    });
            } else {
                fetch('/record?action=stop', { cache: 'no-store' })
                    .then(r => r.json())
                    .then(d => {
                        isRecording = false;
                        btn.classList.remove('btn-active');
                        btn.innerHTML = '🔴 Ghi CSV (2000 SPS)';
                        alert(`Đã hoàn tất ghi file dataset 2000 SPS:\n${d.filename}\nTổng số mẫu: ${d.samples.toLocaleString()}`);
                    });
            }
        }

        window.addEventListener('keydown', function(e) {
            if (e.target.tagName === 'INPUT') return;
            const k = e.key.toLowerCase();
            if (k === 'c') sendCmd('c');
            else if (k === 'f') sendCmd('f');
            else if (k === '+' || k === '=') sendCmd('+');
            else if (k === '-' || k === '_') sendCmd('-');
            else if (k === 's') sendCmd('s');
        });
    </script>
</body>
</html>
"""

class VisualizerHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global recording, record_file, record_count
        global total_dropped_samples, total_samples_received, max_gap_us, clipped_sample_count
        parsed = urlparse(self.path)

        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))

        elif parsed.path == "/data":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(json.dumps(latest_data).encode("utf-8"))

        elif parsed.path == "/reset":
            total_dropped_samples = 0
            total_samples_received = 0
            max_gap_us = 500
            clipped_sample_count = 0
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"status":"reset_ok"}')

        elif parsed.path == "/cmd":
            qs = parse_qs(parsed.query)
            key = qs.get("key", [""])[0]
            success = False
            if key:
                with ser_lock:
                    if ser_instance and ser_instance.is_open:
                        try:
                            ser_instance.write(key.encode("utf-8"))
                            ser_instance.flush()
                            success = True
                        except Exception as e:
                            print(f"[!] Gửi lệnh '{key}' thất bại: {e}")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}' if success else b'{"status":"failed"}')

        elif parsed.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            client_q = queue.Queue(maxsize=10)
            with clients_lock:
                connected_queues.append(client_q)

            init_str = f"data: {json.dumps(latest_data)}\n\n"
            try:
                self.wfile.write(init_str.encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass

            try:
                while True:
                    try:
                        msg = client_q.get(timeout=1.5)
                        self.wfile.write(msg.encode("utf-8"))
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, Exception):
                pass
            finally:
                with clients_lock:
                    if client_q in connected_queues:
                        connected_queues.remove(client_q)

        elif parsed.path == "/record":
            qs = parse_qs(parsed.query)
            action = qs.get("action", [""])[0]
            resp = {}
            if action == "start":
                os.makedirs("data", exist_ok=True)
                fn = os.path.join("data", f"sEMG_2000SPS_{time.strftime('%Y%m%d_%H%M%S')}.csv")
                record_file = open(fn, "w", encoding="utf-8")
                # Header chuẩn 2000 SPS: Kênh 2 cố định chuẩn nghiên cứu y sinh
                record_file.write("sample_idx,timestamp_us,ch1_raw24,ch2_raw24,ch2_raw16,ch2_filtered16,lead_off\n")
                recording = True
                record_count = 0
                total_dropped_samples = 0
                max_gap_us = 500
                resp = {"status": "started", "filename": fn}
            elif action == "stop":
                recording = False
                fn = "N/A"
                if record_file:
                    fn = record_file.name
                    record_file.close()
                    record_file = None
                resp = {"status": "stopped", "filename": fn, "samples": record_count}

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

def main():
    t = threading.Thread(target=serial_worker, daemon=True)
    t.start()

    server_address = ("127.0.0.1", PORT_HTTP)
    httpd = ThreadingHTTPServer(server_address, VisualizerHTTPHandler)
    print(f"\n==================================================================")
    print(f"   [+] sEMG DUAL-STREAM VISUALIZER TỐC ĐỘ CAO SẴN SÀNG: http://localhost:{PORT_HTTP}")
    print(f"==================================================================\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Đang dừng visualizer...")
        httpd.server_close()

if __name__ == "__main__":
    main()
