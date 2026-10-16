#!/usr/bin/env python3
"""
merge_session.py
Công cụ đồng bộ và gộp 2 file CSV của sEMG (2000 SPS) và IMU (100 Hz) thành một file CSV thống nhất.

Cách dùng:
    python merge_session.py              # Tự động gộp phiên mới nhất trong data/
    python merge_session.py 20261016_164500 # Gộp phiên cụ thể
"""

import sys
import os
import glob
import csv
import json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def find_session_files(session_id=None):
    os.makedirs("data", exist_ok=True)
    if session_id:
        semg_matches = glob.glob(f"data/sEMG_2000SPS_{session_id}*.csv")
        imu_matches = glob.glob(f"data/IMU_100Hz_{session_id}*.csv")
    else:
        semg_matches = sorted(glob.glob("data/sEMG_2000SPS_*.csv"))
        imu_matches = sorted(glob.glob("data/IMU_100Hz_*.csv"))
        if not semg_matches or not imu_matches:
            return None, None, None
        # Lấy file mới nhất
        semg_file = semg_matches[-1]
        sid = os.path.basename(semg_file).replace("sEMG_2000SPS_", "").replace(".csv", "")
        imu_file = os.path.join("data", f"IMU_100Hz_{sid}.csv")
        if not os.path.exists(imu_file):
            # Tìm file IMU gần nhất
            imu_file = imu_matches[-1]
        return sid, semg_file, imu_file

    if not semg_matches:
        print(f"[-] Không tìm thấy file sEMG cho phiên {session_id}")
        return None, None, None
    if not imu_matches:
        print(f"[-] Không tìm thấy file IMU cho phiên {session_id}")
        return None, None, None

    return session_id, semg_matches[0], imu_matches[0]


def merge_session(session_id, semg_path, imu_path):
    print(f"\n=======================================================")
    print(f"  ĐỒNG BỘ DỮ LIỆU ĐA CẢM BIẾN (sEMG + IMU)")
    print(f"  Phiên   : {session_id}")
    print(f"  sEMG CSV: {semg_path}")
    print(f"  IMU CSV : {imu_path}")
    print(f"=======================================================")

    print("[*] Đang đọc dữ liệu IMU 100 Hz…")
    imu_rows = []
    with open(imu_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                r["_host_us"] = int(r["host_us"])
                imu_rows.append(r)
            except Exception:
                pass

    if not imu_rows:
        print("[-] File IMU không có mẫu hợp lệ.")
        return

    print(f"    -> Đã đọc {len(imu_rows):,} mẫu IMU.")

    print("[*] Đang đọc và đồng bộ dữ liệu sEMG 2000 SPS…")
    out_path = os.path.join("data", f"Combined_{session_id}.csv")

    imu_cols = [
        "ax_g", "ay_g", "az_g", "gx_dps", "gy_dps", "gz_dps",
        "roll_acc_deg", "pitch_acc_deg", "roll_kal_deg", "pitch_kal_deg",
        "accel_trusted", "button_state"
    ]

    count = 0
    imu_idx = 0
    imu_len = len(imu_rows)

    with open(semg_path, "r", encoding="utf-8") as f_in, \
         open(out_path, "w", encoding="utf-8", newline="") as f_out:
        
        semg_reader = csv.DictReader(f_in)
        fieldnames = [
            "timestamp_us", "time_sec", "ch2_raw16", "ch2_filtered16",
            "roll_deg", "pitch_deg", "ax_g", "ay_g", "az_g",
            "gx_dps", "gy_dps", "gz_dps", "button_rep", "lead_off"
        ]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        t0_us = None

        for row in semg_reader:
            try:
                ts_us = int(row["timestamp_us"])
            except Exception:
                continue

            if t0_us is None:
                t0_us = ts_us

            # Tiến con trỏ IMU đến mẫu gần nhất với ts_us
            while imu_idx + 1 < imu_len and imu_rows[imu_idx + 1]["_host_us"] <= ts_us:
                imu_idx += 1

            cur_imu = imu_rows[imu_idx]

            out_row = {
                "timestamp_us": ts_us,
                "time_sec": round((ts_us - t0_us) / 1e6, 6),
                "ch2_raw16": row.get("ch2_raw16", "0"),
                "ch2_filtered16": row.get("ch2_filtered16", "0"),
                "roll_deg": cur_imu.get("roll_kal_deg", "0.0"),
                "pitch_deg": cur_imu.get("pitch_kal_deg", "0.0"),
                "ax_g": cur_imu.get("ax_g", "0.0"),
                "ay_g": cur_imu.get("ay_g", "0.0"),
                "az_g": cur_imu.get("az_g", "0.0"),
                "gx_dps": cur_imu.get("gx_dps", "0.0"),
                "gy_dps": cur_imu.get("gy_dps", "0.0"),
                "gz_dps": cur_imu.get("gz_dps", "0.0"),
                "button_rep": cur_imu.get("button_state", "0"),
                "lead_off": row.get("lead_off", "0"),
            }
            writer.writerow(out_row)
            count += 1

    print(f"[+] Đồng bộ hoàn tất!")
    print(f"    - File kết hợp: {out_path}")
    print(f"    - Tổng số hàng: {count:,} mẫu đồng bộ @ 2000 SPS")
    print(f"=======================================================\n")


if __name__ == "__main__":
    sid_arg = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "latest" else None
    sid, semg, imu = find_session_files(sid_arg)
    if not sid or not semg or not imu:
        print("[-] Không tìm thấy cặp file session trong thư mục data/")
        sys.exit(1)
    merge_session(sid, semg, imu)
