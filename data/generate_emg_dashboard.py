import os
import sys
import glob
import webbrowser
import numpy as np
import pandas as pd

def find_latest_recording(data_dir):
    pattern = os.path.join(data_dir, "recording_*.csv")
    files = glob.glob(pattern)
    if not files:
        # Fallback to any csv
        files = glob.glob(os.path.join(data_dir, "*.csv"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def analyze_emg_csv(csv_path):
    print(f"[*] Dang doc du lieu tu: {csv_path}")
    df = pd.read_csv(csv_path)

    # Clean headers
    df.columns = df.columns.str.strip()

    # Identify columns
    col_time = next((c for c in df.columns if 'time' in c.lower()), None)
    col_ch1 = next((c for c in df.columns if 'ch1' in c.lower() and 'mv' in c.lower()), None)
    col_ch2 = next((c for c in df.columns if 'ch2' in c.lower() and 'mv' in c.lower()), None)
    col_btn = next((c for c in df.columns if 'button' in c.lower() or 'btn' in c.lower()), None)

    if not col_ch1 and 'raw_ch1' in df.columns:
        # Convert raw to mV: Vref=2.42V, Gain=6
        df['emg_ch1_mv'] = (df['raw_ch1'] * 2420.0) / (8388607.0 * 6.0)
        col_ch1 = 'emg_ch1_mv'

    if not col_ch2 and 'raw_ch2' in df.columns:
        df['emg_ch2_mv'] = (df['raw_ch2'] * 2420.0) / (8388607.0 * 6.0)
        col_ch2 = 'emg_ch2_mv'

    num_samples = len(df)
    if num_samples == 0:
        print("[!] File CSV rong!")
        return

    # Compute sampling rate
    if col_time:
        dt_ms = df[col_time].diff().median()
        fs = 1000.0 / dt_ms if dt_ms > 0 else 500.0
        duration_s = (df[col_time].iloc[-1] - df[col_time].iloc[0]) / 1000.0
    else:
        fs = 500.0
        duration_s = num_samples / fs

    print("==================================================")
    print("      KET QUA PHAN TICH TIN HIEU sEMG 24-BIT      ")
    print("==================================================")
    print(f" [+] Tong so mau:          {num_samples:,} mau")
    print(f" [+] Thoi luong thu:       {duration_s:.2f} giay")
    print(f" [+] Tan so lay mau (Fs):  {fs:.1f} Hz (SPS)")

    if col_ch1:
        vpp1 = df[col_ch1].max() - df[col_ch1].min()
        rms1 = np.sqrt(np.mean(df[col_ch1]**2))
        print(f" [+] Kenh 1 Peak-to-Peak:  {vpp1:.3f} mV  |  RMS: {rms1:.3f} mV")

    if col_ch2:
        vpp2 = df[col_ch2].max() - df[col_ch2].min()
        rms2 = np.sqrt(np.mean(df[col_ch2]**2))
        print(f" [+] Kenh 2 Peak-to-Peak:  {vpp2:.3f} mV  |  RMS: {rms2:.3f} mV")

    if col_btn:
        btn_count = (df[col_btn] == 1).sum()
        btn_pct = (btn_count / num_samples) * 100.0
        print(f" [+] Su kien bam nut BOOT: {btn_count:,} mau ({btn_pct:.1f}%)")
    print("==================================================\n")

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dashboard_html = os.path.join(base_dir, "emg_dashboard.html")

    csv_file = sys.argv[1] if len(sys.argv) > 1 else find_latest_recording(base_dir)

    if csv_file and os.path.exists(csv_file):
        analyze_emg_csv(csv_file)
    else:
        print("[*] Chua tim thay file recording_*.csv nao trong thu muc data.")
        print("    (Mo Dashboard de su dung che do du lieu mo phong Synthetic Demo)")

    if os.path.exists(dashboard_html):
        print(f"[*] Dang mo Dashboard tren trinh duyet: {dashboard_html}")
        webbrowser.open(f"file://{os.path.abspath(dashboard_html)}")
    else:
        print(f"[!] Khong tim thay {dashboard_html}")

if __name__ == "__main__":
    main()
