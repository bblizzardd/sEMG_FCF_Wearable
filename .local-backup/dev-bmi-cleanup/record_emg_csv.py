#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
RECORD_EMG_CSV.PY - GHI DỮ LIỆU sEMG TỪ CỔNG COM RA FILE CSV TỐC ĐỘ CAO (2000 SPS)
================================================================================
Mục đích:
  - Đọc trực tiếp luồng dữ liệu từ ESP32-S3 + ADS1292R qua cổng Serial (2000000 baud).
  - Đọc theo khối và kiểm tra số thứ tự/timestamp để phát hiện mất mẫu.
  - Tự động bắt đúng luồng dữ liệu chuẩn:
      * Luồng Dataset gốc 2000 SPS: $D,seq,timestampUs,ch1_24,ch2_24,raw16,filt16,loff
  - Theo dõi tỷ lệ mất mẫu (Packet Drop Rate) và tốc độ lấy mẫu thực tế (SPS).
================================================================================
Cách dùng:
  python record_emg_csv.py              (Tự động dò cổng COM)
  python record_emg_csv.py COM3         (Chỉ định cổng COM cụ thể)
  python record_emg_csv.py COM3 2000000  (Chỉ định cổng và baudrate)
================================================================================
"""

import sys
import os
import time
import argparse
from datetime import datetime
from sample_timing import SampleClock

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("[!] LỖI: Chưa cài đặt thư viện 'pyserial'.")
    print("    Vui lòng chạy lệnh sau để cài đặt:")
    print("    pip install pyserial\n")
    sys.exit(1)

# Thiết lập encoding UTF-8 cho Windows Terminal
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


def auto_detect_com_port():
    """Tự động tìm cổng COM của ESP32 / USB Serial"""
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return None
    # Ưu tiên các cổng có định danh ESP32, CP210x, CH340, USB-to-UART
    for p in ports:
        desc = (p.description or "").upper()
        hwid = (p.hwid or "").upper()
        if any(keyword in desc or keyword in hwid for keyword in ["303A", "ESP32", "CH34", "CP210", "UART", "USB SERIAL"]):
            return p.device
    return ports[0].device


def list_available_ports():
    """In danh sách các cổng COM khả dụng"""
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("  (Không tìm thấy cổng COM nào)")
    else:
        for p in ports:
            print(f"  - {p.device}: {p.description}")


def main():
    parser = argparse.ArgumentParser(description="Script ghi dữ liệu sEMG từ ESP32-S3 ra file CSV")
    parser.add_argument("port", nargs="?", default=None, help="Tên cổng COM (ví dụ: COM3, COM4). Bỏ trống để tự động dò.")
    parser.add_argument("baud", nargs="?", type=int, default=2000000, help="Tốc độ Baudrate (mặc định: 2000000)")
    parser.add_argument("--output", "-o", default=None, help="Tên file CSV lưu dữ liệu (mặc định tự đặt theo thời gian)")
    parser.add_argument("--dir", "-d", default="data", help="Thư mục lưu file CSV (mặc định: data/)")
    args = parser.parse_args()

    port = args.port or auto_detect_com_port()
    baudrate = args.baud

    if not port:
        print("[!] Không tìm thấy cổng COM nào!")
        print("Danh sách thiết bị kết nối:")
        list_available_ports()
        print("\nVui lòng cắm cáp USB và thử lại, hoặc chỉ định cổng: python record_emg_csv.py COMx")
        sys.exit(1)

    # Tạo thư mục lưu dữ liệu
    save_dir = args.dir
    os.makedirs(save_dir, exist_ok=True)

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.output:
        csv_path = os.path.join(save_dir, args.output) if not os.path.isabs(args.output) else args.output
    else:
        csv_path = os.path.join(save_dir, f"sEMG_recording_{timestamp_str}.csv")

    print("\n" + "="*70)
    print("   THU THẬP DỮ LIỆU sEMG (ESP32-S3 + ADS1292R) -> CSV")
    print("="*70)
    print(f"[*] Cổng Serial : {port} | Baudrate: {baudrate}")
    print(f"[*] File lưu    : {csv_path}")
    print("[*] Đang mở kết nối Serial...")

    try:
        ser = serial.Serial(port, baudrate, timeout=0.1)
        ser.dtr = False
        ser.rts = False
        time.sleep(0.5)
        # Thử tăng bộ đệm driver Serial trên Windows lên 64KB nếu hỗ trợ
        try:
            ser.set_buffer_size(rx_size=65536)
        except Exception:
            pass
    except Exception as e:
        print(f"\n[!] LỖI KẾT NỐI: Không thể mở cổng {port}: {e}")
        print("💡 GỢI Ý:")
        print("   1. Hãy chắc chắn bạn đã ĐÓNG Serial Monitor trong VS Code / PlatformIO.")
        print("   2. Đảm bảo không có phần mềm nào khác đang chiếm cổng COM này.")
        print("   3. Các cổng COM đang có trên máy:")
        list_available_ports()
        sys.exit(1)

    print(f"[+] KẾT NỐI THÀNH CÔNG VỚI {port}!")
    print("[*] Bắt đầu nhận dữ liệu. Nhấn Ctrl + C để dừng và đóng file an toàn.\n")

    # Mở file CSV và bắt đầu ghi
    total_written = 0
    dropped_samples = 0
    sample_clock = SampleClock()
    data_mode = None  # 'D_FORMAT' (2000 SPS) hoặc 'TELEMETRY'
    
    # Biến tính SPS thực tế
    current_sps = 0.0
    recorded_average_sps = 0.0

    byte_buf = bytearray()

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        try:
            while True:
                # Đọc theo khối (chunked) để tối đa hóa hiệu năng I/O
                waiting = ser.in_waiting
                chunk = ser.read(max(waiting, 2048))
                if not chunk:
                    time.sleep(0.001)
                    continue

                byte_buf.extend(chunk)

                # Tách từng dòng trong bộ nhớ bytearray
                while True:
                    nl_pos = byte_buf.find(b"\n")
                    if nl_pos < 0:
                        break
                    raw_line = byte_buf[:nl_pos]
                    del byte_buf[:nl_pos + 1]

                    if not raw_line:
                        continue

                    line = raw_line.decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue

                    # ==========================================================
                    # LUỒNG 1: Dữ liệu mẫu Dataset chuẩn ($D,seq,us,ch1,ch2,raw16,filt16,loff)
                    # ==========================================================
                    if line.startswith("$D,"):
                        parts = line[3:].split(",")
                        if len(parts) >= 7:
                            try:
                                values = [int(value) for value in parts[:7]]
                                seq, hw_us = values[:2]
                                restarted = sample_clock.update(seq, hw_us)
                            except ValueError:
                                continue
                            if restarted:
                                raise RuntimeError("ESP32 đã khởi động lại. Dừng file này; chạy lại để ghi phiên mới.")
                            if data_mode is None:
                                data_mode = "D_FORMAT"
                                f.write("sample_idx,timestamp_us,ch1_raw24,ch2_raw24,ch2_raw16,filtered16,lead_off,time_s\n")
                                f.flush()
                                print("[+] Đã bắt được luồng dữ liệu Dataset 2000 SPS ($D)!")

                            dropped_samples = sample_clock.missing
                            current_sps = sample_clock.sps
                            f.write(",".join(parts[:7]) + f",{sample_clock.elapsed_us / 1_000_000:.6f}\n")
                            total_written += 1
                            recorded_average_sps = sample_clock.average_sps

                            # Cập nhật thông số SPS và flush định kỳ mỗi 500 mẫu (~0.25s)
                            if total_written % 500 == 0:
                                f.flush()
                                drop_rate = (dropped_samples / (total_written + dropped_samples) * 100) if (total_written + dropped_samples) > 0 else 0.0
                                print(f"\r[ĐANG GHI] {total_written:>7} mẫu | SPS: {current_sps:>6.1f} Hz | Rơi: {dropped_samples} ({drop_rate:.2f}%)   ", end="", flush=True)

                    # ==========================================================
                    # LUỒNG 3: Dòng thông báo khác (Log khởi động, Chờ DRDY, Cảnh báo...)
                    # ==========================================================
                    elif not line.startswith("Raw:"):
                        print(f"[ESP32] {line}")

        except KeyboardInterrupt:
            print("\n\n[*] Người dùng bấm Ctrl + C. Đang hoàn tất lưu trữ...")
        except (RuntimeError, serial.SerialException) as exc:
            print(f"\n[!] Dừng ghi: {exc}")
        finally:
            ser.close()
            print("\n" + "="*70)
            print(f"[+] ĐÃ HOÀN TẤT LƯU FILE!")
            print(f"    - Đường dẫn : {os.path.abspath(csv_path)}")
            print(f"    - Tổng mẫu  : {total_written} mẫu")
            if data_mode == "D_FORMAT":
                print(f"    - Số mẫu rơi: {dropped_samples}")
                # Use timestamps of the rows actually saved, including short captures.
                print(f"    - Tần số tb : {recorded_average_sps:.1f} SPS")
            print(f"    - Cổng Serial đã đóng an toàn.")
            print("="*70 + "\n")


if __name__ == "__main__":
    main()
