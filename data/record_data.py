import sys
import time
import os
from datetime import datetime
import serial
import serial.tools.list_ports

def get_default_port():
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return None
    for p in ports:
        if "USB" in p.description or "UART" in p.description or "CP210" in p.description or "CH340" in p.description or "ESP32" in p.description:
            return p.device
    return ports[0].device

def main():
    # Cổng COM mặc định hoặc nhận từ tham số dòng lệnh
    port = sys.argv[1] if len(sys.argv) > 1 else get_default_port()
    baudrate = 921600

    if not port:
        print("[!] Khong tim thay cong COM nao. Vui long kiem tra lai ket noi cap USB.")
        return

    # Tao thu muc data neu chua co
    os.makedirs("data", exist_ok=True)
    
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join("data", f"recording_{timestamp_str}.csv")

    print(f"[*] Dang ket noi voi cong {port} (Baudrate: {baudrate})...")
    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(1) # Cho ESP32 on dinh
    except Exception as e:
        print(f"[!] Khong the mo cong {port}: {e}")
        print(" -> Hay chac chan rang ban da DONG Serial Monitor trong VS Code truoc khi chay script!")
        return

    print(f"[+] Da mo cong thanh cong!")
    print(f"[+] Du lieu se duoc luu vao file: {filename}")
    print("[*] Nhan Ctrl + C bat cu luc nao de dung ghi va luu file.\n")

    sample_count = 0
    header_written = False

    with open(filename, "w", encoding="utf-8") as f:
        try:
            while True:
                if ser.in_waiting > 0:
                    line = ser.readline().decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue

                    # Kiem tra xem co phai dong du lieu CSV hop le khong
                    if "timestamp_ms" in line:
                        f.write(line + "\n")
                        f.flush()
                        header_written = True
                        print(f"Header: {line}")
                    elif "," in line:
                        parts = line.split(",")
                        if len(parts) >= 8:
                            if not header_written:
                                if len(parts) >= 11:
                                    f.write("timestamp_ms,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,roll,pitch,temp,button\n")
                                else:
                                    f.write("timestamp_ms,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,temp,button\n")
                                header_written = True
                            f.write(line + "\n")
                            f.flush()
                            sample_count += 1
                            if sample_count % 50 == 0:
                                print(f"\r-> Da ghi {sample_count} mau du lieu...", end="", flush=True)
        except KeyboardInterrupt:
            print(f"\n\n[*] Da dung thu thap. Tong cong: {sample_count} mau da duoc luu vao {filename}")
        finally:
            ser.close()
            print("[+] Da dong cong Serial an toan.")

if __name__ == "__main__":
    main()
