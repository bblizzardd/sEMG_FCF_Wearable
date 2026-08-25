import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

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

def load_data(filepath='data.csv'):
    df = pd.read_csv(filepath)
    # Quy doi timestamp_ms sang thoi gian tuong doi tinh bang giay
    df['time_s'] = (df['timestamp_ms'] - df['timestamp_ms'].iloc[0]) / 1000.0
    # Tinh do lon vector tong hop (Magnitude)
    df['acc_mag'] = np.sqrt(df['acc_x']**2 + df['acc_y']**2 + df['acc_z']**2)
    df['gyro_mag'] = np.sqrt(df['gyro_x']**2 + df['gyro_y']**2 + df['gyro_z']**2)
    return df

def plot_overview(df, output_path='plot_sensor_overview.png'):
    fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=True, 
                             gridspec_kw={'height_ratios': [2.5, 2.5, 1.2, 1.0]})
    
    # Bang mau hien dai
    c_x, c_y, c_z, c_mag = '#2563EB', '#10B981', '#F59E0B', '#EF4444'
    c_temp, c_btn = '#8B5CF6', '#EC4899'
    
    # Tim cac khoang thoi gian nut dang nhan (button == 1)
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
    ax1.set_ylabel('Gia tốc (m/s²)', fontsize=11, fontweight='bold')
    ax1.set_title('ĐỒ THỊ TỔNG QUAN TÍN HIỆU CẢM BIẾN (IMU / EDGE AI)', fontsize=15, fontweight='bold', pad=12, color='#1E293B')
    ax1.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.9, ncol=4)
    ax1.grid(True, linestyle=':', alpha=0.6)

    # 2. Van toc goc (Gyroscope)
    ax2 = axes[1]
    ax2.plot(df['time_s'], df['gyro_x'], label='Gyro X', color=c_x, linewidth=1.4, alpha=0.85)
    ax2.plot(df['time_s'], df['gyro_y'], label='Gyro Y', color=c_y, linewidth=1.4, alpha=0.85)
    ax2.plot(df['time_s'], df['gyro_z'], label='Gyro Z', color=c_z, linewidth=1.4, alpha=0.85)
    ax2.plot(df['time_s'], df['gyro_mag'], label='Magnitude |Gyro|', color=c_mag, linewidth=1.6, linestyle='--', alpha=0.9)
    ax2.set_ylabel('Vận tốc góc (rad/s)', fontsize=11, fontweight='bold')
    ax2.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.9, ncol=4)
    ax2.grid(True, linestyle=':', alpha=0.6)

    # 3. Nhiet do (Temperature)
    ax3 = axes[2]
    ax3.plot(df['time_s'], df['temp'], label='Nhiệt độ (°C)', color=c_temp, linewidth=1.8)
    ax3.set_ylabel('Nhiệt độ (°C)', fontsize=11, fontweight='bold')
    ax3.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.9)
    ax3.grid(True, linestyle=':', alpha=0.6)

    # 4. Trang thai Nut bam (Button)
    ax4 = axes[3]
    ax4.step(df['time_s'], df['button'], label='Nút bấm (Button)', color=c_btn, linewidth=2, where='mid')
    ax4.fill_between(df['time_s'], df['button'], step='mid', color=c_btn, alpha=0.25)
    ax4.set_yticks([0, 1])
    ax4.set_yticklabels(['Nhả (0)', 'Nhấn (1)'])
    ax4.set_ylabel('Trạng thái nút', fontsize=11, fontweight='bold')
    ax4.set_xlabel('Thời gian (giây)', fontsize=12, fontweight='bold')
    ax4.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.9)
    ax4.grid(True, linestyle=':', alpha=0.6)

    # Danh dau vung nut nhan xuyen suot cac do thi
    for ax in axes:
        for (ts, te) in btn_spans:
            ax.axvspan(ts, te, color=c_btn, alpha=0.12)

    plt.tight_layout()
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
    ax1.set_title('Phân bố Gia tốc theo từng trục & Độ lớn tổng', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Giá trị (m/s²)', fontsize=11)
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
    ax2.set_title('Phân bố Vận tốc góc theo từng trục & Độ lớn tổng', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Giá trị (rad/s)', fontsize=11)
    ax2.grid(True, linestyle=':', alpha=0.6)

    # 3. Heatmap tuong quan Pearson
    ax3 = fig.add_subplot(gs[1, 0])
    cols_corr = ['acc_x', 'acc_y', 'acc_z', 'gyro_x', 'gyro_y', 'gyro_z', 'temp', 'button']
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
    ax3.set_title('Ma trận tương quan giữa các cảm biến', fontsize=12, fontweight='bold')

    # 4. So sanh gia tri trung binh theo trang thai Nut nhan (0 vs 1)
    ax4 = fig.add_subplot(gs[1, 1])
    features = ['acc_mag', 'gyro_mag', 'temp']
    feat_names = ['|Acc| Total', '|Gyro| Total', 'Nhiệt độ (°C)']
    
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

    plt.suptitle('PHÂN TÍCH PHÂN BỐ VÀ TƯƠNG QUAN DỮ LIỆU CẢM BIẾN', fontsize=15, fontweight='bold', y=0.98, color='#1E293B')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Da luu: {output_path}")

def plot_3d_and_fft(df, output_path='plot_3d_trajectory_fft.png'):
    fig = plt.figure(figsize=(15, 6))

    # 1. Quy dao khong gian 3D cua Gia toc (Acc X, Y, Z)
    ax1 = fig.add_subplot(1, 2, 1, projection='3d')
    p = ax1.scatter(df['acc_x'], df['acc_y'], df['acc_z'], c=df['time_s'], cmap='plasma', s=10, alpha=0.75)
    ax1.plot(df['acc_x'], df['acc_y'], df['acc_z'], color='gray', alpha=0.25, linewidth=0.5)
    ax1.set_xlabel('Acc X (m/s²)', labelpad=8)
    ax1.set_ylabel('Acc Y (m/s²)', labelpad=8)
    ax1.set_zlabel('Acc Z (m/s²)', labelpad=8)
    ax1.set_title('Quỹ đạo Không gian Gia tốc 3D (Acc X-Y-Z)', fontsize=12, fontweight='bold')
    cbar = fig.colorbar(p, ax=ax1, pad=0.1, shrink=0.7)
    cbar.set_label('Thời gian (giây)')

    # 2. Pho tan so FFT (Fast Fourier Transform)
    ax2 = fig.add_subplot(1, 2, 2)
    dt = (df['timestamp_ms'].iloc[1] - df['timestamp_ms'].iloc[0]) / 1000.0
    fs = 1.0 / dt if dt > 0 else 43.48
    n = len(df)
    freqs = np.fft.rfftfreq(n, d=dt)

    fft_acc_mag = np.abs(np.fft.rfft(df['acc_mag'] - df['acc_mag'].mean())) / n
    fft_gyro_mag = np.abs(np.fft.rfft(df['gyro_mag'] - df['gyro_mag'].mean())) / n

    ax2.plot(freqs, fft_acc_mag, label='Phổ Gia tốc (|Acc| AC)', color='#2563EB', linewidth=1.5)
    ax2.plot(freqs, fft_gyro_mag, label='Phổ Vận tốc góc (|Gyro| AC)', color='#EF4444', linewidth=1.5)
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
    plot_overview(df, 'plot_sensor_overview.png')
    plot_distributions_and_correlation(df, 'plot_distributions_correlation.png')
    plot_3d_and_fft(df, 'plot_3d_trajectory_fft.png')
    print("Hoan tat tao tat ca do thi thanh cong!")
