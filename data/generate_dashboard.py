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
df['time_s'] = ((df['timestamp_ms'] - df['timestamp_ms'].iloc[0]) / 1000.0).round(4)
df['acc_mag'] = (df['acc_x']**2 + df['acc_y']**2 + df['acc_z']**2)**0.5
df['gyro_mag'] = (df['gyro_x']**2 + df['gyro_y']**2 + df['gyro_z']**2)**0.5

# Dynamic calculations
num_samples = len(df)
duration_s = float(df['time_s'].iloc[-1])
dt_ms = float(df['timestamp_ms'].diff().median())
fs = 1000.0 / dt_ms if dt_ms > 0 else 100.0

# Identify Button Press Events (Starts and Ends)
is_btn = df['button'].values
diffs = np.diff(np.concatenate(([0], is_btn, [0])))
starts = np.where(diffs == 1)[0]
ends = np.where(diffs == -1)[0]

button_events_list = []
for idx, (s, e) in enumerate(zip(starts, ends), 1):
    t_start = float(df['time_s'].iloc[s])
    t_end = float(df['time_s'].iloc[min(e-1, len(df)-1)])
    dur = round(t_end - t_start, 3)
    button_events_list.append({
        "event_id": idx,
        "start_idx": int(s),
        "end_idx": int(e),
        "t_start": t_start,
        "t_end": t_end,
        "duration": dur
    })

btn_events = len(button_events_list)
btn_samples = int(np.sum(is_btn == 1))
btn_pct = (btn_samples / num_samples) * 100.0

temp_min = float(df['temp'].min())
temp_max = float(df['temp'].max())
max_acc = float(df['acc_mag'].max())
max_gyro = float(df['gyro_mag'].max())

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
    "button": df['button'].tolist(),
    "button_events": button_events_list
}

if 'roll' in df.columns and 'pitch' in df.columns:
    data_dict["roll"] = df['roll'].round(2).tolist()
    data_dict["pitch"] = df['pitch'].round(2).tolist()

json_data_str = json.dumps(data_dict)

# Table rows dynamic generation (Units: Acc -> g, Gyro -> °/s)
channels = [
    ('acc_x', 'g', 'Gia tốc trục X'),
    ('acc_y', 'g', 'Gia tốc trục Y'),
    ('acc_z', 'g', 'Gia tốc trục Z'),
    ('acc_mag', 'g', 'Độ lớn gia tốc toàn phần |Acc|'),
    ('gyro_x', '°/s', 'Vận tốc góc trục X'),
    ('gyro_y', '°/s', 'Vận tốc góc trục Y'),
    ('gyro_z', '°/s', 'Vận tốc góc trục Z'),
    ('gyro_mag', '°/s', 'Độ lớn vận tốc góc |Gyro|'),
]

if 'roll' in df.columns and 'pitch' in df.columns:
    channels.append(('roll', '°', 'Góc nghiêng Roll (Kalman Filter)'))
    channels.append(('pitch', '°', 'Góc nghiêng Pitch (Kalman Filter)'))

channels.append(('temp', '°C', 'Nhiệt độ cảm biến'))
channels.append(('button', '0/1', 'Trạng thái nút bấm'))

table_rows_html = ""
for col, unit, desc in channels:
    mean_v = df[col].mean()
    std_v = df[col].std()
    min_v = df[col].min()
    med_v = df[col].median()
    max_v = df[col].max()
    table_rows_html += f"""
    <tr>
        <td><strong>{col}</strong></td>
        <td><span style="color: var(--text-muted); font-size:11px;">{desc}</span></td>
        <td><code>{unit}</code></td>
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
    <title>IMU & Edge AI Sensor Analytics Dashboard (Đơn vị g & °/s)</title>
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <!-- Plotly.js -->
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <style>
        :root {{
            --bg: #090d16;
            --card-bg: rgba(19, 26, 43, 0.78);
            --card-border: rgba(255, 255, 255, 0.09);
            --card-hover-border: rgba(56, 189, 248, 0.35);
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #38bdf8;
            --axis-x: #38bdf8;
            --axis-y: #34d399;
            --axis-z: #fbbf24;
            --gyro-x: #fb923c;
            --gyro-y: #c084fc;
            --gyro-z: #f43f5e;
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
            padding: 20px;
            min-height: 100vh;
            background-image: 
                radial-gradient(circle at 10% 0%, rgba(56, 189, 248, 0.12) 0px, transparent 40%),
                radial-gradient(circle at 90% 90%, rgba(192, 132, 252, 0.09) 0px, transparent 40%);
        }}
        .container {{
            max-width: 1480px;
            margin: 0 auto;
        }}
        
        /* Header */
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
            margin-bottom: 20px;
            padding-bottom: 18px;
            border-bottom: 1px solid var(--card-border);
        }}
        .header-title h1 {{
            font-size: 24px;
            font-weight: 800;
            background: linear-gradient(135deg, #38bdf8 0%, #c084fc 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .badge {{
            font-size: 11px;
            font-weight: 600;
            padding: 4px 12px;
            border-radius: 20px;
            background: rgba(56, 189, 248, 0.12);
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.3);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        /* Navigation Tabs */
        .tabs-nav {{
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            background: rgba(15, 23, 42, 0.7);
            padding: 6px;
            border-radius: 14px;
            border: 1px solid var(--card-border);
            width: fit-content;
        }}
        .tab-btn {{
            background: transparent;
            color: var(--text-muted);
            border: none;
            padding: 9px 18px;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .tab-btn:hover {{
            color: var(--text);
            background: rgba(255, 255, 255, 0.06);
        }}
        .tab-btn.active {{
            background: linear-gradient(135deg, rgba(56, 189, 248, 0.25), rgba(192, 132, 252, 0.25));
            color: #fff;
            border: 1px solid rgba(56, 189, 248, 0.4);
            box-shadow: 0 4px 12px rgba(56, 189, 248, 0.15);
        }}

        /* Toolbar Controls */
        .toolbar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
            margin-bottom: 20px;
            background: var(--card-bg);
            padding: 12px 18px;
            border-radius: 14px;
            border: 1px solid var(--card-border);
        }}
        .toolbar-group {{
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .toolbar-title {{
            font-size: 12px;
            font-weight: 600;
            color: var(--text-muted);
            margin-right: 6px;
            text-transform: uppercase;
        }}
        .btn {{
            background: rgba(255, 255, 255, 0.05);
            color: var(--text);
            border: 1px solid var(--card-border);
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.18s;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}
        .btn:hover {{
            background: rgba(56, 189, 248, 0.2);
            border-color: var(--primary);
            color: #fff;
            transform: translateY(-1px);
        }}
        .btn-primary {{
            background: rgba(56, 189, 248, 0.18);
            border-color: rgba(56, 189, 248, 0.4);
            color: #38bdf8;
        }}
        .btn-primary:hover {{
            background: rgba(56, 189, 248, 0.35);
        }}

        /* KPI Stats Grid */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 14px;
            margin-bottom: 22px;
        }}
        .stat-card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 16px 18px;
            backdrop-filter: blur(12px);
            transition: all 0.2s;
        }}
        .stat-card:hover {{
            transform: translateY(-2px);
            border-color: var(--card-hover-border);
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
        }}
        .stat-label {{
            font-size: 12px;
            color: var(--text-muted);
            margin-bottom: 6px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .stat-value {{
            font-size: 22px;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
        }}
        .stat-sub {{
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 4px;
        }}

        /* Card Container */
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 18px;
            padding: 20px 22px;
            margin-bottom: 22px;
            backdrop-filter: blur(14px);
            box-shadow: 0 8px 24px rgba(0,0,0,0.25);
            transition: border-color 0.2s;
        }}
        .card:hover {{
            border-color: rgba(255, 255, 255, 0.14);
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 14px;
            flex-wrap: wrap;
            gap: 10px;
        }}
        .card-title {{
            font-size: 16px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .card-desc {{
            font-size: 12px;
            color: var(--text-muted);
        }}

        /* Tab Panes */
        .tab-pane {{
            display: none;
        }}
        .tab-pane.active {{
            display: block;
            animation: fadeIn 0.25s ease-in-out;
        }}
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(4px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        /* Chart Spacing & Heights */
        .chart-box {{
            width: 100%;
            height: 340px;
            margin-bottom: 8px;
        }}
        .chart-box-lg {{
            width: 100%;
            height: 850px;
        }}
        .chart-box-btn {{
            width: 100%;
            height: 200px;
        }}
        
        .axis-card {{
            background: rgba(15, 23, 42, 0.65);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 16px 18px 8px 18px;
            margin-bottom: 20px;
            transition: all 0.2s;
        }}
        .axis-card:hover {{
            border-color: rgba(56, 189, 248, 0.3);
        }}
        .axis-card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
            padding-bottom: 8px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        .axis-badge {{
            font-size: 11px;
            font-weight: 700;
            padding: 3px 10px;
            border-radius: 6px;
            font-family: 'JetBrains Mono', monospace;
        }}

        .grid-2col {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        @media (max-width: 992px) {{
            .grid-2col {{ grid-template-columns: 1fr; }}
        }}
        .plot-container-sm {{
            width: 100%;
            height: 420px;
        }}

        /* Table */
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
            padding: 11px 15px;
            text-align: left;
            border-bottom: 1px solid var(--card-border);
        }}
        th {{
            color: var(--text-muted);
            font-weight: 600;
            background: rgba(255, 255, 255, 0.02);
            font-size: 12px;
            text-transform: uppercase;
        }}
        tr:hover td {{
            background: rgba(255, 255, 255, 0.03);
        }}
        
        .hint-box {{
            background: rgba(56, 189, 248, 0.08);
            border-left: 3px solid var(--primary);
            padding: 10px 14px;
            border-radius: 0 8px 8px 0;
            font-size: 12px;
            color: #bae6fd;
            margin-bottom: 18px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header>
            <div class="header-title">
                <h1>📊 IMU & Edge AI Sensor Analytics</h1>
                <span class="badge">Đơn vị: Gia tốc (g) | Vận tốc góc (°/s)</span>
            </div>
            <div class="toolbar-group">
                <span style="font-size:12px; color: var(--text-muted);">⏱️ Tổng thời gian: <strong>{duration_s:.2f}s</strong> ({num_samples:,} mẫu @ {fs:.1f}Hz)</span>
            </div>
        </header>

        <!-- Navigation Tabs -->
        <div class="tabs-nav">
            <button class="tab-btn active" onclick="switchTab('tab-axes', this)">
                📐 1. So Sánh Tách Biệt Trục X - Y - Z
            </button>
            <button class="tab-btn" onclick="switchTab('tab-isolated', this)">
                📊 2. Tách Riêng 6 Kênh Độc Lập
            </button>
            <button class="tab-btn" onclick="switchTab('tab-overview', this)">
                📈 3. Tổng Quan Toàn Diện
            </button>
            <button class="tab-btn" onclick="switchTab('tab-3d-fft', this)">
                🌐 4. Quỹ Đạo 3D & Phổ FFT
            </button>
        </div>

        <!-- Global Smart Toolbar -->
        <div class="toolbar">
            <div class="toolbar-group">
                <span class="toolbar-title">🔍 Thu phóng nhanh:</span>
                <button class="btn btn-primary" onclick="resetAllZoom()">🔄 Reset Toàn Bộ</button>
                <button class="btn" onclick="zoomQuick(0, {duration_s/2:.2f})">🎯 Nửa Đầu (0 - {duration_s/2:.1f}s)</button>
                <button class="btn" onclick="zoomQuick({duration_s/2:.2f}, {duration_s:.2f})">🛑 Nửa Sau ({duration_s/2:.1f}s - {duration_s:.1f}s)</button>
                <button class="btn" onclick="zoomWindow(2.0)">⚡ Cửa sổ 2s</button>
                <button class="btn" onclick="zoomWindow(5.0)">⚡ Cửa sổ 5s</button>
            </div>
            <div class="toolbar-group">
                <span class="toolbar-title">📍 Sự kiện Nút:</span>
                <button class="btn" onclick="prevButtonEvent()">⏮️ Sự kiện trước</button>
                <span id="btn-event-counter" style="font-size:12px; font-family:'JetBrains Mono'; color:var(--accent-pink);">0 / {btn_events}</span>
                <button class="btn" onclick="nextButtonEvent()">⏭️ Sự kiện kế</button>
            </div>
        </div>

        <!-- KPI Cards -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Tổng Mẫu & Thời Lượng</div>
                <div class="stat-value" style="color: var(--primary);">{num_samples:,}</div>
                <div class="stat-sub">{duration_s:.2f} giây @ Δt={dt_ms:.1f}ms</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Tần Số Lấy Mẫu (Fs)</div>
                <div class="stat-value" style="color: var(--accent-green);">{fs:.2f} Hz</div>
                <div class="stat-sub">Độ chính xác 100Hz Non-blocking</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Sự Kiện Nhấn Nút</div>
                <div class="stat-value" style="color: var(--accent-pink);">{btn_events} lần nhấn</div>
                <div class="stat-sub">{btn_samples} mẫu tích cực ({btn_pct:.1f}%)</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Gia Tốc Cực Đại |Acc|</div>
                <div class="stat-value" style="color: var(--accent-amber);">{max_acc:.2f} g</div>
                <div class="stat-sub">Độ lớn vector toàn phần (g)</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Nhiệt Độ Cảm Biến</div>
                <div class="stat-value" style="color: var(--accent-purple);">{temp_min:.1f}°C - {temp_max:.1f}°C</div>
                <div class="stat-sub">Độ biến thiên ΔT = {temp_max-temp_min:+.1f}°C</div>
            </div>
        </div>

        <!-- ==================== TAB 1: SO SÁNH TÁCH BIỆT THEO TRỤC X, Y, Z ==================== -->
        <div id="tab-axes" class="tab-pane active">
            <div class="hint-box">
                <span>💡 <strong>Chế độ so sánh trục độc lập (Đơn vị: Gia tốc g | Con quay °/s):</strong> Mỗi trục X, Y, Z được tách riêng thành một card đồ thị rộng rãi. Khi bạn kéo chuột phóng to ở bất kỳ trục nào, các trục còn lại sẽ <strong>đồng bộ thời gian 100%</strong> mà không bị cắt mất tín hiệu!</span>
                <span style="font-size:11px; opacity:0.8;">Nhấp đúp chuột để Reset</span>
            </div>

            <!-- Card Trục X -->
            <div class="axis-card">
                <div class="axis-card-header">
                    <div class="card-title" style="color: var(--axis-x);">
                        <span>🔵 TRỤC X: Gia Tốc Acc X (g) vs Vận Tốc Góc Gyro X (°/s)</span>
                    </div>
                    <span class="axis-badge" style="background: rgba(56, 189, 248, 0.15); color: var(--axis-x);">AXIS-X</span>
                </div>
                <div id="chart-axis-x" class="chart-box"></div>
            </div>

            <!-- Card Trục Y -->
            <div class="axis-card">
                <div class="axis-card-header">
                    <div class="card-title" style="color: var(--axis-y);">
                        <span>🟢 TRỤC Y: Gia Tốc Acc Y (g) vs Vận Tốc Góc Gyro Y (°/s)</span>
                    </div>
                    <span class="axis-badge" style="background: rgba(52, 211, 153, 0.15); color: var(--axis-y);">AXIS-Y</span>
                </div>
                <div id="chart-axis-y" class="chart-box"></div>
            </div>

            <!-- Card Trục Z -->
            <div class="axis-card">
                <div class="axis-card-header">
                    <div class="card-title" style="color: var(--axis-z);">
                        <span>🟡 TRỤC Z: Gia Tốc Acc Z (g) vs Vận Tốc Góc Gyro Z (°/s)</span>
                    </div>
                    <span class="axis-badge" style="background: rgba(251, 191, 36, 0.15); color: var(--axis-z);">AXIS-Z</span>
                </div>
                <div id="chart-axis-z" class="chart-box"></div>
            </div>

            <!-- Card Nút Nhấn & Nhiệt Độ -->
            <div class="axis-card">
                <div class="axis-card-header">
                    <div class="card-title" style="color: var(--accent-pink);">
                        <span>🔘 TRẠNG THÁI NÚT BẤM (BUTTON) & NHIỆT ĐỘ CẢM BIẾN (°C)</span>
                    </div>
                    <span class="axis-badge" style="background: rgba(244, 114, 182, 0.15); color: var(--accent-pink);">EVENTS</span>
                </div>
                <div id="chart-axis-btn" class="chart-box-btn"></div>
            </div>
        </div>

        <!-- ==================== TAB 2: TÁCH RIÊNG 6 KÊNH ĐỘC LẬP ==================== -->
        <div id="tab-isolated" class="tab-pane">
            <div class="hint-box">
                <span>📊 <strong>Chế độ 6 Kênh Riêng Biệt:</strong> Khoảng cách mỗi sơ đồ được nới rộng tối đa, thang đo trục Y riêng biệt cho từng kênh (Acc theo g, Gyro theo °/s) để zoom sâu vào từng rung động vi mô.</span>
            </div>

            <div class="card">
                <div class="card-header">
                    <div class="card-title">📈 Chi Tiết 6 Kênh Cảm Biến Độc Lập (Đồng bộ Zoom)</div>
                </div>
                <div id="chart-isolated-6" style="width:100%; height: 1300px;"></div>
            </div>
        </div>

        <!-- ==================== TAB 3: TỔNG QUAN TOÀN DIỆN ==================== -->
        <div id="tab-overview" class="tab-pane">
            <div class="card">
                <div class="card-header">
                    <div class="card-title">📈 Tín Hiệu Thời Gian Tổng Hợp (Đầy Đủ Các Kênh)</div>
                    <span class="card-desc">Gia Tốc (g), Vận Tốc Góc (°/s), Nhiệt Độ (°C), Nút Bấm</span>
                </div>
                <div id="chart-overview" class="chart-box-lg"></div>
            </div>
        </div>

        <!-- ==================== TAB 4: QUỸ ĐẠO 3D & PHỔ TẦN SỐ FFT ==================== -->
        <div id="tab-3d-fft" class="tab-pane">
            <div class="grid-2col">
                <div class="card">
                    <div class="card-header">
                        <div class="card-title">🌐 Quỹ Đạo Gia Tốc Không Gian 3D (Acc X, Y, Z theo đơn vị g)</div>
                        <span class="card-desc">Kéo chuột để xoay góc nhìn 3D</span>
                    </div>
                    <div id="chart-3d" class="plot-container-sm"></div>
                </div>
                <div class="card">
                    <div class="card-header">
                        <div class="card-title">⚡ Phổ Tần Số FFT (Gia Tốc g & Vận Tốc Góc °/s)</div>
                        <span class="card-desc">Phân tích tần số dao động (0 - {fs/2:.1f}Hz)</span>
                    </div>
                    <div id="chart-fft" class="plot-container-sm"></div>
                </div>
            </div>
        </div>

        <!-- Bảng Thống Kê Chi Tiết -->
        <div class="card">
            <div class="card-header">
                <div class="card-title">📋 Bảng Thống Kê Thông Số Kỹ Thuật Chi Tiết (Đơn vị g và °/s)</div>
                <span class="card-desc">Mean, Standard Deviation, Min, Median, Max</span>
            </div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Kênh (Channel)</th>
                            <th>Mô tả</th>
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

    <!-- Script Logic -->
    <script>
        const rawData = {json_data_str};
        const time = rawData.time;
        const buttonEvents = rawData.button_events || [];
        let currentEventIdx = -1;
        let isSyncing = false;

        // Tao danh sach cac vung highlight nut nhan
        function getButtonShapes() {{
            const shapes = [];
            for (let ev of buttonEvents) {{
                shapes.push({{
                    type: 'rect',
                    xref: 'x',
                    yref: 'paper',
                    x0: ev.t_start,
                    x1: ev.t_end,
                    y0: 0,
                    y1: 1,
                    fillcolor: 'rgba(244, 114, 182, 0.16)',
                    line: {{ color: 'rgba(244, 114, 182, 0.4)', width: 1, dash: 'dot' }}
                }});
            }}
            return shapes;
        }}

        const btnShapes = getButtonShapes();

        // Base Layout Theme
        const baseTheme = {{
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'rgba(15, 23, 42, 0.55)',
            font: {{ color: '#cbd5e1', family: 'Plus Jakarta Sans' }},
            hovermode: 'x unified',
            hoverlabel: {{ bgcolor: '#1e293b', font: {{ family: 'JetBrains Mono', size: 12 }} }}
        }};

        // ==================== 1. RENDER TAB 1: AXES X, Y, Z SEPARATE ====================
        function renderAxesTab() {{
            const axisCommonLayout = (titleY1, titleY2, color1, color2) => ({{
                ...baseTheme,
                margin: {{ l: 65, r: 65, t: 15, b: 35 }},
                shapes: btnShapes,
                xaxis: {{
                    gridcolor: 'rgba(255, 255, 255, 0.06)',
                    showgrid: true,
                    zeroline: true,
                    zerolinecolor: 'rgba(255,255,255,0.15)'
                }},
                yaxis: {{
                    title: titleY1,
                    titlefont: {{ color: color1, size: 12 }},
                    tickfont: {{ color: color1 }},
                    gridcolor: 'rgba(255, 255, 255, 0.06)',
                    zerolinecolor: 'rgba(255,255,255,0.1)'
                }},
                yaxis2: {{
                    title: titleY2,
                    titlefont: {{ color: color2, size: 12 }},
                    tickfont: {{ color: color2 }},
                    overlaying: 'y',
                    side: 'right',
                    gridcolor: 'rgba(255, 255, 255, 0.02)',
                    zeroline: false
                }},
                legend: {{
                    orientation: 'h',
                    x: 0.01,
                    y: 1.14,
                    font: {{ size: 11 }},
                    bgcolor: 'rgba(15, 23, 42, 0.7)'
                }}
            }});

            // --- Trục X ---
            const traceAccX = {{ x: time, y: rawData.acc_x, name: 'Gia tốc Acc X (g)', line: {{ color: '#38bdf8', width: 1.8 }} }};
            const traceGyroX = {{ x: time, y: rawData.gyro_x, name: 'Vận tốc góc Gyro X (°/s)', yaxis: 'y2', line: {{ color: '#fb923c', width: 1.6, dash: 'solid' }} }};
            Plotly.newPlot('chart-axis-x', [traceAccX, traceGyroX], axisCommonLayout('Acc X (g)', 'Gyro X (°/s)', '#38bdf8', '#fb923c'), {{ responsive: true }});

            // --- Trục Y ---
            const traceAccY = {{ x: time, y: rawData.acc_y, name: 'Gia tốc Acc Y (g)', line: {{ color: '#34d399', width: 1.8 }} }};
            const traceGyroY = {{ x: time, y: rawData.gyro_y, name: 'Vận tốc góc Gyro Y (°/s)', yaxis: 'y2', line: {{ color: '#c084fc', width: 1.6, dash: 'solid' }} }};
            Plotly.newPlot('chart-axis-y', [traceAccY, traceGyroY], axisCommonLayout('Acc Y (g)', 'Gyro Y (°/s)', '#34d399', '#c084fc'), {{ responsive: true }});

            // --- Trục Z ---
            const traceAccZ = {{ x: time, y: rawData.acc_z, name: 'Gia tốc Acc Z (g)', line: {{ color: '#fbbf24', width: 1.8 }} }};
            const traceGyroZ = {{ x: time, y: rawData.gyro_z, name: 'Vận tốc góc Gyro Z (°/s)', yaxis: 'y2', line: {{ color: '#f43f5e', width: 1.6, dash: 'solid' }} }};
            Plotly.newPlot('chart-axis-z', [traceAccZ, traceGyroZ], axisCommonLayout('Acc Z (g)', 'Gyro Z (°/s)', '#fbbf24', '#f43f5e'), {{ responsive: true }});

            // --- Nút Nhấn & Nhiệt Độ ---
            const traceBtn = {{ 
                x: time, y: rawData.button, name: 'Trạng thái nút bấm', 
                line: {{ color: '#f472b6', width: 2, shape: 'hv' }}, 
                fill: 'tozeroy', fillcolor: 'rgba(244, 114, 182, 0.22)' 
            }};
            const traceTemp = {{ 
                x: time, y: rawData.temp, name: 'Nhiệt độ (°C)', yaxis: 'y2', 
                line: {{ color: '#a78bfa', width: 1.8 }} 
            }};
            
            const btnLayout = {{
                ...baseTheme,
                margin: {{ l: 65, r: 65, t: 10, b: 40 }},
                shapes: btnShapes,
                xaxis: {{
                    title: 'Thời gian (giây)',
                    gridcolor: 'rgba(255, 255, 255, 0.06)',
                    showgrid: true
                }},
                yaxis: {{
                    title: 'Nút bấm',
                    titlefont: {{ color: '#f472b6', size: 12 }},
                    tickfont: {{ color: '#f472b6' }},
                    tickvals: [0, 1],
                    ticktext: ['Nhả (0)', 'Nhấn (1)'],
                    gridcolor: 'rgba(255, 255, 255, 0.06)',
                    range: [-0.15, 1.25]
                }},
                yaxis2: {{
                    title: 'Nhiệt độ (°C)',
                    titlefont: {{ color: '#a78bfa', size: 12 }},
                    tickfont: {{ color: '#a78bfa' }},
                    overlaying: 'y',
                    side: 'right',
                    gridcolor: 'rgba(255, 255, 255, 0.02)'
                }},
                legend: {{
                    orientation: 'h',
                    x: 0.01,
                    y: 1.25,
                    font: {{ size: 11 }},
                    bgcolor: 'rgba(15, 23, 42, 0.7)'
                }}
            }};
            Plotly.newPlot('chart-axis-btn', [traceBtn, traceTemp], btnLayout, {{ responsive: true }});

            // Đồng bộ hóa Zoom giữa 4 biểu đồ Tab 1
            const axisCharts = ['chart-axis-x', 'chart-axis-y', 'chart-axis-z', 'chart-axis-btn'];
            axisCharts.forEach(id => {{
                const el = document.getElementById(id);
                el.on('plotly_relayout', function(eventdata) {{
                    if (isSyncing) return;
                    if (eventdata['xaxis.range[0]'] !== undefined || eventdata['xaxis.autorange'] !== undefined) {{
                        isSyncing = true;
                        const update = {{}};
                        if (eventdata['xaxis.range[0]'] !== undefined) {{
                            update['xaxis.range'] = [eventdata['xaxis.range[0]'], eventdata['xaxis.range[1]']];
                            update['xaxis.autorange'] = false;
                        }} else {{
                            update['xaxis.autorange'] = true;
                        }}
                        
                        axisCharts.forEach(otherId => {{
                            if (otherId !== id) {{
                                Plotly.relayout(otherId, update);
                            }}
                        }});
                        isSyncing = false;
                    }}
                }});
            }});
        }}

        // ==================== 2. RENDER TAB 2: 6 ISOLATED CHANNELS ====================
        function renderIsolatedTab() {{
            const traces = [
                {{ x: time, y: rawData.acc_x, name: 'Acc X (g)', line: {{ color: '#38bdf8', width: 1.6 }}, xaxis: 'x', yaxis: 'y1' }},
                {{ x: time, y: rawData.acc_y, name: 'Acc Y (g)', line: {{ color: '#34d399', width: 1.6 }}, xaxis: 'x', yaxis: 'y2' }},
                {{ x: time, y: rawData.acc_z, name: 'Acc Z (g)', line: {{ color: '#fbbf24', width: 1.6 }}, xaxis: 'x', yaxis: 'y3' }},
                {{ x: time, y: rawData.gyro_x, name: 'Gyro X (°/s)', line: {{ color: '#fb923c', width: 1.6 }}, xaxis: 'x', yaxis: 'y4' }},
                {{ x: time, y: rawData.gyro_y, name: 'Gyro Y (°/s)', line: {{ color: '#c084fc', width: 1.6 }}, xaxis: 'x', yaxis: 'y5' }},
                {{ x: time, y: rawData.gyro_z, name: 'Gyro Z (°/s)', line: {{ color: '#f43f5e', width: 1.6 }}, xaxis: 'x', yaxis: 'y6' }}
            ];

            const layout6 = {{
                ...baseTheme,
                grid: {{ rows: 6, columns: 1, pattern: 'independent', roworder: 'top to bottom' }},
                margin: {{ l: 70, r: 30, t: 30, b: 40 }},
                shapes: btnShapes,
                xaxis: {{ title: 'Thời gian (giây)', gridcolor: 'rgba(255,255,255,0.06)', anchor: 'y6' }},
                yaxis:  {{ title: 'Acc X (g)', gridcolor: 'rgba(255,255,255,0.06)', domain: [0.85, 0.98] }},
                yaxis2: {{ title: 'Acc Y (g)', gridcolor: 'rgba(255,255,255,0.06)', domain: [0.68, 0.81] }},
                yaxis3: {{ title: 'Acc Z (g)', gridcolor: 'rgba(255,255,255,0.06)', domain: [0.51, 0.64] }},
                yaxis4: {{ title: 'Gyro X (°/s)', gridcolor: 'rgba(255,255,255,0.06)', domain: [0.34, 0.47] }},
                yaxis5: {{ title: 'Gyro Y (°/s)', gridcolor: 'rgba(255,255,255,0.06)', domain: [0.17, 0.30] }},
                yaxis6: {{ title: 'Gyro Z (°/s)', gridcolor: 'rgba(255,255,255,0.06)', domain: [0.00, 0.13] }},
                legend: {{ orientation: 'h', x: 0, y: 1.04, font: {{ size: 11 }} }}
            }};

            Plotly.newPlot('chart-isolated-6', traces, layout6, {{ responsive: true }});
        }}

        // ==================== 3. RENDER TAB 3: UNIFIED OVERVIEW ====================
        function renderOverviewTab() {{
            const traceAccX = {{ x: time, y: rawData.acc_x, name: 'Acc X (g)', line: {{ color: '#38bdf8', width: 1.4 }}, xaxis: 'x', yaxis: 'y1' }};
            const traceAccY = {{ x: time, y: rawData.acc_y, name: 'Acc Y (g)', line: {{ color: '#34d399', width: 1.4 }}, xaxis: 'x', yaxis: 'y1' }};
            const traceAccZ = {{ x: time, y: rawData.acc_z, name: 'Acc Z (g)', line: {{ color: '#fbbf24', width: 1.4 }}, xaxis: 'x', yaxis: 'y1' }};
            const traceAccMag = {{ x: time, y: rawData.acc_mag, name: '|Acc| Total (g)', line: {{ color: '#f87171', width: 1.8, dash: 'dot' }}, xaxis: 'x', yaxis: 'y1' }};

            const traceGyroX = {{ x: time, y: rawData.gyro_x, name: 'Gyro X (°/s)', line: {{ color: '#fb923c', width: 1.4 }}, xaxis: 'x', yaxis: 'y2' }};
            const traceGyroY = {{ x: time, y: rawData.gyro_y, name: 'Gyro Y (°/s)', line: {{ color: '#c084fc', width: 1.4 }}, xaxis: 'x', yaxis: 'y2' }};
            const traceGyroZ = {{ x: time, y: rawData.gyro_z, name: 'Gyro Z (°/s)', line: {{ color: '#f43f5e', width: 1.4 }}, xaxis: 'x', yaxis: 'y2' }};
            const traceGyroMag = {{ x: time, y: rawData.gyro_mag, name: '|Gyro| Total (°/s)', line: {{ color: '#f87171', width: 1.8, dash: 'dot' }}, xaxis: 'x', yaxis: 'y2' }};

            const traceTemp = {{ x: time, y: rawData.temp, name: 'Nhiệt độ (°C)', line: {{ color: '#a78bfa', width: 1.8 }}, xaxis: 'x', yaxis: 'y3' }};
            const traceBtn = {{ x: time, y: rawData.button, name: 'Nút bấm', line: {{ color: '#f472b6', width: 2, shape: 'hv' }}, fill: 'tozeroy', fillcolor: 'rgba(244, 114, 182, 0.25)', xaxis: 'x', yaxis: 'y4' }};

            const layoutOverview = {{
                ...baseTheme,
                grid: {{ rows: 4, columns: 1, pattern: 'independent', roworder: 'top to bottom' }},
                margin: {{ l: 70, r: 30, t: 25, b: 40 }},
                shapes: btnShapes,
                xaxis: {{ title: 'Thời gian (giây)', gridcolor: 'rgba(255,255,255,0.06)', anchor: 'y4' }},
                yaxis:  {{ title: 'Gia tốc (g)', gridcolor: 'rgba(255,255,255,0.06)', domain: [0.73, 1.0] }},
                yaxis2: {{ title: 'Vận tốc góc (°/s)', gridcolor: 'rgba(255,255,255,0.06)', domain: [0.46, 0.68] }},
                yaxis3: {{ title: 'Nhiệt độ (°C)', gridcolor: 'rgba(255,255,255,0.06)', domain: [0.22, 0.41] }},
                yaxis4: {{ 
                    title: 'Nút nhấn', gridcolor: 'rgba(255,255,255,0.06)', domain: [0.0, 0.17],
                    tickvals: [0, 1], ticktext: ['Nhả (0)', 'Nhấn (1)']
                }},
                legend: {{ orientation: 'h', x: 0, y: 1.06, font: {{ size: 11 }} }}
            }};

            Plotly.newPlot('chart-overview', [traceAccX, traceAccY, traceAccZ, traceAccMag, traceGyroX, traceGyroY, traceGyroZ, traceGyroMag, traceTemp, traceBtn], layoutOverview, {{ responsive: true }});
        }}

        // ==================== 4. RENDER TAB 4: 3D & FFT ====================
        function render3DAndFFT() {{
            // 3D Scatter
            const trace3d = {{
                type: 'scatter3d',
                mode: 'lines+markers',
                x: rawData.acc_x,
                y: rawData.acc_y,
                z: rawData.acc_z,
                line: {{ color: 'rgba(148, 163, 184, 0.35)', width: 1.5 }},
                marker: {{
                    size: 3,
                    color: rawData.time,
                    colorscale: 'Viridis',
                    colorbar: {{ title: 'Thời gian (s)', len: 0.8, x: 1.02 }}
                }}
            }};

            const layout3d = {{
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent',
                font: {{ color: '#cbd5e1' }},
                margin: {{ l: 0, r: 0, t: 0, b: 0 }},
                scene: {{
                    xaxis: {{ title: 'Acc X (g)', gridcolor: 'rgba(255,255,255,0.1)' }},
                    yaxis: {{ title: 'Acc Y (g)', gridcolor: 'rgba(255,255,255,0.1)' }},
                    zaxis: {{ title: 'Acc Z (g)', gridcolor: 'rgba(255,255,255,0.1)' }},
                    bgcolor: 'rgba(15, 23, 42, 0.65)'
                }}
            }};
            Plotly.newPlot('chart-3d', [trace3d], layout3d, {{ responsive: true }});

            // FFT
            const dt = {dt_ms} / 1000.0;
            const fs = {fs};
            const N = rawData.acc_mag.length;
            const meanAcc = rawData.acc_mag.reduce((a,b)=>a+b,0)/N;
            const meanGyro = rawData.gyro_mag.reduce((a,b)=>a+b,0)/N;
            const accSignal = rawData.acc_mag.map(v => v - meanAcc);
            const gyroSignal = rawData.gyro_mag.map(v => v - meanGyro);
            const numFreqs = Math.min(256, Math.floor(N / 2));
            const freqs = [], accAmps = [], gyroAmps = [];

            for(let k=0; k<numFreqs; k++) {{
                const freq = (k * fs) / N;
                freqs.push(freq);
                let reAcc = 0, imAcc = 0, reGyro = 0, imGyro = 0;
                for(let n=0; n<N; n++) {{
                    const phi = (2 * Math.PI * k * n) / N;
                    const c = Math.cos(phi), s = Math.sin(phi);
                    reAcc += accSignal[n] * c;
                    imAcc -= accSignal[n] * s;
                    reGyro += gyroSignal[n] * c;
                    imGyro -= gyroSignal[n] * s;
                }}
                accAmps.push((Math.sqrt(reAcc*reAcc + imAcc*imAcc) * 2) / N);
                gyroAmps.push((Math.sqrt(reGyro*reGyro + imGyro*imGyro) * 2) / N);
            }}

            const traceAccFFT = {{ x: freqs, y: accAmps, name: 'Phổ Gia Tốc (|Acc| AC) (g)', line: {{ color: '#38bdf8', width: 1.8 }} }};
            const traceGyroFFT = {{ x: freqs, y: gyroAmps, name: 'Phổ Vận Tốc Góc (|Gyro| AC) (°/s)', line: {{ color: '#f87171', width: 1.8 }} }};

            const layoutFFT = {{
                ...baseTheme,
                margin: {{ l: 55, r: 25, t: 20, b: 40 }},
                xaxis: {{ title: 'Tần số (Hz)', range: [0, fs/2], gridcolor: 'rgba(255,255,255,0.06)' }},
                yaxis: {{ title: 'Biên độ phổ', gridcolor: 'rgba(255,255,255,0.06)' }},
                legend: {{ orientation: 'h', y: 1.15, font: {{ size: 11 }} }}
            }};

            Plotly.newPlot('chart-fft', [traceAccFFT, traceGyroFFT], layoutFFT, {{ responsive: true }});
        }}

        // ==================== SMART CONTROLS & ZOOM ====================
        function getAllActiveChartIds() {{
            return ['chart-axis-x', 'chart-axis-y', 'chart-axis-z', 'chart-axis-btn', 'chart-isolated-6', 'chart-overview'];
        }}

        function resetAllZoom() {{
            const ids = getAllActiveChartIds();
            ids.forEach(id => {{
                const el = document.getElementById(id);
                if (el && el.data) {{
                    Plotly.relayout(id, {{ 'xaxis.autorange': true }});
                }}
            }});
        }}

        function zoomQuick(startT, endT) {{
            const ids = getAllActiveChartIds();
            ids.forEach(id => {{
                const el = document.getElementById(id);
                if (el && el.data) {{
                    Plotly.relayout(id, {{ 'xaxis.range': [startT, endT], 'xaxis.autorange': false }});
                }}
            }});
        }}

        function zoomWindow(winSec) {{
            const el = document.getElementById('chart-axis-x');
            let centerT = {duration_s/2:.2f};
            if (el && el.layout && el.layout.xaxis && el.layout.xaxis.range) {{
                centerT = (el.layout.xaxis.range[0] + el.layout.xaxis.range[1]) / 2.0;
            }}
            const half = winSec / 2.0;
            const startT = Math.max(0, centerT - half);
            const endT = Math.min({duration_s:.2f}, centerT + half);
            zoomQuick(startT, endT);
        }}

        function nextButtonEvent() {{
            if (buttonEvents.length === 0) return;
            currentEventIdx = (currentEventIdx + 1) % buttonEvents.length;
            focusOnEvent(buttonEvents[currentEventIdx]);
        }}

        function prevButtonEvent() {{
            if (buttonEvents.length === 0) return;
            currentEventIdx = (currentEventIdx - 1 + buttonEvents.length) % buttonEvents.length;
            focusOnEvent(buttonEvents[currentEventIdx]);
        }}

        function focusOnEvent(ev) {{
            const pad = 1.0; // padding 1s
            const startT = Math.max(0, ev.t_start - pad);
            const endT = Math.min({duration_s:.2f}, ev.t_end + pad);
            zoomQuick(startT, endT);
            document.getElementById('btn-event-counter').innerText = `${{ev.event_id}} / ${{buttonEvents.length}} (${{ev.duration}}s)`;
        }}

        // Tab Switching Logic
        function switchTab(tabId, btn) {{
            document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            
            document.getElementById(tabId).classList.add('active');
            btn.classList.add('active');

            // Trigger Plotly Resize / Render
            setTimeout(() => {{
                if (tabId === 'tab-axes') {{
                    Plotly.Plots.resize('chart-axis-x');
                    Plotly.Plots.resize('chart-axis-y');
                    Plotly.Plots.resize('chart-axis-z');
                    Plotly.Plots.resize('chart-axis-btn');
                }} else if (tabId === 'tab-isolated') {{
                    Plotly.Plots.resize('chart-isolated-6');
                }} else if (tabId === 'tab-overview') {{
                    Plotly.Plots.resize('chart-overview');
                }} else if (tabId === 'tab-3d-fft') {{
                    Plotly.Plots.resize('chart-3d');
                    Plotly.Plots.resize('chart-fft');
                }}
            }}, 50);
        }}

        // Initialize All Charts on Load
        window.addEventListener('DOMContentLoaded', () => {{
            renderAxesTab();
            renderIsolatedTab();
            renderOverviewTab();
            render3DAndFFT();
        }});
    </script>
</body>
</html>
"""

output_file = os.path.join(BASE_DIR, 'dashboard.html')
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"{output_file} generated successfully for {num_samples} samples!")
