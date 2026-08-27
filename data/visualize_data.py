import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Dam bao terminal Windows khong bi loi Unicode khi print
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Cau hinh tham my do thi bang Matplotlib thuan (khong phu thuoc seaborn)
plt.style.use('default')
plt.rcParams['font.sans-serif'] = ['Segoe UI', 'DejaVu Sans', 'Arial', 'sans-serif']
plt.rcParams['axes.edgecolor'] = '#CCCCCC'
plt.rcParams['axes.linewidth'] = 0.8
plt.rcParams['figure.facecolor'] = 'white'
plt.rcParams['axes.facecolor'] = '#FAFAFA'

def load_data(filepath=None):
    if filepath is None or filepath == 'data.csv':
        filepath = os.path.join(BASE_DIR, 'data.csv') if os.path.exists(os.path.join(BASE_DIR, 'data.csv')) else 'data.csv'
    df = pd.read_csv(filepath)
    # Quy doi timestamp_ms sang thoi gian tuong doi tinh bang giay
    df['time_s'] = (df['timestamp_ms'] - df['timestamp_ms'].iloc[0]) / 1000.0
    # Tinh do lon vector tong hop (Magnitude)
    df['acc_mag'] = np.sqrt(df['acc_x']**2 + df['acc_y']**2 + df['acc_z']**2)
    df['gyro_mag'] = np.sqrt(df['gyro_x']**2 + df['gyro_y']**2 + df['gyro_z']**2)
    return df

def plot_axes_xyz_breakdown(df, output_path='plot_axes_xyz_breakdown.png'):
    """
    Do thi tach biet 3 truc X, Y, Z de de dang so sanh giua Acc (g) va Gyro (deg/s) theo tung truc
    Kem theo khoang cach thoang dang de khong bi che khuat tin hieu.
    """
    fig, axes = plt.subplots(4, 1, figsize=(15, 14), sharex=True,
                             gridspec_kw={'height_ratios': [2.2, 2.2, 2.2, 1.2], 'hspace': 0.22})
    
    # Bang mau rieng cho tung truc
    c_acc_x, c_gyro_x = '#0284C7', '#EA580C'
    c_acc_y, c_gyro_y = '#059669', '#9333EA'
    c_acc_z, c_gyro_z = '#D97706', '#E11D48'
    c_btn = '#EC4899'

    # Tim cac khoang thoi gian nut dang nhan
    is_btn = df['button'].values
    diffs = np.diff(np.concatenate(([0], is_btn, [0])))
    starts = np.where(diffs == 1)[0]
    ends = np.where(diffs == -1)[0]
    btn_spans = []
    for s, e in zip(starts, ends):
        t_start = df['time_s'].iloc[s]
        t_end = df['time_s'].iloc[min(e-1, len(df)-1)]
        btn_spans.append((t_start, t_end))

    # --- 1. TRUC X: Acc X vs Gyro X ---
    ax1 = axes[0]
    ax1_twin = ax1.twinx()
    l1 = ax1.plot(df['time_s'], df['acc_x'], label='Acc X (g)', color=c_acc_x, linewidth=1.5, alpha=0.9)
    l2 = ax1_twin.plot(df['time_s'], df['gyro_x'], label='Gyro X (°/s)', color=c_gyro_x, linewidth=1.4, linestyle='--', alpha=0.9)
    ax1.set_ylabel('Gia tốc Acc X (g)', color=c_acc_x, fontsize=11, fontweight='bold')
    ax1_twin.set_ylabel('Vận tốc góc Gyro X (°/s)', color=c_gyro_x, fontsize=11, fontweight='bold')
    ax1.set_title('SO SÁNH TÍN HIỆU THEO TỪNG TRỤC X - Y - Z (ĐƠN VỊ: g & °/s)', fontsize=15, fontweight='bold', pad=14, color='#1E293B')
    
    # Gộp legend 2 trục Y
    lines_x = l1 + l2
    labels_x = [l.get_label() for l in lines_x]
    ax1.legend(lines_x, labels_x, loc='upper right', frameon=True, facecolor='white', framealpha=0.9)
    ax1.grid(True, linestyle=':', alpha=0.6)

    # --- 2. TRUC Y: Acc Y vs Gyro Y ---
    ax2 = axes[1]
    ax2_twin = ax2.twinx()
    l3 = ax2.plot(df['time_s'], df['acc_y'], label='Acc Y (g)', color=c_acc_y, linewidth=1.5, alpha=0.9)
    l4 = ax2_twin.plot(df['time_s'], df['gyro_y'], label='Gyro Y (°/s)', color=c_gyro_y, linewidth=1.4, linestyle='--', alpha=0.9)
    ax2.set_ylabel('Gia tốc Acc Y (g)', color=c_acc_y, fontsize=11, fontweight='bold')
    ax2_twin.set_ylabel('Vận tốc góc Gyro Y (°/s)', color=c_gyro_y, fontsize=11, fontweight='bold')
    lines_y = l3 + l4
    labels_y = [l.get_label() for l in lines_y]
    ax2.legend(lines_y, labels_y, loc='upper right', frameon=True, facecolor='white', framealpha=0.9)
    ax2.grid(True, linestyle=':', alpha=0.6)

    # --- 3. TRUC Z: Acc Z vs Gyro Z ---
    ax3 = axes[2]
    ax3_twin = ax3.twinx()
    l5 = ax3.plot(df['time_s'], df['acc_z'], label='Acc Z (g)', color=c_acc_z, linewidth=1.5, alpha=0.9)
    l6 = ax3_twin.plot(df['time_s'], df['gyro_z'], label='Gyro Z (°/s)', color=c_gyro_z, linewidth=1.4, linestyle='--', alpha=0.9)
    ax3.set_ylabel('Gia tốc Acc Z (g)', color=c_acc_z, fontsize=11, fontweight='bold')
    ax3_twin.set_ylabel('Vận tốc góc Gyro Z (°/s)', color=c_gyro_z, fontsize=11, fontweight='bold')
    lines_z = l5 + l6
    labels_z = [l.get_label() for l in lines_z]
    ax3.legend(lines_z, labels_z, loc='upper right', frameon=True, facecolor='white', framealpha=0.9)
    ax3.grid(True, linestyle=':', alpha=0.6)

    # --- 4. TRANG THAI NUT BAM ---
    ax4 = axes[3]
    ax4.step(df['time_s'], df['button'], label='Nút bấm (Button)', color=c_btn, linewidth=2, where='mid')
    ax4.fill_between(df['time_s'], df['button'], step='mid', color=c_btn, alpha=0.25)
    ax4.set_yticks([0, 1])
    ax4.set_yticklabels(['Nhả (0)', 'Nhấn (1)'])
    ax4.set_ylabel('Nút bấm', fontsize=11, fontweight='bold')
    ax4.set_xlabel('Thời gian (giây)', fontsize=12, fontweight='bold')
    ax4.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.9)
    ax4.grid(True, linestyle=':', alpha=0.6)

    # Highlight vung nhan nut xuyen suot
    for ax in axes:
        for (ts, te) in btn_spans:
            ax.axvspan(ts, te, color=c_btn, alpha=0.10)

    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Da luu: {output_path}")

def plot_overview(df, output_path='plot_sensor_overview.png'):
    has_angles = 'roll' in df.columns and 'pitch' in df.columns
    num_plots = 5 if has_angles else 4
    height_ratios = [2.2, 2.2, 2.0, 1.2, 1.0] if has_angles else [2.5, 2.5, 1.2, 1.0]
    figsize = (15, 16) if has_angles else (15, 13)

    fig, axes = plt.subplots(num_plots, 1, figsize=figsize, sharex=True, 
                             gridspec_kw={'height_ratios': height_ratios, 'hspace': 0.20})
    
    # Bang mau hien dai
    c_x, c_y, c_z, c_mag = '#0284C7', '#059669', '#D97706', '#DC2626'
    c_roll, c_pitch = '#0284C7', '#E11D48'
    c_temp, c_btn = '#7C3AED', '#DB2777'
    
    # Tim cac khoang thoi gian nut dang nhan
    is_btn = df['button'].values
    diffs = np.diff(np.concatenate(([0], is_btn, [0])))
    starts = np.where(diffs == 1)[0]
    ends = np.where(diffs == -1)[0]
    btn_spans = []
    for s, e in zip(starts, ends):
        t_start = df['time_s'].iloc[s]
        t_end = df['time_s'].iloc[min(e-1, len(df)-1)]
        btn_spans.append((t_start, t_end))

    # 1. Gia toc (Accelerometer)
    ax1 = axes[0]
    ax1.plot(df['time_s'], df['acc_x'], label='Acc X', color=c_x, linewidth=1.4, alpha=0.85)
    ax1.plot(df['time_s'], df['acc_y'], label='Acc Y', color=c_y, linewidth=1.4, alpha=0.85)
    ax1.plot(df['time_s'], df['acc_z'], label='Acc Z', color=c_z, linewidth=1.4, alpha=0.85)
    ax1.plot(df['time_s'], df['acc_mag'], label='Magnitude |Acc|', color=c_mag, linewidth=1.6, linestyle='--', alpha=0.9)
    ax1.set_ylabel('Gia tốc (g)', fontsize=11, fontweight='bold')
    ax1.set_title('ĐỒ THỊ TỔNG QUAN TÍN HIỆU CẢM BIẾN (IMU / EDGE AI)', fontsize=15, fontweight='bold', pad=12, color='#1E293B')
    ax1.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.9, ncol=4)
    ax1.grid(True, linestyle=':', alpha=0.6)

    # 2. Van toc goc (Gyroscope)
    ax2 = axes[1]
    ax2.plot(df['time_s'], df['gyro_x'], label='Gyro X', color=c_x, linewidth=1.4, alpha=0.85)
    ax2.plot(df['time_s'], df['gyro_y'], label='Gyro Y', color=c_y, linewidth=1.4, alpha=0.85)
    ax2.plot(df['time_s'], df['gyro_z'], label='Gyro Z', color=c_z, linewidth=1.4, alpha=0.85)
    ax2.plot(df['time_s'], df['gyro_mag'], label='Magnitude |Gyro|', color=c_mag, linewidth=1.6, linestyle='--', alpha=0.9)
    ax2.set_ylabel('Vận tốc góc (°/s)', fontsize=11, fontweight='bold')
    ax2.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.9, ncol=4)
    ax2.grid(True, linestyle=':', alpha=0.6)

    ax_idx = 2

    # 3. Goc nghieng Kalman Filter (Roll / Pitch) neu co
    if has_angles:
        ax_ang = axes[ax_idx]
        ax_ang.plot(df['time_s'], df['roll'], label='Roll (°)', color=c_roll, linewidth=1.6, alpha=0.9)
        ax_ang.plot(df['time_s'], df['pitch'], label='Pitch (°)', color=c_pitch, linewidth=1.6, alpha=0.9)
        ax_ang.set_ylabel('Góc nghiêng (°)', fontsize=11, fontweight='bold')
        ax_ang.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.9, ncol=2)
        ax_ang.grid(True, linestyle=':', alpha=0.6)
        ax_idx += 1

    # 4. Nhiet do (Temperature)
    ax_temp = axes[ax_idx]
    ax_temp.plot(df['time_s'], df['temp'], label='Nhiệt độ (°C)', color=c_temp, linewidth=1.8)
    ax_temp.set_ylabel('Nhiệt độ (°C)', fontsize=11, fontweight='bold')
    ax_temp.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.9)
    ax_temp.grid(True, linestyle=':', alpha=0.6)
    ax_idx += 1

    # 5. Trang thai Nut bam (Button)
    ax_btn = axes[ax_idx]
    ax_btn.step(df['time_s'], df['button'], label='Nút bấm (Button)', color=c_btn, linewidth=2, where='mid')
    ax_btn.fill_between(df['time_s'], df['button'], step='mid', color=c_btn, alpha=0.25)
    ax_btn.set_yticks([0, 1])
    ax_btn.set_yticklabels(['Nhả (0)', 'Nhấn (1)'])
    ax_btn.set_ylabel('Trạng thái nút', fontsize=11, fontweight='bold')
    ax_btn.set_xlabel('Thời gian (giây)', fontsize=12, fontweight='bold')
    ax_btn.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.9)
    ax_btn.grid(True, linestyle=':', alpha=0.6)

    # Danh dau vung nut nhan xuyen suot cac do thi
    for ax in axes:
        for (ts, te) in btn_spans:
            ax.axvspan(ts, te, color=c_btn, alpha=0.10)

    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Da luu: {output_path}")

def plot_distributions_and_correlation(df, output_path='plot_distributions_correlation.png'):
    fig = plt.figure(figsize=(15, 10))
    gs = fig.add_gridspec(2, 2, hspace=0.32, wspace=0.25)

    # 1. Boxplot Gia toc (Acc)
    ax1 = fig.add_subplot(gs[0, 0])
    acc_cols = ['acc_x', 'acc_y', 'acc_z', 'acc_mag']
    acc_labels = ['Acc X', 'Acc Y', 'Acc Z', '|Acc|']
    acc_data = [df[col].dropna() for col in acc_cols]
    ax1.boxplot(acc_data, tick_labels=acc_labels, patch_artist=True,
                boxprops=dict(facecolor='#38BDF8', color='#0284C7', alpha=0.75),
                medianprops=dict(color='#0F172A', linewidth=1.5),
                whiskerprops=dict(color='#0284C7'),
                capprops=dict(color='#0284C7'),
                flierprops=dict(marker='o', markersize=4, alpha=0.4, markerfacecolor='#0284C7'))
    ax1.set_title('Phân bố Gia tốc (g) theo từng trục & Độ lớn tổng', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Giá trị (g)', fontsize=11)
    ax1.grid(True, linestyle=':', alpha=0.6)

    # 2. Boxplot Van toc goc (Gyro)
    ax2 = fig.add_subplot(gs[0, 1])
    gyro_cols = ['gyro_x', 'gyro_y', 'gyro_z', 'gyro_mag']
    gyro_labels = ['Gyro X', 'Gyro Y', 'Gyro Z', '|Gyro|']
    gyro_data = [df[col].dropna() for col in gyro_cols]
    ax2.boxplot(gyro_data, tick_labels=gyro_labels, patch_artist=True,
                boxprops=dict(facecolor='#34D399', color='#059669', alpha=0.75),
                medianprops=dict(color='#0F172A', linewidth=1.5),
                whiskerprops=dict(color='#059669'),
                capprops=dict(color='#059669'),
                flierprops=dict(marker='o', markersize=4, alpha=0.4, markerfacecolor='#059669'))
    ax2.set_title('Phân bố Vận tốc góc (°/s) theo từng trục & Độ lớn tổng', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Giá trị (°/s)', fontsize=11)
    ax2.grid(True, linestyle=':', alpha=0.6)

    # 3. Heatmap tuong quan Pearson
    ax3 = fig.add_subplot(gs[1, 0])
    cols_corr = ['acc_x', 'acc_y', 'acc_z', 'gyro_x', 'gyro_y', 'gyro_z']
    if 'roll' in df.columns and 'pitch' in df.columns:
        cols_corr += ['roll', 'pitch']
    cols_corr += ['temp', 'button']
    corr_matrix = df[cols_corr].corr().values
    
    im = ax3.imshow(corr_matrix, cmap='coolwarm', vmin=-1, vmax=1)
    cbar = fig.colorbar(im, ax=ax3, fraction=0.046, pad=0.04)
    cbar.set_label('Hệ số tương quan (Pearson)', fontsize=10)
    
    ax3.set_xticks(range(len(cols_corr)))
    ax3.set_yticks(range(len(cols_corr)))
    ax3.set_xticklabels(cols_corr, rotation=45, ha='right', fontsize=9)
    ax3.set_yticklabels(cols_corr, fontsize=9)
    
    # Hien thi so lieu trong tung o heatmap
    for i in range(len(cols_corr)):
        for j in range(len(cols_corr)):
            val = corr_matrix[i, j]
            text_color = "white" if abs(val) > 0.55 else "black"
            ax3.text(j, i, f"{val:.2f}", ha="center", va="center", color=text_color, fontsize=8, fontweight='bold')
    # 4. So sanh gia tri trung binh theo trang thai Nut nhan (0 vs 1)
    ax4 = fig.add_subplot(gs[1, 1])
    features = ['acc_mag', 'gyro_mag', 'temp']
    feat_names = ['|Acc| Total (g)', '|Gyro| Total (°/s)', 'Nhiệt độ (°C)']
    
    means_btn0 = []
    means_btn1 = []
    for feat in features:
        val_min = df[feat].min()
        val_max = df[feat].max()
        norm_series = (df[feat] - val_min) / (val_max - val_min if val_max > val_min else 1)
        means_btn0.append(norm_series[df['button'] == 0].mean())
        means_btn1.append(norm_series[df['button'] == 1].mean())
    
    x = np.arange(len(features))
    width = 0.35
    ax4.bar(x - width/2, means_btn0, width, label='Nhả nút (0)', color='#10B981', alpha=0.85)
    ax4.bar(x + width/2, means_btn1, width, label='Nhấn nút (1)', color='#F43F5E', alpha=0.85)
    ax4.set_xticks(x)
    ax4.set_xticklabels(feat_names, fontsize=10)
    ax4.set_ylabel('Giá trị trung bình chuẩn hóa (0 - 1)', fontsize=10)
    ax4.set_title('So sánh tín hiệu khi Nhả nút vs Nhấn nút', fontsize=12, fontweight='bold')
    ax4.legend(frameon=True)
    ax4.grid(True, linestyle=':', alpha=0.6)

    plt.suptitle('PHÂN TÍCH PHÂN BỐ VÀ TƯƠNG QUAN DỮ LIỆU CẢM BIẾN (ĐƠN VỊ g & °/s)', fontsize=15, fontweight='bold', y=0.98, color='#1E293B')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Da luu: {output_path}")

def plot_3d_and_fft(df, output_path='plot_3d_trajectory_fft.png'):
    fig = plt.figure(figsize=(15, 6))

    # 1. Quy dao khong gian 3D cua Gia toc (Acc X, Y, Z theo g)
    ax1 = fig.add_subplot(1, 2, 1, projection='3d')
    p = ax1.scatter(df['acc_x'], df['acc_y'], df['acc_z'], c=df['time_s'], cmap='plasma', s=10, alpha=0.75)
    ax1.plot(df['acc_x'], df['acc_y'], df['acc_z'], color='gray', alpha=0.25, linewidth=0.5)
    ax1.set_xlabel('Acc X (g)', labelpad=8)
    ax1.set_ylabel('Acc Y (g)', labelpad=8)
    ax1.set_zlabel('Acc Z (g)', labelpad=8)
    ax1.set_title('Quỹ đạo Không gian Gia tốc 3D (Acc X-Y-Z tính theo g)', fontsize=12, fontweight='bold')
    cbar = fig.colorbar(p, ax=ax1, pad=0.1, shrink=0.7)
    cbar.set_label('Thời gian (giây)')

    # 2. Pho tan so FFT (Fast Fourier Transform)
    ax2 = fig.add_subplot(1, 2, 2)
    dt = (df['timestamp_ms'].iloc[1] - df['timestamp_ms'].iloc[0]) / 1000.0
    fs = 1.0 / dt if dt > 0 else 100.0
    n = len(df)
    freqs = np.fft.rfftfreq(n, d=dt)

    fft_acc_mag = np.abs(np.fft.rfft(df['acc_mag'] - df['acc_mag'].mean())) / n
    fft_gyro_mag = np.abs(np.fft.rfft(df['gyro_mag'] - df['gyro_mag'].mean())) / n

    ax2.plot(freqs, fft_acc_mag, label='Phổ Gia tốc (|Acc| AC) (g)', color='#0284C7', linewidth=1.5)
    ax2.plot(freqs, fft_gyro_mag, label='Phổ Vận tốc góc (|Gyro| AC) (°/s)', color='#E11D48', linewidth=1.5)
    ax2.set_title(f'Phân tích Phổ tần số FFT (Tần số lấy mẫu Fs ≈ {fs:.1f} Hz)', fontsize=12, fontweight='bold')
    ax2.set_xlabel('Tần số (Hz)', fontsize=11, fontweight='bold')
    ax2.set_ylabel('Biên độ phổ', fontsize=11, fontweight='bold')
    ax2.set_xlim(0, fs / 2)
    ax2.legend(loc='upper right', frameon=True)
    ax2.grid(True, linestyle=':', alpha=0.6)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Da luu: {output_path}")

if __name__ == '__main__':
    print("Dang doc file data.csv...")
    df = load_data('data.csv')
    print(f"Da nap {len(df)} dong du lieu.")
    plot_axes_xyz_breakdown(df, os.path.join(BASE_DIR, 'plot_axes_xyz_breakdown.png'))
    plot_overview(df, os.path.join(BASE_DIR, 'plot_sensor_overview.png'))
    plot_distributions_and_correlation(df, os.path.join(BASE_DIR, 'plot_distributions_correlation.png'))
    plot_3d_and_fft(df, os.path.join(BASE_DIR, 'plot_3d_trajectory_fft.png'))
    print("Hoan tat tao tat ca do thi thanh cong!")
