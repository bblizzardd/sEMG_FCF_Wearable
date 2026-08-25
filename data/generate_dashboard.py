import sys
import json
import numpy as np
import pandas as pd

import os

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
csv_file = os.path.join(BASE_DIR, 'data.csv') if os.path.exists(os.path.join(BASE_DIR, 'data.csv')) else 'data.csv'

df = pd.read_csv(csv_file)
df['time_s'] = ((df['timestamp_ms'] - df['timestamp_ms'].iloc[0]) / 1000.0).round(3)
df['acc_mag'] = (df['acc_x']**2 + df['acc_y']**2 + df['acc_z']**2)**0.5
df['gyro_mag'] = (df['gyro_x']**2 + df['gyro_y']**2 + df['gyro_z']**2)**0.5

# Dynamic calculations
num_samples = len(df)
duration_s = float(df['time_s'].iloc[-1])
dt_ms = float(df['timestamp_ms'].diff().median())
fs = 1000.0 / dt_ms if dt_ms > 0 else 43.48

# Count button events
is_btn = df['button'].values
diffs = np.diff(np.concatenate(([0], is_btn, [0])))
btn_events = int(np.sum(diffs == 1))
btn_samples = int(np.sum(is_btn == 1))
btn_pct = (btn_samples / num_samples) * 100.0

temp_min = float(df['temp'].min())
temp_max = float(df['temp'].max())
max_acc = float(df['acc_mag'].max())

# Prepare JSON data
data_dict = {
    "time": df['time_s'].tolist(),
    "timestamp_ms": df['timestamp_ms'].tolist(),
    "acc_x": df['acc_x'].round(4).tolist(),
    "acc_y": df['acc_y'].round(4).tolist(),
    "acc_z": df['acc_z'].round(4).tolist(),
    "acc_mag": df['acc_mag'].round(4).tolist(),
    "gyro_x": df['gyro_x'].round(4).tolist(),
    "gyro_y": df['gyro_y'].round(4).tolist(),
    "gyro_z": df['gyro_z'].round(4).tolist(),
    "gyro_mag": df['gyro_mag'].round(4).tolist(),
    "temp": df['temp'].round(2).tolist(),
    "button": df['button'].tolist()
}

json_data_str = json.dumps(data_dict)

# Table rows dynamic generation
channels = [
    ('acc_x', 'm/s²'),
    ('acc_y', 'm/s²'),
    ('acc_z', 'm/s²'),
    ('acc_mag', 'm/s²'),
    ('gyro_x', 'rad/s'),
    ('gyro_y', 'rad/s'),
    ('gyro_z', 'rad/s'),
    ('gyro_mag', 'rad/s'),
    ('temp', '°C'),
    ('button', '0/1')
]

table_rows_html = ""
for col, unit in channels:
    mean_v = df[col].mean()
    std_v = df[col].std()
    min_v = df[col].min()
    med_v = df[col].median()
    max_v = df[col].max()
    table_rows_html += f"""
    <tr>
        <td><strong>{col}</strong></td>
        <td>{unit}</td>
        <td>{mean_v:.4f}</td>
        <td>{std_v:.4f}</td>
        <td>{min_v:.4f}</td>
        <td>{med_v:.4f}</td>
        <td>{max_v:.4f}</td>
    </tr>"""

html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard Phân Tích Dữ Liệu Cảm Biến IMU & Edge AI</title>
    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <!-- Plotly.js -->
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <style>
        :root {{
            --bg: #0b0f19;
            --card-bg: rgba(22, 30, 49, 0.75);
            --card-border: rgba(255, 255, 255, 0.08);
            --text: #f1f5f9;
            --text-muted: #94a3b8;
            --primary: #38bdf8;
            --accent-green: #34d399;
            --accent-amber: #fbbf24;
            --accent-red: #f87171;
            --accent-purple: #c084fc;
            --accent-pink: #f472b6;
        }}
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Plus Jakarta Sans', sans-serif;
            background: var(--bg);
            color: var(--text);
            padding: 24px;
            min-height: 100vh;
            background-image: 
                radial-gradient(at 0% 0%, rgba(56, 189, 248, 0.12) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(192, 132, 252, 0.1) 0px, transparent 50%);
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
            margin-bottom: 24px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--card-border);
        }}
        .header-title h1 {{
            font-size: 26px;
            font-weight: 800;
            background: linear-gradient(135deg, #38bdf8 0%, #a855f7 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .badge {{
            font-size: 11px;
            font-weight: 600;
            padding: 4px 10px;
            border-radius: 20px;
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.3);
            text-transform: uppercase;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .stat-card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 18px 20px;
            backdrop-filter: blur(12px);
            transition: transform 0.2s, border-color 0.2s;
        }}
        .stat-card:hover {{
            transform: translateY(-2px);
            border-color: rgba(56, 189, 248, 0.3);
        }}
        .stat-label {{
            font-size: 13px;
            color: var(--text-muted);
            margin-bottom: 6px;
            font-weight: 500;
        }}
        .stat-value {{
            font-size: 24px;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
        }}
        .stat-sub {{
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 4px;
        }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 18px;
            padding: 22px;
            margin-bottom: 24px;
            backdrop-filter: blur(12px);
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }}
        .card-title {{
            font-size: 18px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .grid-2col {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        @media (max-width: 900px) {{
            .grid-2col {{ grid-template-columns: 1fr; }}
        }}
        .plot-container {{
            width: 100%;
            height: 480px;
        }}
        .plot-container-sm {{
            width: 100%;
            height: 380px;
        }}
        .btn-controls {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .btn {{
            background: rgba(255, 255, 255, 0.05);
            color: var(--text);
            border: 1px solid var(--card-border);
            padding: 6px 14px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .btn:hover {{
            background: rgba(56, 189, 248, 0.2);
            border-color: var(--primary);
        }}
        .table-wrap {{
            overflow-x: auto;
            margin-top: 10px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            font-family: 'JetBrains Mono', monospace;
        }}
        th, td {{
            padding: 10px 14px;
            text-align: left;
            border-bottom: 1px solid var(--card-border);
        }}
        th {{
            color: var(--text-muted);
            font-weight: 600;
            background: rgba(255, 255, 255, 0.02);
        }}
        tr:hover td {{
            background: rgba(255, 255, 255, 0.03);
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-title">
                <h1>📊 IMU & Edge AI Sensor Analytics</h1>
                <span class="badge">data.csv ({num_samples:,} mẫu)</span>
            </div>
            <div class="btn-controls">
                <button class="btn" onclick="resetZoom()">🔄 Reset Toàn Bộ</button>
                <button class="btn" onclick="zoomFirstHalf()">🎯 Nửa Đầu (0 - {duration_s/2:.1f}s)</button>
                <button class="btn" onclick="zoomSecondHalf()">🛑 Nửa Sau ({duration_s/2:.1f}s - {duration_s:.1f}s)</button>
            </div>
        </header>

        <!-- KPI Cards -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Tổng Mẫu Dữ Liệu</div>
                <div class="stat-value" style="color: var(--primary);">{num_samples:,}</div>
                <div class="stat-sub">Khoảng thời gian: {duration_s:.2f} s</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Tần Số Lấy Mẫu (Fs)</div>
                <div class="stat-value" style="color: var(--accent-green);">{fs:.2f} Hz</div>
                <div class="stat-sub">Chu kỳ Δt = {dt_ms:.1f} ms</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Số Lần Nhấn Nút</div>
                <div class="stat-value" style="color: var(--accent-pink);">{btn_events} Sự kiện</div>
                <div class="stat-sub">{btn_samples} mẫu tích cực ({btn_pct:.2f}%)</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Nhiệt Độ Hoạt Động</div>
                <div class="stat-value" style="color: var(--accent-purple);">{temp_min:.2f}°C - {temp_max:.2f}°C</div>
                <div class="stat-sub">ΔT = {temp_max - temp_min:+.2f}°C</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Gia Tốc Cực Đại |Acc|</div>
                <div class="stat-value" style="color: var(--accent-amber);">{max_acc:.2f} m/s²</div>
                <div class="stat-sub">Độ lớn vector cực đại</div>
            </div>
        </div>

        <!-- Main Time-Series Charts -->
        <div class="card">
            <div class="card-header">
                <div class="card-title">📈 Tín Hiệu Thời Gian (Gia Tốc, Vận Tốc Góc, Nhiệt Độ, Nút Bấm)</div>
                <span style="font-size:12px; color: var(--text-muted);">Tương tác: Kéo chuột để phóng to, bấm đôi để reset</span>
            </div>
            <div id="chart-synced" class="plot-container" style="height: 740px;"></div>
        </div>

        <!-- 2 Column Layout: 3D Trajectory & FFT Spectrum -->
        <div class="grid-2col">
            <div class="card">
                <div class="card-header">
                    <div class="card-title">🌐 Quỹ Đạo Gia Tốc Không Gian 3D</div>
                </div>
                <div id="chart-3d" class="plot-container-sm"></div>
            </div>
            <div class="card">
                <div class="card-header">
                    <div class="card-title">⚡ Phổ Tần Số FFT (Gia tốc & Vận tốc góc)</div>
                </div>
                <div id="chart-fft" class="plot-container-sm"></div>
            </div>
        </div>

        <!-- Summary Statistics Table -->
        <div class="card">
            <div class="card-header">
                <div class="card-title">📋 Bảng Thống Kê Chi Tiết Các Kênh Cảm Biến</div>
            </div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Kênh (Channel)</th>
                            <th>Đơn vị</th>
                            <th>Trung bình (Mean)</th>
                            <th>Độ lệch chuẩn (Std)</th>
                            <th>Giá trị Min</th>
                            <th>Trung vị (Median)</th>
                            <th>Giá trị Max</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_rows_html}
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        const rawData = {json_data_str};
        
        // 1. Synced Subplots using Plotly
        function renderSyncedChart() {{
            const time = rawData.time;
            
            // Traces for Accelerometer
            const traceAccX = {{ x: time, y: rawData.acc_x, name: 'Acc X (m/s²)', line: {{ color: '#38bdf8', width: 1.5 }}, xaxis: 'x', yaxis: 'y1' }};
            const traceAccY = {{ x: time, y: rawData.acc_y, name: 'Acc Y (m/s²)', line: {{ color: '#34d399', width: 1.5 }}, xaxis: 'x', yaxis: 'y1' }};
            const traceAccZ = {{ x: time, y: rawData.acc_z, name: 'Acc Z (m/s²)', line: {{ color: '#fbbf24', width: 1.5 }}, xaxis: 'x', yaxis: 'y1' }};
            const traceAccMag = {{ x: time, y: rawData.acc_mag, name: '|Acc| Total', line: {{ color: '#f87171', width: 2, dash: 'dot' }}, xaxis: 'x', yaxis: 'y1' }};
            
            // Traces for Gyroscope
            const traceGyroX = {{ x: time, y: rawData.gyro_x, name: 'Gyro X (rad/s)', line: {{ color: '#38bdf8', width: 1.5 }}, xaxis: 'x', yaxis: 'y2' }};
            const traceGyroY = {{ x: time, y: rawData.gyro_y, name: 'Gyro Y (rad/s)', line: {{ color: '#34d399', width: 1.5 }}, xaxis: 'x', yaxis: 'y2' }};
            const traceGyroZ = {{ x: time, y: rawData.gyro_z, name: 'Gyro Z (rad/s)', line: {{ color: '#fbbf24', width: 1.5 }}, xaxis: 'x', yaxis: 'y2' }};
            const traceGyroMag = {{ x: time, y: rawData.gyro_mag, name: '|Gyro| Total', line: {{ color: '#f87171', width: 2, dash: 'dot' }}, xaxis: 'x', yaxis: 'y2' }};
            
            // Trace Temperature
            const traceTemp = {{ x: time, y: rawData.temp, name: 'Nhiệt độ (°C)', line: {{ color: '#c084fc', width: 2 }}, xaxis: 'x', yaxis: 'y3' }};
            
            // Trace Button
            const traceBtn = {{ x: time, y: rawData.button, name: 'Nút nhấn (0/1)', line: {{ color: '#f472b6', width: 2, shape: 'hv' }}, fill: 'tozeroy', fillcolor: 'rgba(244, 114, 182, 0.25)', xaxis: 'x', yaxis: 'y4' }};
            
            // Create shapes for button press regions
            const shapes = [];
            let inBtn = false, startT = 0;
            for(let i=0; i<rawData.button.length; i++) {{
                if (rawData.button[i] === 1 && !inBtn) {{
                    inBtn = true;
                    startT = time[i];
                }} else if (rawData.button[i] === 0 && inBtn) {{
                    inBtn = false;
                    shapes.push({{
                        type: 'rect',
                        xref: 'x',
                        yref: 'paper',
                        x0: startT,
                        x1: time[i-1],
                        y0: 0,
                        y1: 1,
                        fillcolor: 'rgba(244, 114, 182, 0.15)',
                        line: {{ width: 0 }}
                    }});
                }}
            }}

            const layout = {{
                grid: {{ rows: 4, columns: 1, pattern: 'independent', roworder: 'top to bottom' }},
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'rgba(15, 23, 42, 0.6)',
                font: {{ color: '#cbd5e1', family: 'Plus Jakarta Sans' }},
                margin: {{ l: 60, r: 30, t: 20, b: 40 }},
                shapes: shapes,
                xaxis: {{
                    title: 'Thời gian (giây)',
                    gridcolor: 'rgba(255, 255, 255, 0.06)',
                    showgrid: true,
                    anchor: 'y4'
                }},
                yaxis: {{
                    title: 'Gia tốc (m/s²)',
                    gridcolor: 'rgba(255, 255, 255, 0.06)',
                    domain: [0.74, 1.0]
                }},
                yaxis2: {{
                    title: 'Vận tốc góc (rad/s)',
                    gridcolor: 'rgba(255, 255, 255, 0.06)',
                    domain: [0.46, 0.70]
                }},
                yaxis3: {{
                    title: 'Nhiệt độ (°C)',
                    gridcolor: 'rgba(255, 255, 255, 0.06)',
                    domain: [0.22, 0.42]
                }},
                yaxis4: {{
                    title: 'Nút nhấn',
                    gridcolor: 'rgba(255, 255, 255, 0.06)',
                    domain: [0.0, 0.18],
                    tickvals: [0, 1],
                    ticktext: ['Nhả (0)', 'Nhấn (1)']
                }},
                legend: {{
                    orientation: 'h',
                    x: 0,
                    y: 1.08,
                    font: {{ size: 11 }}
                }}
            }};

            Plotly.newPlot('chart-synced', [traceAccX, traceAccY, traceAccZ, traceAccMag, traceGyroX, traceGyroY, traceGyroZ, traceGyroMag, traceTemp, traceBtn], layout, {{ responsive: true }});
        }}

        // 2. 3D Acceleration Scatter Plot
        function render3DChart() {{
            const trace3d = {{
                type: 'scatter3d',
                mode: 'lines+markers',
                x: rawData.acc_x,
                y: rawData.acc_y,
                z: rawData.acc_z,
                line: {{ color: 'rgba(148, 163, 184, 0.4)', width: 1.5 }},
                marker: {{
                    size: 3.5,
                    color: rawData.time,
                    colorscale: 'Viridis',
                    colorbar: {{ title: 'Thời gian (s)', len: 0.8, x: 1.05 }}
                }}
            }};

            const layout3d = {{
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent',
                font: {{ color: '#cbd5e1' }},
                margin: {{ l: 0, r: 0, t: 0, b: 0 }},
                scene: {{
                    xaxis: {{ title: 'Acc X', gridcolor: 'rgba(255,255,255,0.1)' }},
                    yaxis: {{ title: 'Acc Y', gridcolor: 'rgba(255,255,255,0.1)' }},
                    zaxis: {{ title: 'Acc Z', gridcolor: 'rgba(255,255,255,0.1)' }},
                    bgcolor: 'rgba(15, 23, 42, 0.6)'
                }}
            }};

            Plotly.newPlot('chart-3d', [trace3d], layout3d, {{ responsive: true }});
        }}

        // 3. FFT Spectrum Calculation and Plot
        function renderFFTChart() {{
            const dt = {dt_ms} / 1000.0;
            const fs = {fs};
            const N = rawData.acc_mag.length;
            
            const meanAcc = rawData.acc_mag.reduce((a,b)=>a+b,0)/N;
            const meanGyro = rawData.gyro_mag.reduce((a,b)=>a+b,0)/N;
            
            const accSignal = rawData.acc_mag.map(v => v - meanAcc);
            const gyroSignal = rawData.gyro_mag.map(v => v - meanGyro);
            
            const numFreqs = Math.min(256, Math.floor(N / 2));
            const freqs = [];
            const accAmps = [];
            const gyroAmps = [];

            for(let k=0; k<numFreqs; k++) {{
                const freq = (k * fs) / N;
                freqs.push(freq);
                
                let reAcc = 0, imAcc = 0;
                let reGyro = 0, imGyro = 0;
                for(let n=0; n<N; n++) {{
                    const phi = (2 * Math.PI * k * n) / N;
                    const cosVal = Math.cos(phi);
                    const sinVal = Math.sin(phi);
                    reAcc += accSignal[n] * cosVal;
                    imAcc -= accSignal[n] * sinVal;
                    reGyro += gyroSignal[n] * cosVal;
                    imGyro -= gyroSignal[n] * sinVal;
                }}
                accAmps.push((Math.sqrt(reAcc*reAcc + imAcc*imAcc) * 2) / N);
                gyroAmps.push((Math.sqrt(reGyro*reGyro + imGyro*imGyro) * 2) / N);
            }}

            const traceAccFFT = {{ x: freqs, y: accAmps, name: 'Phổ Gia Tốc (|Acc| AC)', line: {{ color: '#38bdf8', width: 1.8 }} }};
            const traceGyroFFT = {{ x: freqs, y: gyroAmps, name: 'Phổ Vận Tốc Góc (|Gyro| AC)', line: {{ color: '#f87171', width: 1.8 }} }};

            const layoutFFT = {{
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'rgba(15, 23, 42, 0.6)',
                font: {{ color: '#cbd5e1' }},
                margin: {{ l: 50, r: 20, t: 20, b: 40 }},
                xaxis: {{ title: 'Tần số (Hz)', range: [0, fs/2], gridcolor: 'rgba(255,255,255,0.06)' }},
                yaxis: {{ title: 'Biên độ', gridcolor: 'rgba(255,255,255,0.06)' }},
                legend: {{ orientation: 'h', y: 1.15, font: {{ size: 11 }} }}
            }};

            Plotly.newPlot('chart-fft', [traceAccFFT, traceGyroFFT], layoutFFT, {{ responsive: true }});
        }}

        // Controls
        function resetZoom() {{
            Plotly.relayout('chart-synced', {{ 'xaxis.autorange': true }});
        }}
        function zoomFirstHalf() {{
            Plotly.relayout('chart-synced', {{ 'xaxis.range': [0, {duration_s/2:.2f}] }});
        }}
        function zoomSecondHalf() {{
            Plotly.relayout('chart-synced', {{ 'xaxis.range': [{duration_s/2:.2f}, {duration_s:.2f}] }});
        }}

        // Initialize All Charts
        window.addEventListener('DOMContentLoaded', () => {{
            renderSyncedChart();
            render3DChart();
            renderFFTChart();
        }});
    </script>
</body>
</html>
"""

output_file = os.path.join(BASE_DIR, 'dashboard.html')
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"{output_file} generated successfully for {num_samples} samples!")
