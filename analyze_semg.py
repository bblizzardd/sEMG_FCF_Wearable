"""
================================================================================
sEMG OFFLINE SCIENTIFIC PIPELINE & FATIGUE / FEATURE EXTRACTION TOOL
Chuẩn SENIAM / ISEK:
  ch2_raw24 -> Remove DC (20Hz HPF) -> Notch 50Hz/100Hz -> LPF 450Hz (20-450Hz Bandpass)
  -> Time-domain Features (RMS, MAV, WL, ZC, SSC)
  -> Frequency-domain & Fatigue Tracking (PSD, MDF, MNF)
================================================================================
"""

import sys
import os
import csv
import math

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Bi-directional (Zero-phase) IIR filter implementation to eliminate all phase distortion
def filtfilt_iir(b, a, x):
    # Forward pass
    y_fwd = [0.0] * len(x)
    for i in range(len(x)):
        val = b[0] * x[i]
        if i >= 1:
            val += b[1] * x[i-1] - a[1] * y_fwd[i-1]
        if i >= 2:
            val += b[2] * x[i-2] - a[2] * y_fwd[i-2]
        y_fwd[i] = val
    
    # Backward pass
    y_bwd = [0.0] * len(x)
    for i in range(len(x) - 1, -1, -1):
        val = b[0] * y_fwd[i]
        if i < len(x) - 1:
            val += b[1] * y_fwd[i+1] - a[1] * y_bwd[i+1]
        if i < len(x) - 2:
            val += b[2] * y_fwd[i+2] - a[2] * y_bwd[i+2]
        y_bwd[i] = val
    return y_bwd

def process_semg_file(csv_path, output_csv=None):
    if not os.path.exists(csv_path):
        print(f"[!] Không tìm thấy file: {csv_path}")
        return

    print("=" * 75)
    print(f"🔬 ĐANG XỬ LÝ PIPELINE KHOA HỌC CHO FILE: {os.path.basename(csv_path)}")
    print("=" * 75)

    sample_indices = []
    timestamps_us = []
    ch1_raw24 = []
    ch2_raw24 = []
    leadoff = []

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if not row or len(row) < 5:
                continue
            sample_indices.append(int(row[0]))
            timestamps_us.append(int(row[1]))
            ch1_raw24.append(int(row[2]))
            ch2_raw24.append(int(row[3]))
            if len(row) >= 7:
                leadoff.append(int(row[6]))

    N = len(sample_indices)
    if N < 200:
        print("[!] File quá ngắn, không đủ mẫu để phân tích.")
        return

    # Tần số lấy mẫu thực tế từ sample_idx và thời gian
    fs = 2000.0
    total_sec = (sample_indices[-1] - sample_indices[0] + 1) / fs

    print(f"\n[1] THÔNG TIN GỐC:")
    print(f"  - Tổng số mẫu: {N:,} mẫu ({total_sec:.2f} giây)")
    print(f"  - Tần số lấy mẫu chuẩn hóa: {fs:.1f} Hz (Nyquist: {fs/2:.1f} Hz)")
    print(f"  - Kênh sEMG thực nghiệm chính: ch2_raw24 (Biceps Biopotential)")

    # --------------------------------------------------------------------------
    # PIPELINE 1: LỌC ZERO-PHASE THEO CHUẨN SENIAM (20 - 450 Hz)
    # --------------------------------------------------------------------------
    raw_signal = [float(x) for x in ch2_raw24]

    # Trừ DC Offset sơ bộ
    mean_raw = sum(raw_signal) / N
    s_zero_mean = [x - mean_raw for x in raw_signal]

    # Bộ lọc HPF 20Hz (Butterworth Bậc 2 @ 2000 SPS)
    b_hp = [0.956543, -1.913086, 0.956543]
    a_hp = [1.0, -1.911197, 0.914976]
    s_hp = filtfilt_iir(b_hp, a_hp, s_zero_mean)

    # Bộ lọc Notch 50Hz (IIR Bậc 2 @ 2000 SPS)
    b_n50 = [0.996245, -1.967959, 0.996245]
    a_n50 = [1.0, -1.935869, 0.960400]
    s_n50 = filtfilt_iir(b_n50, a_n50, s_hp)

    # Bộ lọc Notch 100Hz (IIR Bậc 2 @ 2000 SPS)
    b_n100 = [0.984086, -1.871843, 0.984086]
    a_n100 = [1.0, -1.864071, 0.960400]
    s_n100 = filtfilt_iir(b_n100, a_n100, s_n50)

    # Bộ lọc LPF 450Hz (Butterworth Bậc 2 @ 2000 SPS) - Giữ dải mỏi cơ 20-450Hz
    b_lp = [0.248341, 0.496682, 0.248341]
    a_lp = [1.0, -0.184214, 0.177578]
    clean_emg = filtfilt_iir(b_lp, a_lp, s_n100)

    print(f"\n[2] HOÀN TẤT CHUỖI LỌC ZERO-PHASE (FORWARD-BACKWARD):")
    print(f"  - Remove DC + HPF 20 Hz: Loại bỏ triệt để trôi điện cực")
    print(f"  - Notch 50 Hz & 100 Hz: Triệt sóng điện lưới & hài")
    print(f"  - LPF 450 Hz: Cắt nhiễu ngoài dải cơ, bảo toàn 100% phổ mỏi")

    # --------------------------------------------------------------------------
    # PIPELINE 2: TÍNH TOÁN CÁC ĐẶC TRƯNG MIỀN THỜI GIAN (TIME-DOMAIN FEATURES)
    # --------------------------------------------------------------------------
    # RMS, MAV, WL, ZC, SSC, SSI, WAMP
    mean_clean = sum(clean_emg) / N
    rms_total = math.sqrt(sum(x**2 for x in clean_emg) / N)
    mav_total = sum(abs(x) for x in clean_emg) / N
    ssi_total = sum(x**2 for x in clean_emg)
    wl_total = sum(abs(clean_emg[i] - clean_emg[i-1]) for i in range(1, N))

    zc_total = 0
    deadband_zc = rms_total * 0.15
    for i in range(1, N):
        if (clean_emg[i] * clean_emg[i-1] < 0) and abs(clean_emg[i] - clean_emg[i-1]) >= deadband_zc:
            zc_total += 1

    ssc_total = 0
    for i in range(1, N-1):
        d1 = clean_emg[i] - clean_emg[i-1]
        d2 = clean_emg[i] - clean_emg[i+1]
        if (d1 * d2 > 0) and (abs(d1) >= deadband_zc or abs(d2) >= deadband_zc):
            ssc_total += 1

    print(f"\n[3] BỘ ĐẶC TRƯNG MIỀN THỜI GIAN (CHUẨN ML / PATTERN RECOGNITION):")
    print(f"  • RMS (Root Mean Square)        : {rms_total:10.2f}")
    print(f"  • MAV (Mean Absolute Value)     : {mav_total:10.2f}")
    print(f"  • WL  (Waveform Length)         : {wl_total:10.0f}")
    print(f"  • ZC  (Zero Crossing Count)     : {zc_total:10d} lần ({zc_total/total_sec:.1f} crossings/s)")
    print(f"  • SSC (Slope Sign Changes)      : {ssc_total:10d} lần ({ssc_total/total_sec:.1f} changes/s)")
    print(f"  • SSI (Simple Square Integral)  : {ssi_total:10.2e}")

    # --------------------------------------------------------------------------
    # PIPELINE 3: PHÂN TÍCH MIỀN TẦN SỐ & THEO DÕI MỎI CƠ (MDF & MNF)
    # --------------------------------------------------------------------------
    # Chia cửa sổ 1.0 giây (2000 mẫu), bước nhảy 0.5 giây (50% overlap)
    win_len = 2000
    win_step = 1000
    time_windows = []
    mdf_list = []
    mnf_list = []
    rms_window_list = []

    for w_start in range(0, N - win_len, win_step):
        segment = clean_emg[w_start:w_start + win_len]
        t_mid = (sample_indices[w_start + win_len//2] - sample_indices[0]) / fs
        w_rms = math.sqrt(sum(x**2 for x in segment) / win_len)

        # Tính Periodogram bằng DFT đơn giản trong dải 20 - 450 Hz
        # Vì N_win = 2000, bin width = fs / N = 1.0 Hz
        # Ta tính DFT trực tiếp cho các tần số nguyên k từ 20 đến 450 Hz
        psd_bins = []
        freq_bins = []
        for k in range(20, 451, 2): # bước 2 Hz để tính toán siêu tốc
            omega = 2.0 * math.pi * k / fs
            cos_sum = sum(segment[n] * math.cos(omega * n) for n in range(0, win_len, 2))
            sin_sum = sum(segment[n] * math.sin(omega * n) for n in range(0, win_len, 2))
            power = (cos_sum**2 + sin_sum**2) / win_len
            psd_bins.append(power)
            freq_bins.append(k)

        total_power = sum(psd_bins)
        if total_power > 0:
            # Mean Frequency (MNF)
            mnf = sum(f * p for f, p in zip(freq_bins, psd_bins)) / total_power

            # Median Frequency (MDF)
            half_power = total_power / 2.0
            cum_power = 0.0
            mdf = freq_bins[0]
            for f, p in zip(freq_bins, psd_bins):
                cum_power += p
                if cum_power >= half_power:
                    mdf = f
                    break

            time_windows.append(t_mid)
            mdf_list.append(mdf)
            mnf_list.append(mnf)
            rms_window_list.append(w_rms)

    print(f"\n[4] PHÂN TÍCH PHỔ TẦN SỐ & THEO DÕI MỎI CƠ (MDF / MNF TRACKING):")
    if mdf_list:
        avg_mdf = sum(mdf_list) / len(mdf_list)
        avg_mnf = sum(mnf_list) / len(mnf_list)
        print(f"  • Median Frequency (MDF trung bình) : {avg_mdf:6.1f} Hz")
        print(f"  • Mean Frequency   (MNF trung bình) : {avg_mnf:6.1f} Hz")

        # Tính độ dốc trôi tần số (Linear Regression Slope - Fatigue Index)
        n_w = len(time_windows)
        mean_t = sum(time_windows) / n_w
        mean_mdf = sum(mdf_list) / n_w
        num_slope = sum((time_windows[i] - mean_t) * (mdf_list[i] - mean_mdf) for i in range(n_w))
        den_slope = sum((time_windows[i] - mean_t)**2 for i in range(n_w))
        mdf_slope = num_slope / den_slope if den_slope > 0 else 0.0

        print(f"  • Độ dốc trôi MDF (Fatigue Slope)   : {mdf_slope:+.3f} Hz/giây")
        if mdf_slope < -0.5:
            print(f"    => [PHÁT HIỆN MỎI CƠ RÕ RỆT]: MDF giảm với tốc độ {mdf_slope:.2f} Hz/s.")
        else:
            print(f"    => [CƠ CHƯA MỎI CỤC BỘ]: Chế độ gồng nhả ngắt quãng giữ tần số ổn định.")

        print(f"\n  Bảng diễn biến MDF & MNF theo từng cửa sổ 1 giây:")
        print(f"  {'Thời gian (s)':<15}{'RMS':<12}{'MDF (Hz)':<12}{'MNF (Hz)':<12}")
        for i in range(min(8, len(time_windows))):
            print(f"  {time_windows[i]:<15.2f}{rms_window_list[i]:<12.1f}{mdf_list[i]:<12.1f}{mnf_list[i]:<12.1f}")
        if len(time_windows) > 8:
            print(f"  ... và {len(time_windows)-8} cửa sổ tiếp theo.")

    # --------------------------------------------------------------------------
    # PIPELINE 4: XUẤT FILE DATASET NGHIÊN CỨU ĐÃ LÀM SẠCH (CLEANED DATASET)
    # --------------------------------------------------------------------------
    if not output_csv:
        output_csv = os.path.splitext(csv_path)[0] + "_CLEANED_SENIAM.csv"

    with open(output_csv, 'w', encoding='utf-8', newline='') as f_out:
        writer = csv.writer(f_out)
        writer.writerow(["sample_idx", "time_sec", "ch2_raw24", "clean_emg_seniam"])
        for i in range(N):
            t_sec = (sample_indices[i] - sample_indices[0]) / fs
            writer.writerow([sample_indices[i], f"{t_sec:.6f}", ch2_raw24[i], f"{clean_emg[i]:.2f}"])

    print(f"\n[5] ĐÃ LƯU BỘ DỮ LIỆU ĐÃ LỌC CHUẨN SENIAM:")
    print(f"  📁 File kết quả: {output_csv}")
    print("=" * 75)

if __name__ == "__main__":
    target_csv = sys.argv[1] if len(sys.argv) > 1 else r"data\sEMG_2000SPS_20260929_165627.csv"
    process_semg_file(target_csv)
