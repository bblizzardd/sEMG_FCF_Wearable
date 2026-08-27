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
        .btn-zoom-mode {{
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-muted);
            border: 1px solid var(--card-border);
            padding: 5px 10px;
            border-radius: 8px;
            font-size: 11px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.18s;
            display: inline-flex;
            align-items: center;
            gap: 5px;
        }}
        .btn-zoom-mode:hover {{
            color: #fff;
            border-color: var(--primary);
            background: rgba(56, 189, 248, 0.15);
        }}
        .btn-zoom-mode.active {{
            background: rgba(56, 189, 248, 0.25);
            border-color: #38bdf8;
            color: #38bdf8;
            box-shadow: 0 0 10px rgba(56, 189, 248, 0.3);
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

        /* Fullscreen Card Mode */
        body.fullscreen-active {{
            overflow: hidden;
        }}
        .axis-card.is-fullscreen,
        .card.is-fullscreen {{
            position: fixed !important;
            top: 0 !important;
            left: 0 !important;
            right: 0 !important;
            bottom: 0 !important;
            width: 100vw !important;
            height: 100vh !important;
            max-width: 100vw !important;
            max-height: 100vh !important;
            z-index: 999999 !important;
            border-radius: 0 !important;
            margin: 0 !important;
            padding: 20px 24px !important;
            background: #090d16 !important;
            background-image: 
                radial-gradient(circle at 10% 0%, rgba(56, 189, 248, 0.16) 0px, transparent 50%),
                radial-gradient(circle at 90% 90%, rgba(192, 132, 252, 0.12) 0px, transparent 50%) !important;
            display: flex !important;
            flex-direction: column !important;
            box-shadow: none !important;
            border: none !important;
            animation: zoomModal 0.22s cubic-bezier(0.16, 1, 0.3, 1) !important;
        }}

        @keyframes zoomModal {{
            from {{
                opacity: 0;
                transform: scale(0.98);
            }}
            to {{
                opacity: 1;
                transform: scale(1);
            }}
        }}

        .is-fullscreen .axis-card-header,
        .is-fullscreen .card-header {{
            flex-shrink: 0 !important;
            margin-bottom: 12px !important;
            padding-bottom: 12px !important;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1) !important;
        }}

        .is-fullscreen .chart-box,
        .is-fullscreen .chart-box-lg,
        .is-fullscreen .chart-box-btn,
        .is-fullscreen .plot-container-sm {{
            flex: 1 1 auto !important;
            width: 100% !important;
            height: calc(100vh - 90px) !important;
            max-height: calc(100vh - 90px) !important;
            margin-bottom: 0 !important;
        }}

        .btn-fullscreen {{
            background: rgba(255, 255, 255, 0.06);
            color: var(--text);
            border: 1px solid var(--card-border);
            padding: 5px 12px;
            border-radius: 8px;
            font-size: 11px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-family: 'Plus Jakarta Sans', sans-serif;
        }}
        .btn-fullscreen:hover {{
            background: rgba(56, 189, 248, 0.25);
            border-color: var(--primary);
            color: #38bdf8;
            transform: translateY(-1px);
            box-shadow: 0 2px 10px rgba(56, 189, 248, 0.3);
        }}
        .is-fullscreen .btn-fullscreen {{
            background: rgba(244, 63, 94, 0.2);
            border-color: rgba(244, 63, 94, 0.5);
            color: #fda4af;
        }}
        .is-fullscreen .btn-fullscreen:hover {{
            background: rgba(244, 63, 94, 0.35);
            border-color: #f43f5e;
            color: #fff;
            box-shadow: 0 2px 10px rgba(244, 63, 94, 0.4);
        }}

        /* Fullscreen Tab Overlay (Comparison Mode) */
        .tab-pane.is-tab-fullscreen {{
            position: fixed !important;
            top: 0 !important;
            left: 0 !important;
            right: 0 !important;
            bottom: 0 !important;
            width: 100vw !important;
            height: 100vh !important;
            max-width: 100vw !important;
            max-height: 100vh !important;
            z-index: 999990 !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
            margin: 0 !important;
            padding: 20px 30px 60px 30px !important;
            background: #090d16 !important;
            background-image: 
                radial-gradient(circle at 10% 0%, rgba(56, 189, 248, 0.15) 0px, transparent 50%),
                radial-gradient(circle at 90% 90%, rgba(192, 132, 252, 0.12) 0px, transparent 50%) !important;
            display: block !important;
            animation: zoomModal 0.22s cubic-bezier(0.16, 1, 0.3, 1) !important;
        }}

        .tab-fullscreen-header {{
            position: sticky;
            top: -20px;
            z-index: 999995;
            background: rgba(9, 13, 22, 0.94);
            backdrop-filter: blur(16px);
            padding: 14px 20px;
            margin: -20px -30px 20px -30px;
            border-bottom: 1px solid var(--card-border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
        }}

        .btn-tab-fullscreen {{
            background: linear-gradient(135deg, rgba(56, 189, 248, 0.18), rgba(192, 132, 252, 0.18));
            color: #bae6fd;
            border: 1px solid rgba(56, 189, 248, 0.4);
            padding: 6px 14px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-family: 'Plus Jakarta Sans', sans-serif;
        }}
        .btn-tab-fullscreen:hover {{
            background: linear-gradient(135deg, rgba(56, 189, 248, 0.35), rgba(192, 132, 252, 0.35));
            border-color: var(--primary);
            color: #fff;
            transform: translateY(-1px);
            box-shadow: 0 4px 14px rgba(56, 189, 248, 0.3);
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
                <span class="toolbar-title">⚡ Thao tác nhanh:</span>
                <button class="btn btn-primary" onclick="resetAllZoom()">🔄 Reset Toàn Bộ</button>
                <button class="btn btn-tab-fullscreen" onclick="toggleCurrentTabFullscreen()" title="Phóng to toàn bộ các đồ thị trong tab hiện tại">📺 Phóng To Mục</button>
            </div>
            <div class="toolbar-group">
                <span class="toolbar-title">🎛️ Chế độ Cuộn Chuột:</span>
                <button class="btn-zoom-mode active" id="btn-mode-xy" onclick="setZoomMode('xy', this)" title="Cuộn chuột phóng to/thu nhỏ cả 2 chiều đồng thời (Mặc định)">🔍 Cả 2 Chiều (XY)</button>
                <button class="btn-zoom-mode" id="btn-mode-x" onclick="setZoomMode('x', this)" title="Cuộn chuột chỉ dãn/thu trục thời gian (Hoặc giữ phím Shift khi cuộn)">↔️ Chiều Ngang (X)</button>
                <button class="btn-zoom-mode" id="btn-mode-y" onclick="setZoomMode('y', this)" title="Cuộn chuột chỉ dãn/thu biên độ (Hoặc giữ phím Ctrl/Alt khi cuộn)">↕️ Chiều Dọc (Y)</button>
            </div>
            <div class="toolbar-group">
                <span class="toolbar-title">↔️ Chiều Ngang (Thời Gian):</span>
                <button class="btn" onclick="stretchX(1.4)" title="Kéo dãn trục thời gian (Phím +)">↔️➕ Dãn X</button>
                <button class="btn" onclick="stretchX(0.71)" title="Thu hẹp trục thời gian (Phím -)">↔️➖ Thu X</button>
                <button class="btn" onclick="setTimeWindow(2.0)" title="Xem cửa sổ thời gian 2 giây">⏱️ 2s</button>
                <button class="btn" onclick="setTimeWindow(5.0)" title="Xem cửa sổ thời gian 5 giây">⏱️ 5s</button>
                <button class="btn" onclick="setTimeWindow(10.0)" title="Xem cửa sổ thời gian 10 giây">⏱️ 10s</button>
            </div>
            <div class="toolbar-group">
                <span class="toolbar-title">↕️ Chiều Dọc (Biên Độ):</span>
                <button class="btn" onclick="stretchY(1.4)" title="Phóng to biên độ dọc (Shift + hoặc Ctrl+Cuộn)">↕️➕ Dãn Y</button>
                <button class="btn" onclick="stretchY(0.71)" title="Thu nhỏ biên độ dọc (Shift - hoặc Ctrl+Cuộn)">↕️➖ Thu Y</button>
                <button class="btn" onclick="autoFitY()" title="Tự động căn chỉnh biên độ Y vừa vặn">↕️ Auto Y</button>
            </div>
            <div class="toolbar-group">
                <span class="toolbar-title">📍 Nút Nhấn:</span>
                <button class="btn" onclick="prevButtonEvent()">⏮️ Trước</button>
                <span id="btn-event-counter" style="font-size:12px; font-family:'JetBrains Mono'; color:var(--accent-pink);">0 / {btn_events}</span>
                <button class="btn" onclick="nextButtonEvent()">⏭️ Kế</button>
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
                <span>💡 <strong>Thao tác trực quan:</strong> 🖱️ <strong>Cuộn chuột</strong> để Zoom (Mặc định cả 2 chiều XY) • ⌨️ <strong>Shift + Cuộn</strong> để Zoom <strong>Chiều Ngang (X)</strong> • <strong>Ctrl/Alt + Cuộn</strong> để Zoom <strong>Chiều Dọc (Y)</strong> • 🖐️ <strong>Nhấn giữ & kéo</strong> để Dịch chuyển (Pan) • 🔄 <strong>Nhấp đúp</strong> để Reset!</span>
                <div style="display: flex; gap: 8px;">
                    <button class="btn-tab-fullscreen" onclick="toggleTabFullscreen('tab-axes')">📺 Phóng to toàn bộ Tab 1 để so sánh</button>
                </div>
            </div>

            <!-- Card Trục X -->
            <div class="axis-card" id="card-axis-x">
                <div class="axis-card-header">
                    <div class="card-title" style="color: var(--axis-x);">
                        <span>🔵 TRỤC X: Gia Tốc Acc X (g) vs Vận Tốc Góc Gyro X (°/s)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="axis-badge" style="background: rgba(56, 189, 248, 0.15); color: var(--axis-x);">AXIS-X</span>
                        <button class="btn-fullscreen" onclick="toggleFullscreen('card-axis-x', 'chart-axis-x')" title="Phóng to đồ thị này">⛶ Toàn màn hình</button>
                    </div>
                </div>
                <div id="chart-axis-x" class="chart-box"></div>
            </div>

            <!-- Card Trục Y -->
            <div class="axis-card" id="card-axis-y">
                <div class="axis-card-header">
                    <div class="card-title" style="color: var(--axis-y);">
                        <span>🟢 TRỤC Y: Gia Tốc Acc Y (g) vs Vận Tốc Góc Gyro Y (°/s)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="axis-badge" style="background: rgba(52, 211, 153, 0.15); color: var(--axis-y);">AXIS-Y</span>
                        <button class="btn-fullscreen" onclick="toggleFullscreen('card-axis-y', 'chart-axis-y')" title="Phóng to đồ thị này">⛶ Toàn màn hình</button>
                    </div>
                </div>
                <div id="chart-axis-y" class="chart-box"></div>
            </div>

            <!-- Card Trục Z -->
            <div class="axis-card" id="card-axis-z">
                <div class="axis-card-header">
                    <div class="card-title" style="color: var(--axis-z);">
                        <span>🟡 TRỤC Z: Gia Tốc Acc Z (g) vs Vận Tốc Góc Gyro Z (°/s)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="axis-badge" style="background: rgba(251, 191, 36, 0.15); color: var(--axis-z);">AXIS-Z</span>
                        <button class="btn-fullscreen" onclick="toggleFullscreen('card-axis-z', 'chart-axis-z')" title="Phóng to đồ thị này">⛶ Toàn màn hình</button>
                    </div>
                </div>
                <div id="chart-axis-z" class="chart-box"></div>
            </div>

            <!-- Card Nút Nhấn & Nhiệt Độ -->
            <div class="axis-card" id="card-axis-btn">
                <div class="axis-card-header">
                    <div class="card-title" style="color: var(--accent-pink);">
                        <span>🔘 TRẠNG THÁI NÚT BẤM (BUTTON) & NHIỆT ĐỘ CẢM BIẾN (°C)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="axis-badge" style="background: rgba(244, 114, 182, 0.15); color: var(--accent-pink);">EVENTS</span>
                        <button class="btn-fullscreen" onclick="toggleFullscreen('card-axis-btn', 'chart-axis-btn')" title="Phóng to đồ thị này">⛶ Toàn màn hình</button>
                    </div>
                </div>
                <div id="chart-axis-btn" class="chart-box-btn"></div>
            </div>
        </div>

        <!-- ==================== TAB 2: TÁCH RIÊNG 6 KÊNH ĐỘC LẬP ==================== -->
        <div id="tab-isolated" class="tab-pane">
            <div class="hint-box">
                <span>📊 <strong>6 Kênh Riêng Biệt:</strong> 🖱️ <strong>Cuộn chuột</strong> để Zoom (Mặc định XY) • ⌨️ <strong>Shift + Cuộn</strong> (Zoom X) • <strong>Ctrl/Alt + Cuộn</strong> (Zoom Y) • 🖐️ <strong>Kéo chuột</strong> để Pan • 🔄 <strong>Nhấp đúp</strong> để Reset!</span>
                <div style="display: flex; gap: 8px;">
                    <button class="btn-tab-fullscreen" onclick="toggleTabFullscreen('tab-isolated')">📺 Phóng to toàn bộ 6 kênh để so sánh</button>
                </div>
            </div>

            <!-- Card Acc X -->
            <div class="axis-card" id="card-iso-acc-x">
                <div class="axis-card-header">
                    <div class="card-title" style="color: #38bdf8;">
                        <span>🔵 GIA TỐC ACC X (g)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="axis-badge" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8;">ACC-X</span>
                        <button class="btn-fullscreen" onclick="toggleFullscreen('card-iso-acc-x', 'chart-iso-acc-x')" title="Phóng to đồ thị này">⛶ Toàn màn hình</button>
                    </div>
                </div>
                <div id="chart-iso-acc-x" class="chart-box" style="height: 240px;"></div>
            </div>

            <!-- Card Acc Y -->
            <div class="axis-card" id="card-iso-acc-y">
                <div class="axis-card-header">
                    <div class="card-title" style="color: #34d399;">
                        <span>🟢 GIA TỐC ACC Y (g)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="axis-badge" style="background: rgba(52, 211, 153, 0.15); color: #34d399;">ACC-Y</span>
                        <button class="btn-fullscreen" onclick="toggleFullscreen('card-iso-acc-y', 'chart-iso-acc-y')" title="Phóng to đồ thị này">⛶ Toàn màn hình</button>
                    </div>
                </div>
                <div id="chart-iso-acc-y" class="chart-box" style="height: 240px;"></div>
            </div>

            <!-- Card Acc Z -->
            <div class="axis-card" id="card-iso-acc-z">
                <div class="axis-card-header">
                    <div class="card-title" style="color: #fbbf24;">
                        <span>🟡 GIA TỐC ACC Z (g)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="axis-badge" style="background: rgba(251, 191, 36, 0.15); color: #fbbf24;">ACC-Z</span>
                        <button class="btn-fullscreen" onclick="toggleFullscreen('card-iso-acc-z', 'chart-iso-acc-z')" title="Phóng to đồ thị này">⛶ Toàn màn hình</button>
                    </div>
                </div>
                <div id="chart-iso-acc-z" class="chart-box" style="height: 240px;"></div>
            </div>

            <!-- Card Gyro X -->
            <div class="axis-card" id="card-iso-gyro-x">
                <div class="axis-card-header">
                    <div class="card-title" style="color: #fb923c;">
                        <span>🟠 VẬN TỐC GÓC GYRO X (°/s)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="axis-badge" style="background: rgba(251, 146, 60, 0.15); color: #fb923c;">GYRO-X</span>
                        <button class="btn-fullscreen" onclick="toggleFullscreen('card-iso-gyro-x', 'chart-iso-gyro-x')" title="Phóng to đồ thị này">⛶ Toàn màn hình</button>
                    </div>
                </div>
                <div id="chart-iso-gyro-x" class="chart-box" style="height: 240px;"></div>
            </div>

            <!-- Card Gyro Y -->
            <div class="axis-card" id="card-iso-gyro-y">
                <div class="axis-card-header">
                    <div class="card-title" style="color: #c084fc;">
                        <span>🟣 VẬN TỐC GÓC GYRO Y (°/s)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="axis-badge" style="background: rgba(192, 132, 252, 0.15); color: #c084fc;">GYRO-Y</span>
                        <button class="btn-fullscreen" onclick="toggleFullscreen('card-iso-gyro-y', 'chart-iso-gyro-y')" title="Phóng to đồ thị này">⛶ Toàn màn hình</button>
                    </div>
                </div>
                <div id="chart-iso-gyro-y" class="chart-box" style="height: 240px;"></div>
            </div>

            <!-- Card Gyro Z -->
            <div class="axis-card" id="card-iso-gyro-z">
                <div class="axis-card-header">
                    <div class="card-title" style="color: #f43f5e;">
                        <span>🔴 VẬN TỐC GÓC GYRO Z (°/s)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="axis-badge" style="background: rgba(244, 63, 94, 0.15); color: #f43f5e;">GYRO-Z</span>
                        <button class="btn-fullscreen" onclick="toggleFullscreen('card-iso-gyro-z', 'chart-iso-gyro-z')" title="Phóng to đồ thị này">⛶ Toàn màn hình</button>
                    </div>
                </div>
                <div id="chart-iso-gyro-z" class="chart-box" style="height: 240px;"></div>
            </div>
        </div>

        <!-- ==================== TAB 3: TỔNG QUAN TOÀN DIỆN ==================== -->
        <div id="tab-overview" class="tab-pane">
            <div class="hint-box">
                <span>💡 <strong>Tổng quan phân nhóm:</strong> 🖱️ <strong>Cuộn chuột</strong> để Zoom (Mặc định XY) • ⌨️ <strong>Shift + Cuộn</strong> (Zoom X) • <strong>Ctrl/Alt + Cuộn</strong> (Zoom Y) • 🖐️ <strong>Kéo chuột</strong> để Pan • 🔄 <strong>Nhấp đúp</strong> để Reset!</span>
                <div style="display: flex; gap: 8px;">
                    <button class="btn-tab-fullscreen" onclick="toggleTabFullscreen('tab-overview')">📺 Phóng to toàn bộ Tab 3 để so sánh</button>
                </div>
            </div>

            <!-- Card Gia Tốc -->
            <div class="axis-card" id="card-overview-acc">
                <div class="axis-card-header">
                    <div class="card-title" style="color: var(--primary);">
                        <span>📈 GIA TỐC: Acc X, Acc Y, Acc Z & Độ Lớn Toàn Phần |Acc| (g)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="axis-badge" style="background: rgba(56, 189, 248, 0.15); color: var(--primary);">ACCEL</span>
                        <button class="btn-fullscreen" onclick="toggleFullscreen('card-overview-acc', 'chart-overview-acc')" title="Phóng to đồ thị này">⛶ Toàn màn hình</button>
                    </div>
                </div>
                <div id="chart-overview-acc" class="chart-box"></div>
            </div>

            <!-- Card Vận Tốc Góc -->
            <div class="axis-card" id="card-overview-gyro">
                <div class="axis-card-header">
                    <div class="card-title" style="color: var(--gyro-x);">
                        <span>🌀 VẬN TỐC GÓC: Gyro X, Gyro Y, Gyro Z & Độ Lớn Toàn Phần |Gyro| (°/s)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="axis-badge" style="background: rgba(251, 146, 60, 0.15); color: var(--gyro-x);">GYRO</span>
                        <button class="btn-fullscreen" onclick="toggleFullscreen('card-overview-gyro', 'chart-overview-gyro')" title="Phóng to đồ thị này">⛶ Toàn màn hình</button>
                    </div>
                </div>
                <div id="chart-overview-gyro" class="chart-box"></div>
            </div>

            <!-- Card Nhiệt Độ -->
            <div class="axis-card" id="card-overview-temp">
                <div class="axis-card-header">
                    <div class="card-title" style="color: var(--accent-purple);">
                        <span>🌡️ NHIỆT ĐỘ CẢM BIẾN (°C)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="axis-badge" style="background: rgba(192, 132, 252, 0.15); color: var(--accent-purple);">TEMP</span>
                        <button class="btn-fullscreen" onclick="toggleFullscreen('card-overview-temp', 'chart-overview-temp')" title="Phóng to đồ thị này">⛶ Toàn màn hình</button>
                    </div>
                </div>
                <div id="chart-overview-temp" class="chart-box" style="height: 250px;"></div>
            </div>

            <!-- Card Nút Bấm -->
            <div class="axis-card" id="card-overview-btn">
                <div class="axis-card-header">
                    <div class="card-title" style="color: var(--accent-pink);">
                        <span>🔘 TRẠNG THÁI NÚT BẤM (BUTTON EVENTS)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="axis-badge" style="background: rgba(244, 114, 182, 0.15); color: var(--accent-pink);">BUTTON</span>
                        <button class="btn-fullscreen" onclick="toggleFullscreen('card-overview-btn', 'chart-overview-btn')" title="Phóng to đồ thị này">⛶ Toàn màn hình</button>
                    </div>
                </div>
                <div id="chart-overview-btn" class="chart-box-btn"></div>
            </div>
        </div>

        <!-- ==================== TAB 4: QUỸ ĐẠO 3D & PHỔ TẦN SỐ FFT ==================== -->
        <div id="tab-3d-fft" class="tab-pane">
            <div class="hint-box">
                <span>🌐 <strong>Phân tích không gian & tần số:</strong> 🖱️ <strong>Cuộn chuột</strong> để zoom • 🖐️ <strong>Nhấn giữ & kéo chuột</strong> để xoay 3D / Pan FFT!</span>
                <div style="display: flex; gap: 8px;">
                    <button class="btn-tab-fullscreen" onclick="toggleTabFullscreen('tab-3d-fft')">📺 Phóng to cả 3D & FFT để so sánh</button>
                </div>
            </div>

            <div class="grid-2col">
                <div class="card" id="card-3d">
                    <div class="card-header">
                        <div>
                            <div class="card-title">🌐 Quỹ Đạo Gia Tốc Không Gian 3D (Acc X, Y, Z theo đơn vị g)</div>
                            <span class="card-desc">Kéo chuột để xoay góc nhìn 3D • Cuộn chuột để zoom</span>
                        </div>
                        <button class="btn-fullscreen" onclick="toggleFullscreen('card-3d', 'chart-3d')" title="Phóng to đồ thị này">⛶ Toàn màn hình</button>
                    </div>
                    <div id="chart-3d" class="plot-container-sm"></div>
                </div>
                <div class="card" id="card-fft">
                    <div class="card-header">
                        <div>
                            <div class="card-title">⚡ Phổ Tần Số FFT (Gia Tốc g & Vận Tốc Góc °/s)</div>
                            <span class="card-desc">Phân tích tần số dao động (0 - {fs/2:.1f}Hz) • Cuộn chuột để zoom</span>
                        </div>
                        <button class="btn-fullscreen" onclick="toggleFullscreen('card-fft', 'chart-fft')" title="Phóng to đồ thị này">⛶ Toàn màn hình</button>
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
        let syncTimeout = null;

        const renderedTabs = {{
            'tab-axes': false,
            'tab-isolated': false,
            'tab-overview': false,
            'tab-3d-fft': false
        }};

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

        // Base Layout Theme: dragmode is set to 'pan' (Click and Drag to Pan / Translate)
        const baseTheme = {{
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'rgba(15, 23, 42, 0.55)',
            font: {{ color: '#cbd5e1', family: 'Plus Jakarta Sans' }},
            hovermode: 'x unified',
            hoverlabel: {{ bgcolor: '#1e293b', font: {{ family: 'JetBrains Mono', size: 12 }} }},
            dragmode: 'pan'
        }};

        // Plotly Global Configuration (Enabled Mouse Wheel Scroll Zoom + Pan Drag)
        const plotlyConfig = {{
            scrollZoom: true,
            responsive: true,
            displaylogo: false,
            modeBarButtonsToRemove: ['lasso2d', 'select2d', 'zoom2d']
        }};

        // Smooth non-blocking group zoom synchronization
        function setupGroupZoomSync(groupChartIds) {{
            groupChartIds.forEach(sourceId => {{
                const el = document.getElementById(sourceId);
                if (!el) return;

                el.on('plotly_relayout', function(eventdata) {{
                    if (isSyncing) return;
                    if (eventdata['xaxis.range[0]'] === undefined && eventdata['xaxis.autorange'] === undefined) return;

                    isSyncing = true;
                    if (syncTimeout) clearTimeout(syncTimeout);

                    const update = {{}};
                    if (eventdata['xaxis.range[0]'] !== undefined) {{
                        update['xaxis.range'] = [eventdata['xaxis.range[0]'], eventdata['xaxis.range[1]']];
                        update['xaxis.autorange'] = false;
                    }} else {{
                        update['xaxis.autorange'] = true;
                    }}

                    groupChartIds.forEach(targetId => {{
                        if (targetId !== sourceId) {{
                            const targetEl = document.getElementById(targetId);
                            if (targetEl && targetEl.data) {{
                                Plotly.relayout(targetId, update);
                            }}
                        }}
                    }});

                    syncTimeout = setTimeout(() => {{
                        isSyncing = false;
                    }}, 25);
                }});
            }});
        }}

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
            Plotly.newPlot('chart-axis-x', [traceAccX, traceGyroX], axisCommonLayout('Acc X (g)', 'Gyro X (°/s)', '#38bdf8', '#fb923c'), plotlyConfig);
            attachWheelZoomListener('chart-axis-x');

            // --- Trục Y ---
            const traceAccY = {{ x: time, y: rawData.acc_y, name: 'Gia tốc Acc Y (g)', line: {{ color: '#34d399', width: 1.8 }} }};
            const traceGyroY = {{ x: time, y: rawData.gyro_y, name: 'Vận tốc góc Gyro Y (°/s)', yaxis: 'y2', line: {{ color: '#c084fc', width: 1.6, dash: 'solid' }} }};
            Plotly.newPlot('chart-axis-y', [traceAccY, traceGyroY], axisCommonLayout('Acc Y (g)', 'Gyro Y (°/s)', '#34d399', '#c084fc'), plotlyConfig);
            attachWheelZoomListener('chart-axis-y');

            // --- Trục Z ---
            const traceAccZ = {{ x: time, y: rawData.acc_z, name: 'Gia tốc Acc Z (g)', line: {{ color: '#fbbf24', width: 1.8 }} }};
            const traceGyroZ = {{ x: time, y: rawData.gyro_z, name: 'Vận tốc góc Gyro Z (°/s)', yaxis: 'y2', line: {{ color: '#f43f5e', width: 1.6, dash: 'solid' }} }};
            Plotly.newPlot('chart-axis-z', [traceAccZ, traceGyroZ], axisCommonLayout('Acc Z (g)', 'Gyro Z (°/s)', '#fbbf24', '#f43f5e'), plotlyConfig);
            attachWheelZoomListener('chart-axis-z');

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
            Plotly.newPlot('chart-axis-btn', [traceBtn, traceTemp], btnLayout, plotlyConfig);
            attachWheelZoomListener('chart-axis-btn');

            // Đồng bộ hóa Zoom giữa 4 biểu đồ Tab 1
            setupGroupZoomSync(['chart-axis-x', 'chart-axis-y', 'chart-axis-z', 'chart-axis-btn']);
        }}

        // ==================== 2. RENDER TAB 2: 6 SEPARATE ISOLATED CARDS ====================
        function renderIsolatedTab() {{
            const commonIsoLayout = (titleY, color) => ({{
                ...baseTheme,
                margin: {{ l: 65, r: 35, t: 10, b: 35 }},
                shapes: btnShapes,
                xaxis: {{
                    title: 'Thời gian (giây)',
                    gridcolor: 'rgba(255, 255, 255, 0.06)',
                    showgrid: true,
                    zeroline: true,
                    zerolinecolor: 'rgba(255,255,255,0.15)'
                }},
                yaxis: {{
                    title: titleY,
                    titlefont: {{ color: color, size: 12 }},
                    tickfont: {{ color: color }},
                    gridcolor: 'rgba(255, 255, 255, 0.06)',
                    zerolinecolor: 'rgba(255,255,255,0.1)'
                }},
                legend: {{
                    orientation: 'h',
                    x: 0.01,
                    y: 1.18,
                    font: {{ size: 11 }},
                    bgcolor: 'rgba(15, 23, 42, 0.7)'
                }}
            }});

            const traceAccX = {{ x: time, y: rawData.acc_x, name: 'Gia tốc Acc X (g)', line: {{ color: '#38bdf8', width: 1.8 }} }};
            Plotly.newPlot('chart-iso-acc-x', [traceAccX], commonIsoLayout('Acc X (g)', '#38bdf8'), plotlyConfig);
            attachWheelZoomListener('chart-iso-acc-x');

            const traceAccY = {{ x: time, y: rawData.acc_y, name: 'Gia tốc Acc Y (g)', line: {{ color: '#34d399', width: 1.8 }} }};
            Plotly.newPlot('chart-iso-acc-y', [traceAccY], commonIsoLayout('Acc Y (g)', '#34d399'), plotlyConfig);
            attachWheelZoomListener('chart-iso-acc-y');

            const traceAccZ = {{ x: time, y: rawData.acc_z, name: 'Gia tốc Acc Z (g)', line: {{ color: '#fbbf24', width: 1.8 }} }};
            Plotly.newPlot('chart-iso-acc-z', [traceAccZ], commonIsoLayout('Acc Z (g)', '#fbbf24'), plotlyConfig);
            attachWheelZoomListener('chart-iso-acc-z');

            const traceGyroX = {{ x: time, y: rawData.gyro_x, name: 'Vận tốc góc Gyro X (°/s)', line: {{ color: '#fb923c', width: 1.8 }} }};
            Plotly.newPlot('chart-iso-gyro-x', [traceGyroX], commonIsoLayout('Gyro X (°/s)', '#fb923c'), plotlyConfig);
            attachWheelZoomListener('chart-iso-gyro-x');

            const traceGyroY = {{ x: time, y: rawData.gyro_y, name: 'Vận tốc góc Gyro Y (°/s)', line: {{ color: '#c084fc', width: 1.8 }} }};
            Plotly.newPlot('chart-iso-gyro-y', [traceGyroY], commonIsoLayout('Gyro Y (°/s)', '#c084fc'), plotlyConfig);
            attachWheelZoomListener('chart-iso-gyro-y');

            const traceGyroZ = {{ x: time, y: rawData.gyro_z, name: 'Vận tốc góc Gyro Z (°/s)', line: {{ color: '#f43f5e', width: 1.8 }} }};
            Plotly.newPlot('chart-iso-gyro-z', [traceGyroZ], commonIsoLayout('Gyro Z (°/s)', '#f43f5e'), plotlyConfig);
            attachWheelZoomListener('chart-iso-gyro-z');

            // Đồng bộ hóa Zoom giữa 6 kênh Tab 2
            setupGroupZoomSync(['chart-iso-acc-x', 'chart-iso-acc-y', 'chart-iso-acc-z', 'chart-iso-gyro-x', 'chart-iso-gyro-y', 'chart-iso-gyro-z']);
        }}

        // ==================== 3. RENDER TAB 3: SEPARATE OVERVIEW CHARTS ====================
        function renderOverviewTab() {{
            const commonOverviewLayout = (titleY, color) => ({{
                ...baseTheme,
                margin: {{ l: 65, r: 35, t: 15, b: 35 }},
                shapes: btnShapes,
                xaxis: {{
                    gridcolor: 'rgba(255, 255, 255, 0.06)',
                    showgrid: true,
                    zeroline: true,
                    zerolinecolor: 'rgba(255,255,255,0.15)'
                }},
                yaxis: {{
                    title: titleY,
                    titlefont: {{ color: color, size: 12 }},
                    tickfont: {{ color: color }},
                    gridcolor: 'rgba(255, 255, 255, 0.06)',
                    zerolinecolor: 'rgba(255,255,255,0.1)'
                }},
                legend: {{
                    orientation: 'h',
                    x: 0.01,
                    y: 1.14,
                    font: {{ size: 11 }},
                    bgcolor: 'rgba(15, 23, 42, 0.7)'
                }}
            }});

            // 1. Gia tốc
            const traceAccX = {{ x: time, y: rawData.acc_x, name: 'Acc X (g)', line: {{ color: '#38bdf8', width: 1.6 }} }};
            const traceAccY = {{ x: time, y: rawData.acc_y, name: 'Acc Y (g)', line: {{ color: '#34d399', width: 1.6 }} }};
            const traceAccZ = {{ x: time, y: rawData.acc_z, name: 'Acc Z (g)', line: {{ color: '#fbbf24', width: 1.6 }} }};
            const traceAccMag = {{ x: time, y: rawData.acc_mag, name: '|Acc| Toàn phần (g)', line: {{ color: '#f87171', width: 1.8, dash: 'dot' }} }};
            Plotly.newPlot('chart-overview-acc', [traceAccX, traceAccY, traceAccZ, traceAccMag], commonOverviewLayout('Gia tốc (g)', '#38bdf8'), plotlyConfig);
            attachWheelZoomListener('chart-overview-acc');

            // 2. Vận tốc góc
            const traceGyroX = {{ x: time, y: rawData.gyro_x, name: 'Gyro X (°/s)', line: {{ color: '#fb923c', width: 1.6 }} }};
            const traceGyroY = {{ x: time, y: rawData.gyro_y, name: 'Gyro Y (°/s)', line: {{ color: '#c084fc', width: 1.6 }} }};
            const traceGyroZ = {{ x: time, y: rawData.gyro_z, name: 'Gyro Z (°/s)', line: {{ color: '#f43f5e', width: 1.6 }} }};
            const traceGyroMag = {{ x: time, y: rawData.gyro_mag, name: '|Gyro| Toàn phần (°/s)', line: {{ color: '#f87171', width: 1.8, dash: 'dot' }} }};
            Plotly.newPlot('chart-overview-gyro', [traceGyroX, traceGyroY, traceGyroZ, traceGyroMag], commonOverviewLayout('Vận tốc góc (°/s)', '#fb923c'), plotlyConfig);
            attachWheelZoomListener('chart-overview-gyro');

            // 3. Nhiệt độ
            const traceTemp = {{ x: time, y: rawData.temp, name: 'Nhiệt độ (°C)', line: {{ color: '#a78bfa', width: 1.8 }} }};
            Plotly.newPlot('chart-overview-temp', [traceTemp], commonOverviewLayout('Nhiệt độ (°C)', '#a78bfa'), plotlyConfig);
            attachWheelZoomListener('chart-overview-temp');

            // 4. Nút bấm
            const traceBtn = {{ 
                x: time, y: rawData.button, name: 'Trạng thái nút bấm', 
                line: {{ color: '#f472b6', width: 2, shape: 'hv' }}, 
                fill: 'tozeroy', fillcolor: 'rgba(244, 114, 182, 0.22)' 
            }};
            const btnLayout = {{
                ...baseTheme,
                margin: {{ l: 65, r: 35, t: 10, b: 40 }},
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
                legend: {{
                    orientation: 'h',
                    x: 0.01,
                    y: 1.25,
                    font: {{ size: 11 }},
                    bgcolor: 'rgba(15, 23, 42, 0.7)'
                }}
            }};
            Plotly.newPlot('chart-overview-btn', [traceBtn], btnLayout, plotlyConfig);
            attachWheelZoomListener('chart-overview-btn');

            // Đồng bộ hóa Zoom giữa 4 biểu đồ Tab 3
            setupGroupZoomSync(['chart-overview-acc', 'chart-overview-gyro', 'chart-overview-temp', 'chart-overview-btn']);
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
            Plotly.newPlot('chart-3d', [trace3d], layout3d, plotlyConfig);

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

            Plotly.newPlot('chart-fft', [traceAccFFT, traceGyroFFT], layoutFFT, plotlyConfig);
        }}

        // ==================== SMART CONTROLS & ZOOM ENGINES ====================
        const maxTime = {duration_s:.2f};
        let currentZoomMode = 'xy'; // 'xy', 'x', 'y'

        function setZoomMode(mode, btn) {{
            currentZoomMode = mode;
            document.querySelectorAll('.btn-zoom-mode').forEach(b => b.classList.remove('active'));
            if (btn) {{
                btn.classList.add('active');
            }} else {{
                const targetBtn = document.getElementById('btn-mode-' + mode);
                if (targetBtn) targetBtn.classList.add('active');
            }}
        }}

        // Reset toàn bộ Zoom (cả trục X và tất cả trục Y)
        function resetAllZoom(targetChartId = null) {{
            let plots = [];
            if (targetChartId) {{
                const el = document.getElementById(targetChartId);
                if (el) plots = [el];
            }} else {{
                const activeTab = document.querySelector('.tab-pane.active');
                if (activeTab) plots = Array.from(activeTab.querySelectorAll('.js-plotly-plot, [id^="chart-"]'));
            }}
            plots.forEach(el => {{
                if (el.id && el.data) {{
                    Plotly.relayout(el.id, {{
                        'xaxis.autorange': true,
                        'yaxis.autorange': true,
                        'yaxis2.autorange': true
                    }});
                }}
            }});
        }}

        // Kéo dãn / Thu hẹp CHIỀU NGANG (Trục thời gian X)
        function stretchX(factor, targetChartId = null) {{
            let plots = [];
            if (targetChartId) {{
                const el = document.getElementById(targetChartId);
                if (el) plots = [el];
            }} else {{
                const activeTab = document.querySelector('.tab-pane.active');
                if (activeTab) plots = Array.from(activeTab.querySelectorAll('.js-plotly-plot, [id^="chart-"]'));
            }}
            if (plots.length === 0) return;

            const firstPlot = plots[0];
            let r0 = 0, r1 = maxTime;
            if (firstPlot.layout && firstPlot.layout.xaxis && firstPlot.layout.xaxis.range) {{
                r0 = firstPlot.layout.xaxis.range[0];
                r1 = firstPlot.layout.xaxis.range[1];
            }}

            const center = (r0 + r1) / 2.0;
            let halfSpan = ((r1 - r0) / 2.0) / factor;
            if (halfSpan < 0.05) halfSpan = 0.05;
            if (halfSpan > maxTime / 2.0) halfSpan = maxTime / 2.0;

            let newR0 = center - halfSpan;
            let newR1 = center + halfSpan;
            if (newR0 < 0) {{
                newR1 += (0 - newR0);
                newR0 = 0;
            }}
            if (newR1 > maxTime) {{
                newR0 -= (newR1 - maxTime);
                newR1 = maxTime;
                if (newR0 < 0) newR0 = 0;
            }}

            plots.forEach(el => {{
                if (el.id && el.data) {{
                    Plotly.relayout(el.id, {{
                        'xaxis.range': [newR0, newR1],
                        'xaxis.autorange': false
                    }});
                }}
            }});
        }}

        // Kéo dãn / Thu hẹp CHIỀU DỌC (Trục biên độ Y và Y2)
        function stretchY(factor, targetChartId = null) {{
            let plots = [];
            if (targetChartId) {{
                const el = document.getElementById(targetChartId);
                if (el) plots = [el];
            }} else {{
                const activeTab = document.querySelector('.tab-pane.active');
                if (activeTab) plots = Array.from(activeTab.querySelectorAll('.js-plotly-plot, [id^="chart-"]'));
            }}
            
            plots.forEach(el => {{
                if (!el.id || !el.data || !el.layout) return;
                const layout = el.layout;
                const update = {{}};

                // 1. Trục Y chính
                if (layout.yaxis) {{
                    let y0, y1;
                    if (layout.yaxis.range && !layout.yaxis.autorange) {{
                        y0 = layout.yaxis.range[0];
                        y1 = layout.yaxis.range[1];
                    }} else {{
                        const vals = [];
                        el.data.forEach(tr => {{
                            if ((!tr.yaxis || tr.yaxis === 'y') && tr.y) {{
                                vals.push(...tr.y);
                            }}
                        }});
                        if (vals.length > 0) {{
                            const minV = Math.min(...vals);
                            const maxV = Math.max(...vals);
                            const pad = Math.max(0.1, (maxV - minV) * 0.12);
                            y0 = minV - pad;
                            y1 = maxV + pad;
                        }} else {{
                            y0 = -1; y1 = 1;
                        }}
                    }}
                    const center = (y0 + y1) / 2.0;
                    const half = ((y1 - y0) / 2.0) / factor;
                    update['yaxis.range'] = [center - half, center + half];
                    update['yaxis.autorange'] = false;
                }}

                // 2. Trục Y phụ (Y2 nếu có)
                if (layout.yaxis2) {{
                    let y2_0, y2_1;
                    if (layout.yaxis2.range && !layout.yaxis2.autorange) {{
                        y2_0 = layout.yaxis2.range[0];
                        y2_1 = layout.yaxis2.range[1];
                    }} else {{
                        const vals2 = [];
                        el.data.forEach(tr => {{
                            if (tr.yaxis === 'y2' && tr.y) {{
                                vals2.push(...tr.y);
                            }}
                        }});
                        if (vals2.length > 0) {{
                            const minV = Math.min(...vals2);
                            const maxV = Math.max(...vals2);
                            const pad = Math.max(0.1, (maxV - minV) * 0.12);
                            y2_0 = minV - pad;
                            y2_1 = maxV + pad;
                        }} else {{
                            y2_0 = -10; y2_1 = 10;
                        }}
                    }}
                    const center2 = (y2_0 + y2_1) / 2.0;
                    const half2 = ((y2_1 - y2_0) / 2.0) / factor;
                    update['yaxis2.range'] = [center2 - half2, center2 + half2];
                    update['yaxis2.autorange'] = false;
                }}

                Plotly.relayout(el.id, update);
            }});
        }}

        // Tự động căn chỉnh biên độ Y vừa vặn
        function autoFitY(targetChartId = null) {{
            let plots = [];
            if (targetChartId) {{
                const el = document.getElementById(targetChartId);
                if (el) plots = [el];
            }} else {{
                const activeTab = document.querySelector('.tab-pane.active');
                if (activeTab) plots = Array.from(activeTab.querySelectorAll('.js-plotly-plot, [id^="chart-"]'));
            }}
            plots.forEach(el => {{
                if (el.id && el.data) {{
                    Plotly.relayout(el.id, {{
                        'yaxis.autorange': true,
                        'yaxis2.autorange': true
                    }});
                }}
            }});
        }}

        // Đặt kích thước cửa sổ thời gian cố định (2s, 5s, 10s...)
        function setTimeWindow(spanSec, targetChartId = null) {{
            let plots = [];
            if (targetChartId) {{
                const el = document.getElementById(targetChartId);
                if (el) plots = [el];
            }} else {{
                const activeTab = document.querySelector('.tab-pane.active');
                if (activeTab) plots = Array.from(activeTab.querySelectorAll('.js-plotly-plot, [id^="chart-"]'));
            }}
            if (plots.length === 0) return;

            const firstPlot = plots[0];
            let center = maxTime / 2.0;
            if (firstPlot.layout && firstPlot.layout.xaxis && firstPlot.layout.xaxis.range) {{
                center = (firstPlot.layout.xaxis.range[0] + firstPlot.layout.xaxis.range[1]) / 2.0;
            }}

            let half = spanSec / 2.0;
            let newR0 = Math.max(0, center - half);
            let newR1 = Math.min(maxTime, center + half);
            if (newR1 - newR0 < spanSec) {{
                if (newR0 === 0) newR1 = Math.min(maxTime, spanSec);
                else if (newR1 === maxTime) newR0 = Math.max(0, maxTime - spanSec);
            }}

            plots.forEach(el => {{
                if (el.id && el.data) {{
                    Plotly.relayout(el.id, {{
                        'xaxis.range': [newR0, newR1],
                        'xaxis.autorange': false
                    }});
                }}
            }});
        }}

        // Dịch chuyển thời gian sang trái / phải
        function panTime(deltaPercent, targetChartId = null) {{
            let plots = [];
            if (targetChartId) {{
                const el = document.getElementById(targetChartId);
                if (el) plots = [el];
            }} else {{
                const activeTab = document.querySelector('.tab-pane.active');
                if (activeTab) plots = Array.from(activeTab.querySelectorAll('.js-plotly-plot, [id^="chart-"]'));
            }}
            if (plots.length === 0) return;

            const firstPlot = plots[0];
            let r0 = 0, r1 = maxTime;
            if (firstPlot.layout && firstPlot.layout.xaxis && firstPlot.layout.xaxis.range) {{
                r0 = firstPlot.layout.xaxis.range[0];
                r1 = firstPlot.layout.xaxis.range[1];
            }}

            const span = r1 - r0;
            const shift = span * deltaPercent;
            let newR0 = r0 + shift;
            let newR1 = r1 + shift;

            if (newR0 < 0) {{
                newR1 = span;
                newR0 = 0;
            }}
            if (newR1 > maxTime) {{
                newR0 = Math.max(0, maxTime - span);
                newR1 = maxTime;
            }}

            plots.forEach(el => {{
                if (el.id && el.data) {{
                    Plotly.relayout(el.id, {{
                        'xaxis.range': [newR0, newR1],
                        'xaxis.autorange': false
                    }});
                }}
            }});
        }}

        // Lắng nghe thao tác cuộn chuột thông minh (hỗ trợ Shift = Zoom X, Ctrl/Alt = Zoom Y)
        function attachWheelZoomListener(chartId) {{
            const el = document.getElementById(chartId);
            if (!el) return;

            el.addEventListener('wheel', function(e) {{
                let mode = currentZoomMode;
                if (e.shiftKey) mode = 'x';
                else if (e.ctrlKey || e.altKey) mode = 'y';

                if (mode === 'xy') {{
                    // Để Plotly xử lý cuộn phóng to 2D tự nhiên
                    return;
                }}

                // Nếu là chế độ riêng lẻ X hoặc Y, chặn cuộn 2D và áp dụng zoom riêng
                e.preventDefault();
                e.stopPropagation();

                const factor = e.deltaY < 0 ? 1.25 : 0.8;
                if (mode === 'x') {{
                    stretchX(factor, chartId);
                }} else if (mode === 'y') {{
                    stretchY(factor, chartId);
                }}
            }}, {{ passive: false }});
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
            const pad = 0.8; // 0.8s padding
            const startT = Math.max(0, ev.t_start - pad);
            const endT = Math.min(maxTime, ev.t_end + pad);
            const activeTab = document.querySelector('.tab-pane.active');
            if (activeTab) {{
                const plots = activeTab.querySelectorAll('.js-plotly-plot, [id^="chart-"]');
                plots.forEach(el => {{
                    if (el.id && el.data) {{
                        Plotly.relayout(el.id, {{ 'xaxis.range': [startT, endT], 'xaxis.autorange': false }});
                    }}
                }});
            }}
            document.getElementById('btn-event-counter').innerText = `${{ev.event_id}} / ${{buttonEvents.length}} (${{ev.duration}}s)`;
        }}

        // Tab Switching Logic (On-Demand Lazy Rendering for Instant Performance)
        function switchTab(tabId, btn) {{
            document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            
            document.getElementById(tabId).classList.add('active');
            if (btn) btn.classList.add('active');

            if (!renderedTabs[tabId]) {{
                if (tabId === 'tab-axes') renderAxesTab();
                else if (tabId === 'tab-isolated') renderIsolatedTab();
                else if (tabId === 'tab-overview') renderOverviewTab();
                else if (tabId === 'tab-3d-fft') render3DAndFFT();
                renderedTabs[tabId] = true;
            }} else {{
                setTimeout(() => {{
                    if (tabId === 'tab-axes') {{
                        Plotly.Plots.resize('chart-axis-x');
                        Plotly.Plots.resize('chart-axis-y');
                        Plotly.Plots.resize('chart-axis-z');
                        Plotly.Plots.resize('chart-axis-btn');
                    }} else if (tabId === 'tab-isolated') {{
                        Plotly.Plots.resize('chart-iso-acc-x');
                        Plotly.Plots.resize('chart-iso-acc-y');
                        Plotly.Plots.resize('chart-iso-acc-z');
                        Plotly.Plots.resize('chart-iso-gyro-x');
                        Plotly.Plots.resize('chart-iso-gyro-y');
                        Plotly.Plots.resize('chart-iso-gyro-z');
                    }} else if (tabId === 'tab-overview') {{
                        Plotly.Plots.resize('chart-overview-acc');
                        Plotly.Plots.resize('chart-overview-gyro');
                        Plotly.Plots.resize('chart-overview-temp');
                        Plotly.Plots.resize('chart-overview-btn');
                    }} else if (tabId === 'tab-3d-fft') {{
                        Plotly.Plots.resize('chart-3d');
                        Plotly.Plots.resize('chart-fft');
                    }}
                }}, 30);
            }}
        }}

        // Fullscreen Single Card Toggle Logic
        function toggleFullscreen(cardId, chartId) {{
            const card = document.getElementById(cardId);
            if (!card) return;
            
            const isFull = card.classList.contains('is-fullscreen');
            const btn = card.querySelector('.btn-fullscreen');
            
            if (isFull) {{
                card.classList.remove('is-fullscreen');
                document.body.classList.remove('fullscreen-active');
                if (btn) btn.innerHTML = '⛶ Toàn màn hình';
                const fsControls = card.querySelector('.single-fs-toolbar');
                if (fsControls) fsControls.remove();
            }} else {{
                document.querySelectorAll('.is-fullscreen').forEach(el => {{
                    el.classList.remove('is-fullscreen');
                    const b = el.querySelector('.btn-fullscreen');
                    if (b) b.innerHTML = '⛶ Toàn màn hình';
                    const oldC = el.querySelector('.single-fs-toolbar');
                    if (oldC) oldC.remove();
                }});
                card.classList.add('is-fullscreen');
                document.body.classList.add('fullscreen-active');
                if (btn) btn.innerHTML = '✕ Thu nhỏ (Esc)';

                // Thêm thanh công cụ Zoom vào tiêu đề thẻ khi phóng to toàn màn hình
                const header = card.querySelector('.axis-card-header') || card.querySelector('.card-header');
                if (header && !header.querySelector('.single-fs-toolbar')) {{
                    const fsBar = document.createElement('div');
                    fsBar.className = 'single-fs-toolbar';
                    fsBar.style = 'display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-left:auto; margin-right:12px;';
                    fsBar.innerHTML = `
                        <button class="btn btn-primary" style="padding:4px 8px; font-size:11px;" onclick="resetAllZoom('${{chartId}}')">🔄 Reset</button>
                        <button class="btn" style="padding:4px 8px; font-size:11px;" onclick="stretchX(1.4, '${{chartId}}')">↔️➕ Dãn X</button>
                        <button class="btn" style="padding:4px 8px; font-size:11px;" onclick="stretchX(0.71, '${{chartId}}')">↔️➖ Thu X</button>
                        <button class="btn" style="padding:4px 8px; font-size:11px;" onclick="stretchY(1.4, '${{chartId}}')">↕️➕ Dãn Y</button>
                        <button class="btn" style="padding:4px 8px; font-size:11px;" onclick="stretchY(0.71, '${{chartId}}')">↕️➖ Thu Y</button>
                        <button class="btn" style="padding:4px 8px; font-size:11px;" onclick="autoFitY('${{chartId}}')">↕️ Auto Y</button>
                        <button class="btn" style="padding:4px 8px; font-size:11px;" onclick="setTimeWindow(2.0, '${{chartId}}')">⏱️ 2s</button>
                        <button class="btn" style="padding:4px 8px; font-size:11px;" onclick="setTimeWindow(5.0, '${{chartId}}')">⏱️ 5s</button>
                    `;
                    const rightContainer = header.lastElementChild;
                    header.insertBefore(fsBar, rightContainer);
                }}
            }}
            
            const chartEl = document.getElementById(chartId);
            if (chartEl) {{
                setTimeout(() => {{
                    Plotly.Plots.resize(chartEl);
                    Plotly.relayout(chartEl, {{ autosize: true }});
                }}, 40);
            }}
        }}

        // Fullscreen Entire Tab Comparison Logic
        function toggleTabFullscreen(tabId) {{
            const tab = document.getElementById(tabId);
            if (!tab) return;

            // Ensure tab is rendered first
            if (!renderedTabs[tabId]) {{
                if (tabId === 'tab-axes') renderAxesTab();
                else if (tabId === 'tab-isolated') renderIsolatedTab();
                else if (tabId === 'tab-overview') renderOverviewTab();
                else if (tabId === 'tab-3d-fft') render3DAndFFT();
                renderedTabs[tabId] = true;
            }}

            const isFull = tab.classList.contains('is-tab-fullscreen');
            
            // Close single card fullscreen
            document.querySelectorAll('.is-fullscreen').forEach(el => {{
                el.classList.remove('is-fullscreen');
                const b = el.querySelector('.btn-fullscreen');
                if (b) b.innerHTML = '⛶ Toàn màn hình';
                const oldC = el.querySelector('.single-fs-toolbar');
                if (oldC) oldC.remove();
            }});

            if (isFull) {{
                tab.classList.remove('is-tab-fullscreen');
                document.body.classList.remove('fullscreen-active');
                const oldH = tab.querySelector('.tab-fullscreen-header');
                if (oldH) oldH.remove();
            }} else {{
                // Close other tab fullscreens
                document.querySelectorAll('.is-tab-fullscreen').forEach(el => {{
                    el.classList.remove('is-tab-fullscreen');
                    const oldH = el.querySelector('.tab-fullscreen-header');
                    if (oldH) oldH.remove();
                }});

                tab.classList.add('is-tab-fullscreen');
                document.body.classList.add('fullscreen-active');

                // Add sticky top comparison control bar
                let fsHeader = tab.querySelector('.tab-fullscreen-header');
                if (!fsHeader) {{
                    fsHeader = document.createElement('div');
                    fsHeader.className = 'tab-fullscreen-header';
                    fsHeader.innerHTML = `
                        <div style="display:flex; align-items:center; gap:10px;">
                            <span style="font-weight:800; font-size:15px; color:#38bdf8;">
                                📺 CHẾ ĐỘ SO SÁNH TOÀN BỘ CÁC ĐỒ THỊ TRONG MỤC
                            </span>
                            <span class="badge" style="background:rgba(52,211,153,0.15); color:#34d399;">ĐỒNG BỘ ZOOM 100%</span>
                        </div>
                        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                            <button class="btn btn-primary" onclick="resetAllZoom()">🔄 Reset Zoom</button>
                            <button class="btn" onclick="stretchX(1.4)">↔️➕ Dãn X</button>
                            <button class="btn" onclick="stretchX(0.71)">↔️➖ Thu X</button>
                            <button class="btn" onclick="stretchY(1.4)">↕️➕ Dãn Y</button>
                            <button class="btn" onclick="stretchY(0.71)">↕️➖ Thu Y</button>
                            <button class="btn" onclick="autoFitY()">↕️ Auto Y</button>
                            <button class="btn" onclick="setTimeWindow(2.0)">⏱️ 2s</button>
                            <button class="btn" onclick="setTimeWindow(5.0)">⏱️ 5s</button>
                            <button class="btn" style="background:rgba(244,63,94,0.25); border-color:#f43f5e; color:#fff;" onclick="toggleTabFullscreen('${{tabId}}')">
                                ✕ Thu nhỏ (Esc)
                            </button>
                        </div>
                    `;
                    tab.insertBefore(fsHeader, tab.firstChild);
                }}
            }}

            // Auto resize all Plotly charts inside this tab
            setTimeout(() => {{
                const plots = tab.querySelectorAll('.js-plotly-plot, [id^="chart-"]');
                plots.forEach(p => {{
                    if (p.id) {{
                        Plotly.Plots.resize(p.id);
                        Plotly.relayout(p.id, {{ autosize: true }});
                    }}
                }});
            }}, 40);
        }}

        function toggleCurrentTabFullscreen() {{
            const activeTab = document.querySelector('.tab-pane.active');
            if (activeTab) {{
                toggleTabFullscreen(activeTab.id);
            }}
        }}

        // Key Navigation:
        // + / - : Zoom Chiều Ngang X
        // Shift + (+ / - / Mũi tên lên / xuống) : Zoom Chiều Dọc Y
        // Mũi tên trái / phải : Dịch chuyển thời gian (Pan X)
        // 0 : Reset toàn bộ
        // Esc : Thoát toàn màn hình
        document.addEventListener('keydown', function(e) {{
            if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;

            if (e.shiftKey && (e.key === '+' || e.key === '=' || e.key === 'ArrowUp')) {{
                e.preventDefault();
                stretchY(1.35);
            }} else if (e.shiftKey && (e.key === '-' || e.key === '_' || e.key === 'ArrowDown')) {{
                e.preventDefault();
                stretchY(0.74);
            }} else if (!e.shiftKey && (e.key === '+' || e.key === '=')) {{
                stretchX(1.35);
            }} else if (!e.shiftKey && (e.key === '-' || e.key === '_')) {{
                stretchX(0.74);
            }} else if (!e.shiftKey && e.key === 'ArrowLeft') {{
                panTime(-0.1);
            }} else if (!e.shiftKey && e.key === 'ArrowRight') {{
                panTime(0.1);
            }} else if (e.key === '0') {{
                resetAllZoom();
            }}

            // ESC Key listener to close single card or whole tab fullscreen
            if (e.key === 'Escape' || e.keyCode === 27) {{
                // 1. Check single card fullscreen
                const fullCard = document.querySelector('.is-fullscreen');
                if (fullCard) {{
                    const btn = fullCard.querySelector('.btn-fullscreen');
                    fullCard.classList.remove('is-fullscreen');
                    document.body.classList.remove('fullscreen-active');
                    if (btn) btn.innerHTML = '⛶ Toàn màn hình';
                    
                    const chartDiv = fullCard.querySelector('.js-plotly-plot') || fullCard.querySelector('[id^="chart-"]');
                    if (chartDiv && chartDiv.id) {{
                        setTimeout(() => {{
                            Plotly.Plots.resize(chartDiv.id);
                            Plotly.relayout(chartDiv.id, {{ autosize: true }});
                        }}, 40);
                    }}
                    return;
                }}

                // 2. Check entire tab fullscreen
                const fullTab = document.querySelector('.is-tab-fullscreen');
                if (fullTab) {{
                    toggleTabFullscreen(fullTab.id);
                }}
            }}
        }});

        // Initialize Tab 1 on Load for instant startup
        window.addEventListener('DOMContentLoaded', () => {{
            renderAxesTab();
            renderedTabs['tab-axes'] = true;
        }});
    </script>
</body>
</html>
"""

output_file = os.path.join(BASE_DIR, 'dashboard.html')
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"{output_file} generated successfully for {num_samples} samples!")
