#!/usr/bin/env python3
"""
merge_session.py
Gộp file CSV sEMG (2000 SPS) và IMU (100 Hz) của một phiên thành data/Combined_<phiên>.csv
(sEMG + IMU + button_state), cùng định dạng recorder ghi trực tiếp – xem combined_csv.py.
Dùng cho các phiên ghi trước khi recorder có file gộp, hoặc để tạo lại file gộp.

Cách dùng:
    python merge_session.py                   # Phiên mới nhất trong data/
    python merge_session.py 20261016_164552   # Phiên cụ thể (hoặc tiền tố, vd 20261021 = cả ngày)
    python merge_session.py all               # Mọi phiên chưa có file gộp
"""

import csv
import glob
import os
import re
import sys

from combined_csv import IMU_LENGTHS, CombinedWriter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DATA_DIR = "data"
SEMG_REQUIRED = ("sample_idx", "timestamp_us", "ch2_raw24", "ch2_raw16", "ch2_filtered16", "lead_off")


def session_ids():
    ids = set()
    for path in glob.glob(os.path.join(DATA_DIR, "*.csv")):
        match = re.match(r"^(?:sEMG_2000SPS|IMU_100Hz)_(\d{8}_\d{6})\.csv$", os.path.basename(path))
        if match:
            ids.add(match.group(1))
    return sorted(ids)


def read_imu(path):
    """Các mẫu IMU (host_us, fields) theo thứ tự trong file."""
    samples = []
    if not os.path.exists(path):
        return samples
    with open(path, encoding="utf-8", newline="") as f:
        for fields in csv.reader(f):
            if len(fields) in IMU_LENGTHS and fields[0] != "session":
                try:
                    samples.append((int(fields[2]), fields))
                except ValueError:
                    pass
    return samples


def merge_session(session_id):
    semg_path = os.path.join(DATA_DIR, f"sEMG_2000SPS_{session_id}.csv")
    imu_path = os.path.join(DATA_DIR, f"IMU_100Hz_{session_id}.csv")
    out_path = os.path.join(DATA_DIR, f"Combined_{session_id}.csv")
    print(f"\n=======================================================")
    print(f"  GỘP DỮ LIỆU sEMG + IMU + NÚT · phiên {session_id}")
    print(f"  sEMG CSV: {semg_path if os.path.exists(semg_path) else '(không có)'}")
    print(f"  IMU CSV : {imu_path if os.path.exists(imu_path) else '(không có)'}")
    print(f"=======================================================")

    imu = read_imu(imu_path)
    semg_count = 0
    with open(out_path, "w", encoding="utf-8") as out:
        writer = CombinedWriter(out)
        k = 0
        if os.path.exists(semg_path):
            with open(semg_path, encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                col = {name: i for i, name in enumerate(next(reader, []))}
                missing = [name for name in SEMG_REQUIRED if name not in col]
                if missing:
                    print(f"[-] File sEMG thiếu cột {', '.join(missing)}: bỏ qua phần sEMG.")
                    reader = ()
                btn = col.get("button_state")
                for row in reader:
                    try:
                        ts = int(row[col["timestamp_us"]])
                        values = [row[col[name]] for name in SEMG_REQUIRED]
                    except (ValueError, IndexError):
                        continue
                    # Phát lại 2 luồng theo đúng thứ tự thời gian như khi recorder nhận trực tiếp
                    while k < len(imu) and imu[k][0] <= ts:
                        writer.add_imu(imu[k][1])
                        k += 1
                    button = row[btn] if btn is not None and btn < len(row) else ""
                    writer.add_semg(values[0], ts, *values[2:], button)
                    semg_count += 1
        for _, fields in imu[k:]:
            writer.add_imu(fields)
        writer.close()

    print(f"[+] {semg_count:,} mẫu sEMG + {len(imu):,} mẫu IMU -> {writer.rows:,} dòng")
    print(f"    File gộp: {out_path}")
    return out_path


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "latest"
    ids = session_ids()
    if arg == "all":
        targets = [sid for sid in ids if not os.path.exists(os.path.join(DATA_DIR, f"Combined_{sid}.csv"))]
        skipped = len(ids) - len(targets)
        if skipped:
            print(f"[*] Bỏ qua {skipped} phiên đã có file gộp (chạy với mã phiên để tạo lại).")
    elif arg == "latest":
        targets = ids[-1:]
    else:
        targets = [sid for sid in ids if sid.startswith(arg)]
    if not targets:
        print("[-] Không có phiên nào cần gộp trong thư mục data/" if arg == "all"
              else f"[-] Không tìm thấy file sEMG/IMU của phiên '{arg}' trong thư mục data/")
        sys.exit(0 if arg == "all" else 1)
    for sid in targets:
        merge_session(sid)
