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
DEFAULT_COM = sys.argv[1] if len(sys.argv) > 1 else "COM13"

# Trạng thái toàn cục
serial_status = "Đang kết nối..."
latest_data = {
    "raw": 0,
    "env": 0,
    "base": 0,
    "sens": "x1.00",
    "percent": 0,
    "status": "ĐANG KẾT NỐI...",
    "port": DEFAULT_COM,
    "connected": False,
    "timestamp": 0
}

clients_lock = threading.Lock()
connected_queues = []
ser_instance = None
recording = False
record_file = None
record_count = 0

def find_serial_port():
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        if p.device.upper() == DEFAULT_COM.upper():
            return p.device
    for p in ports:
        desc = (p.description or "").upper()
        if "CH34" in desc or "USB-SERIAL" in desc or "CP210" in desc or "UART" in desc:
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
                pass  # Bỏ bớt frame cũ nếu client đọc chậm

def serial_worker():
    global ser_instance, latest_data, recording, record_file, record_count, serial_status

    while True:
        port_name = find_serial_port()
        serial_status = f"Đang mở cổng {port_name}..."
        print(f"[*] Đang kết nối Serial: {port_name} @ {SERIAL_BAUD}...")

        try:
            ser = serial.Serial(port_name, SERIAL_BAUD, timeout=1)
            ser_instance = ser
            serial_status = f"Đã kết nối: {port_name}"
            print(f"[+] KẾT NỐI THÀNH CÔNG VỚI {port_name}! Đang truyền dữ liệu lên Web Visualizer...")
            
            while True:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue

                # Parse dòng định dạng từ ESP32-S3:
                # Raw:   1234 | Env: 820 | Base: 800 | x1.00 | Luc:[====      ]  20% | GONG NHE
                if "Raw:" in line and "Env:" in line:
                    try:
                        parts = [p.strip() for p in line.split("|")]
                        raw_val = 0
                        env_val = 0
                        base_val = 0
                        sensitivity_str = "x1.00"
                        percent_val = 0
                        status_val = "THA LONG"

                        for p in parts:
                            if "Raw:" in p:
                                raw_val = int(p.replace("Raw:", "").strip())
                            elif "Env:" in p:
                                env_val = int(p.replace("Env:", "").strip())
                            elif "Base:" in p:
                                base_val = int(p.replace("Base:", "").strip())
                            elif p.startswith("x") and len(p) <= 6:
                                sensitivity_str = p
                            elif "%" in p:
                                pct_idx = p.find("%")
                                num_str = p[:pct_idx].split()[-1]
                                percent_val = int(num_str)
                            elif any(k in p for k in ["THA LONG", "GONG NHE", "GONG VUA", "GONG MANH"]):
                                status_val = p

                        data_point = {
                            "raw": raw_val,
                            "env": env_val,
                            "base": base_val,
                            "sens": sensitivity_str,
                            "percent": percent_val,
                            "status": status_val,
                            "port": port_name,
                            "connected": True,
                            "timestamp": int(time.time() * 1000)
                        }

                        latest_data = data_point

                        # Ghi file CSV nếu đang bật ghi
                        if recording and record_file:
                            record_file.write(f"{data_point['timestamp']},{raw_val},{env_val},{base_val},{sensitivity_str},{percent_val},{status_val}\n")
                            record_count += 1
                            if record_count % 30 == 0:
                                record_file.flush()

                        broadcast_data(data_point)

                    except Exception as parse_err:
                        pass
        except Exception as e:
            serial_status = f"Lỗi cổng ({port_name}): {e}"
            print(f"[!] Lỗi Serial ({port_name}): {e}. Đang thử kết nối lại sau 2s...")
            time.sleep(2)

HTML_PAGE = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>sEMG Live Visualizer | ESP32-S3 + ADS1292R</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #07090e;
            --bg-card: rgba(15, 20, 32, 0.85);
            --border-card: rgba(255, 255, 255, 0.08);
            --neon-blue: #00f0ff;
            --neon-green: #00ff88;
            --neon-orange: #ff9900;
            --neon-red: #ff3366;
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
            padding: 24px;
        }

        .container { max-width: 1400px; margin: 0 auto; }

        /* HEADER */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 20px;
            padding: 16px 28px;
            margin-bottom: 24px;
            backdrop-filter: blur(20px);
        }

        .title-group { display: flex; align-items: center; gap: 16px; }
        .logo-pulse {
            width: 14px; height: 14px; border-radius: 50%;
            background: var(--neon-green);
            box-shadow: 0 0 16px var(--neon-green);
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.85); } }

        h1 { font-size: 1.35rem; font-weight: 800; letter-spacing: -0.02em; }
        .subtitle { font-size: 0.85rem; color: var(--text-dim); margin-top: 2px; }

        .btn-group { display: flex; gap: 10px; align-items: center; }
        .btn {
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid var(--border-card);
            color: var(--text-main);
            padding: 8px 16px;
            border-radius: 12px;
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .btn:hover { background: rgba(0, 240, 255, 0.15); border-color: var(--neon-blue); }
        .btn-active { background: rgba(255, 51, 102, 0.25) !important; border-color: var(--neon-red) !important; color: #ff6b8b !important; }

        .port-pill {
            font-family: var(--font-mono);
            font-size: 0.8rem;
            padding: 5px 12px;
            border-radius: 20px;
            background: rgba(0, 255, 136, 0.1);
            color: var(--neon-green);
            border: 1px solid rgba(0, 255, 136, 0.3);
        }

        /* GRID CHÍNH */
        .main-grid {
            display: grid;
            grid-template-columns: 2.2fr 1fr;
            gap: 24px;
        }
        @media (max-width: 1000px) {
            .main-grid { grid-template-columns: 1fr; }
        }

        /* CARD */
        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 20px;
            padding: 22px;
            backdrop-filter: blur(20px);
            margin-bottom: 24px;
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 14px;
        }
        .card-title { font-size: 0.92rem; font-weight: 700; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.05em; }

        /* CANVAS OSCILLOSCOPE */
        canvas {
            width: 100%;
            height: 200px;
            border-radius: 14px;
            background: rgba(5, 8, 14, 0.95);
            display: block;
        }

        /* GAUGE & STATS SIDEBAR */
        .gauge-wrapper {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 16px 0;
            text-align: center;
        }

        .gauge-circle {
            position: relative;
            width: 220px;
            height: 220px;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .gauge-circle svg {
            transform: rotate(-90deg);
            width: 100%;
            height: 100%;
        }

        .gauge-bg { fill: none; stroke: rgba(255, 255, 255, 0.08); stroke-width: 16; }
        .gauge-fill {
            fill: none;
            stroke: var(--neon-green);
            stroke-width: 16;
            stroke-linecap: round;
            stroke-dasharray: 565;
            stroke-dashoffset: 565;
            transition: stroke-dashoffset 0.08s ease, stroke 0.2s ease;
        }

        .gauge-inner-val {
            position: absolute;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .percent-number { font-size: 3.2rem; font-weight: 800; font-family: var(--font-mono); line-height: 1; }
        .percent-unit { font-size: 0.85rem; color: var(--text-dim); font-weight: 600; margin-top: 4px; }

        .status-badge {
            margin-top: 18px;
            padding: 8px 24px;
            border-radius: 30px;
            font-size: 1.1rem;
            font-weight: 800;
            letter-spacing: 0.05em;
            background: rgba(0, 255, 136, 0.15);
            color: var(--neon-green);
            border: 1px solid rgba(0, 255, 136, 0.3);
            transition: all 0.2s;
        }

        /* METRIC CARDS ROW */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            margin-top: 16px;
        }
        .stat-item {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-card);
            border-radius: 14px;
            padding: 12px 8px;
            text-align: center;
        }
        .stat-name { font-size: 0.72rem; color: var(--text-dim); margin-bottom: 6px; font-weight: 600; }
        .stat-val { font-family: var(--font-mono); font-size: 1.15rem; font-weight: 700; }

        .keys-hint {
            margin-top: 18px;
            font-size: 0.78rem;
            color: var(--text-dim);
            line-height: 1.6;
            text-align: center;
        }
        kbd {
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 6px;
            padding: 2px 6px;
            font-family: var(--font-mono);
            font-size: 0.75rem;
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
                    <h1>sEMG BIO-SIGNAL REAL-TIME MONITOR</h1>
                    <div class="subtitle">ESP32-S3 &bull; ADS1292R 24-bit Front-End &bull; 1000 SPS (Baud 115200)</div>
                </div>
            </div>
            <div class="btn-group">
                <span class="port-pill" id="lblPortPill">COM13</span>
                <button class="btn" onclick="sendCommand('c')">⚡ Cân Chỉnh (C)</button>
                <button class="btn" onclick="sendCommand('+')">➕ Tăng Nhạy (+)</button>
                <button class="btn" onclick="sendCommand('-')">➖ Giảm Nhạy (-)</button>
                <button class="btn" id="btnRecord" onclick="toggleRecord()">🔴 Ghi CSV</button>
            </div>
        </header>

        <!-- MAIN GRID -->
        <div class="main-grid">
            <!-- CỘT BIỂU ĐỒ SÓNG -->
            <div>
                <!-- SÓNG RAW OSCILLOSCOPE -->
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">1. Tín hiệu thô sEMG (Raw ADC)</span>
                        <span id="txtRawVal" style="font-family: var(--font-mono); color: var(--neon-blue); font-weight: 700;">Raw: 0</span>
                    </div>
                    <canvas id="canvasRaw"></canvas>
                </div>

                <!-- SÓNG ENVELOPE (LỰC CO CƠ) -->
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">2. Đường bao hình lực cơ (Envelope & Baseline)</span>
                        <span id="txtEnvVal" style="font-family: var(--font-mono); color: var(--neon-green); font-weight: 700;">Env: 0 | Base: 0</span>
                    </div>
                    <canvas id="canvasEnv"></canvas>
                </div>
            </div>

            <!-- CỘT ĐỒNG HỒ ĐO LỰC (GAUGE) -->
            <div>
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">Lực Co Cơ Bắp Tay (MVC %)</span>
                        <span id="lblSensPill" style="font-family: var(--font-mono); color: var(--neon-blue); font-size: 0.85rem; font-weight: 700;">x1.00</span>
                    </div>
                    <div class="gauge-wrapper">
                        <div class="gauge-circle">
                            <svg viewBox="0 0 200 200">
                                <circle class="gauge-bg" cx="100" cy="100" r="90"></circle>
                                <circle class="gauge-fill" id="gaugeProgress" cx="100" cy="100" r="90"></circle>
                            </svg>
                            <div class="gauge-inner-val">
                                <span class="percent-number" id="lblPercent">0</span>
                                <span class="percent-unit">PHẦN TRĂM (%)</span>
                            </div>
                        </div>

                        <div class="status-badge" id="lblStatus">ĐANG KẾT NỐI...</div>
                    </div>

                    <!-- THÔNG SỐ ĐO NHANH -->
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
                            <div class="stat-name">Đỉnh Gồng</div>
                            <div class="stat-val" id="statPeak" style="color: var(--neon-orange);">0</div>
                        </div>
                    </div>

                    <div class="keys-hint">
                        Phím tắt: <kbd>C</kbd> cân chỉnh zero &bull; <kbd>+</kbd> tăng nhạy &bull; <kbd>-</kbd> giảm nhạy
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const MAX_POINTS = 300;
        const rawHistory = new Array(MAX_POINTS).fill(0);
        const envHistory = new Array(MAX_POINTS).fill(0);
        const baseHistory = new Array(MAX_POINTS).fill(0);

        const canvasRaw = document.getElementById('canvasRaw');
        const ctxRaw = canvasRaw.getContext('2d');
        const canvasEnv = document.getElementById('canvasEnv');
        const ctxEnv = canvasEnv.getContext('2d');

        function resizeCanvases() {
            if (canvasRaw.parentElement) {
                canvasRaw.width = canvasRaw.parentElement.clientWidth - 44;
                canvasRaw.height = 180;
                canvasEnv.width = canvasEnv.parentElement.clientWidth - 44;
                canvasEnv.height = 180;
            }
        }
        window.addEventListener('resize', resizeCanvases);
        resizeCanvases();

        const gaugeCircle = document.getElementById('gaugeProgress');
        const circumference = 2 * Math.PI * 90;
        gaugeCircle.style.strokeDasharray = circumference;

        function setGauge(pct) {
            pct = Math.max(0, Math.min(100, pct));
            const offset = circumference - (pct / 100) * circumference;
            gaugeCircle.style.strokeDashoffset = offset;

            if (pct >= 60) {
                gaugeCircle.style.stroke = 'var(--neon-red)';
            } else if (pct >= 25) {
                gaugeCircle.style.stroke = 'var(--neon-orange)';
            } else if (pct >= 10) {
                gaugeCircle.style.stroke = 'var(--neon-blue)';
            } else {
                gaugeCircle.style.stroke = 'var(--neon-green)';
            }
        }

        let maxFlexPeak = 1000;

        function drawWaveforms() {
            // 1. Raw Canvas
            const wR = canvasRaw.width;
            const hR = canvasRaw.height;
            ctxRaw.fillStyle = 'rgba(5, 8, 14, 0.95)';
            ctxRaw.fillRect(0, 0, wR, hR);

            ctxRaw.strokeStyle = 'rgba(255, 255, 255, 0.05)';
            ctxRaw.lineWidth = 1;
            for (let y = 30; y < hR; y += 30) {
                ctxRaw.beginPath(); ctxRaw.moveTo(0, y); ctxRaw.lineTo(wR, y); ctxRaw.stroke();
            }

            let minR = Math.min(...rawHistory);
            let maxR = Math.max(...rawHistory);
            let rangeR = Math.max(2000, maxR - minR);
            let midR = (maxR + minR) / 2;

            ctxRaw.strokeStyle = '#00f0ff';
            ctxRaw.lineWidth = 2;
            ctxRaw.shadowColor = '#00f0ff';
            ctxRaw.shadowBlur = 6;
            ctxRaw.beginPath();
            for (let i = 0; i < MAX_POINTS; i++) {
                const x = (i / (MAX_POINTS - 1)) * wR;
                const normalized = (rawHistory[i] - midR) / rangeR;
                const y = hR / 2 - normalized * (hR * 0.42);
                if (i === 0) ctxRaw.moveTo(x, y); else ctxRaw.lineTo(x, y);
            }
            ctxRaw.stroke();
            ctxRaw.shadowBlur = 0;

            // 2. Envelope Canvas
            const wE = canvasEnv.width;
            const hE = canvasEnv.height;
            ctxEnv.fillStyle = 'rgba(5, 8, 14, 0.95)';
            ctxEnv.fillRect(0, 0, wE, hE);

            ctxEnv.strokeStyle = 'rgba(255, 255, 255, 0.05)';
            for (let y = 30; y < hE; y += 30) {
                ctxEnv.beginPath(); ctxEnv.moveTo(0, y); ctxEnv.lineTo(wE, y); ctxEnv.stroke();
            }

            let maxE = Math.max(1500, ...envHistory);

            // Baseline (xanh dương đứt khúc)
            ctxEnv.strokeStyle = 'rgba(0, 240, 255, 0.4)';
            ctxEnv.lineWidth = 1.5;
            ctxEnv.setLineDash([4, 4]);
            ctxEnv.beginPath();
            for (let i = 0; i < MAX_POINTS; i++) {
                const x = (i / (MAX_POINTS - 1)) * wE;
                const y = hE - (baseHistory[i] / maxE) * (hE * 0.85) - 10;
                if (i === 0) ctxEnv.moveTo(x, y); else ctxEnv.lineTo(x, y);
            }
            ctxEnv.stroke();
            ctxEnv.setLineDash([]);

            // Envelope (xanh neon)
            ctxEnv.strokeStyle = '#00ff88';
            ctxEnv.lineWidth = 2.5;
            ctxEnv.shadowColor = '#00ff88';
            ctxEnv.shadowBlur = 8;
            ctxEnv.beginPath();
            for (let i = 0; i < MAX_POINTS; i++) {
                const x = (i / (MAX_POINTS - 1)) * wE;
                const y = hE - (envHistory[i] / maxE) * (hE * 0.85) - 10;
                if (i === 0) ctxEnv.moveTo(x, y); else ctxEnv.lineTo(x, y);
            }
            ctxEnv.stroke();
            ctxEnv.shadowBlur = 0;

            requestAnimationFrame(drawWaveforms);
        }
        requestAnimationFrame(drawWaveforms);

        // KẾT NỐI SSE TỰ ĐỘNG RECONNECT
        let eventSource = null;
        function connectSSE() {
            if (eventSource) {
                eventSource.close();
            }
            eventSource = new EventSource('/stream');

            eventSource.onopen = function() {
                console.log("[SSE] Đã kết nối với Web Server");
            };

            eventSource.onmessage = function(event) {
                if (!event.data || event.data.trim() === "") return;
                try {
                    const data = JSON.parse(event.data);

                    rawHistory.push(data.raw);
                    rawHistory.shift();
                    envHistory.push(data.env);
                    envHistory.shift();
                    baseHistory.push(data.base);
                    baseHistory.shift();

                    if (data.env > maxFlexPeak) maxFlexPeak = data.env;

                    document.getElementById('txtRawVal').innerText = `Raw: ${data.raw.toLocaleString()}`;
                    document.getElementById('txtEnvVal').innerText = `Env: ${data.env.toLocaleString()} | Base: ${data.base.toLocaleString()}`;
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
                } catch(e) {}
            };

            eventSource.onerror = function() {
                console.log("[SSE] Mất kết nối, tự kết nối lại sau 2s...");
                eventSource.close();
                setTimeout(connectSSE, 2000);
            };
        }
        connectSSE();

        function sendCommand(cmd) {
            fetch('/cmd?key=' + encodeURIComponent(cmd));
        }

        window.addEventListener('keydown', (e) => {
            if (e.key === 'c' || e.key === 'C') sendCommand('c');
            if (e.key === '+') sendCommand('+');
            if (e.key === '-') sendCommand('-');
        });

        let isRecording = false;
        function toggleRecord() {
            const btn = document.getElementById('btnRecord');
            isRecording = !isRecording;
            if (isRecording) {
                fetch('/record?action=start');
                btn.innerText = '⏹️ Dừng Lưu CSV';
                btn.classList.add('btn-active');
            } else {
                fetch('/record?action=stop').then(r => r.json()).then(data => {
                    alert('Đã lưu file dữ liệu thành công:\\n' + data.filename + '\\nSố mẫu: ' + data.samples);
                });
                btn.innerText = '🔴 Ghi CSV';
                btn.classList.remove('btn-active');
            }
        }
    </script>
</body>
</html>
"""

class RobustRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global ser_instance, recording, record_file, record_count
        parsed = urlparse(self.path)

        if parsed.path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))

        elif parsed.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            client_q = queue.Queue(maxsize=100)
            with clients_lock:
                connected_queues.append(client_q)

            # Gửi ngay trạng thái hiện tại
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
                        # Gửi comment SSE ping để giữ kết nối không bị timeout
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, Exception):
                pass
            finally:
                with clients_lock:
                    if client_q in connected_queues:
                        connected_queues.remove(client_q)

        elif parsed.path == "/cmd":
            qs = parse_qs(parsed.query)
            key = qs.get("key", [""])[0]
            if key and ser_instance and ser_instance.is_open:
                try:
                    ser_instance.write(key.encode("utf-8"))
                except Exception:
                    pass
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")

        elif parsed.path == "/record":
            qs = parse_qs(parsed.query)
            action = qs.get("action", [""])[0]
            resp = {}
            if action == "start":
                os.makedirs("data", exist_ok=True)
                fn = os.path.join("data", f"emg_recording_{time.strftime('%Y%m%d_%H%M%S')}.csv")
                record_file = open(fn, "w", encoding="utf-8")
                record_file.write("timestamp_ms,raw,env,base,sens,percent,status\n")
                recording = True
                record_count = 0
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
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Ẩn bớt log truy cập HTTP liên tục
        pass

def main():
    # 1. Khởi động luồng đọc Serial nền
    t = threading.Thread(target=serial_worker, daemon=True)
    t.start()

    # 2. Khởi động Threading Web Server (xử lý đa luồng đồng thời)
    server_address = ("127.0.0.1", PORT_HTTP)
    
    # Cho phép tái sử dụng port ngay lập tức nếu vừa bị tắt
    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer(server_address, RobustRequestHandler)
    
    url = f"http://localhost:{PORT_HTTP}"
    print(f"\n==================================================================")
    print(f"   [+] sEMG REAL-TIME WEB VISUALIZER SẴN SÀNG: {url}")
    print(f"==================================================================\n")

    # Mở trình duyệt web tự động
    time.sleep(1)
    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Đang tắt Visualizer...")
        httpd.server_close()

if __name__ == "__main__":
    main()
