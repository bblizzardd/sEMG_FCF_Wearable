# sEMG_FCF_Wearable

Dự án thu nhận, xử lý và phân tích tín hiệu điện cơ bề mặt (**sEMG - Surface Electromyography**) sử dụng vi điều khiển **ESP32-S3** kết hợp cùng module cảm biến sinh học **ProtoCentral ADS1292R**.

---

## 1. Sơ đồ kết nối phần cứng (ESP32-S3 & ADS1292R)

| Chân ADS1292R | Chân ESP32-S3 | Chức năng / Ghi chú |
| :--- | :--- | :--- |
| **CS (SS)** | GPIO 10 | Chip Select (SPI) |
| **SCK (CLK)** | GPIO 12 | SPI Clock (Chế độ `SPI_MODE1`, 1 MHz) |
| **MOSI (DIN)** | GPIO 11 | Master Out Slave In |
| **MISO (DOUT)**| GPIO 13 | Master In Slave Out |
| **PWDN / RESET**| GPIO 9 | Reset phần cứng (kéo xuống LOW để reset) |
| **START** | GPIO 8 | Kích hoạt chuyển đổi ADC |
| **DRDY** | GPIO 4 | Báo dữ liệu mới sẵn sàng (Active LOW) |
| **3.3V** | 3.3V | Nguồn nuôi 3.3V ổn định |
| **GND** | GND | Nối chung mass hệ thống |

---

## 2. Hướng dẫn kết nối cáp 3 dây đo sEMG (Chuẩn IEC)

Bộ dây đo 3 điện cực snap-lead của module ADS1292R tuân theo quy chuẩn mã màu quốc tế:

| Ký hiệu trên dây | Màu sắc | Tên cực (IEC) | Vai trò trong đo sEMG |
| :---: | :---: | :---: | :--- |
| **R** | Đỏ (Red) | Right Arm (RA) | **Điện cực đo vi sai 1 (IN-)** |
| **L** | Vàng (Yellow) | Left Arm (LA) | **Điện cực đo vi sai 2 (IN+)** |
| *(Không chữ)* | Xanh lá (Green) | Right Leg (RL / Ref) | **Điện cực tham chiếu / khử nhiễu (RLD / Ground)** |

---

## 3. Vị trí dán điện cực cơ bắp tay trước (Biceps Brachii - Chuẩn SENIAM)

Theo khuyến nghị quốc tế của tổ chức **SENIAM** (*Surface ElectroMyoGraphy for the Non-Invasive Assessment of Muscles*), vị trí đặt điện cực trên cơ nhị đầu cánh tay (Biceps Brachii) được xác định như sau:

```text
                  [ Vai ]
                     ●  <--- Chấm xanh trên: Mỏm cùng vai (Medial Acromion)
                     |        [ DÁN DÂY XANH LÁ (Tham chiếu / RLD) ]
                     |
                     |  (2/3 chiều dài)
                     |
                    [x] <--- Dấu X vàng: Vị trí đặt cặp điện cực đo (Bụng cơ)
                     |        [ DÁN DÂY ĐỎ (R) VÀ DÂY VÀNG (L) ]
                     |        (Cách nhau 1.5 - 2 cm dọc theo thớ cơ)
                     |  (1/3 chiều dài)
                     |
                     ●  <--- Chấm xanh dưới: Hõm nếp gấp khuỷu tay (Fossa cubit)
                 [ Cẳng tay ]
```

### Chi tiết cách dán:
1. **Dây Xanh lá cây (Tham chiếu / Ground - RLD):**
   * Dán vào **chấm xanh ở mỏm cùng vai (Acromion)** hoặc vùng xương trung tính (mỏm khuỷu tay / cùi chỏ, xương đòn).
   * **Mục đích:** Cân bằng điện thế cơ thể với mạch đo, kích hoạt mạch lọc bù nhiễu tần số 50Hz (Right Leg Drive).
2. **Dây Đỏ (R) & Dây Vàng (L) (Cặp cực đo vi sai):**
   * Đặt 2 miếng dán điện cực tại **bụng cơ (xung quanh vị trí dấu X màu vàng)**.
   * Dán **dọc theo hướng thớ cơ** (hướng từ trên vai xuống khuỷu tay).
   * Khoảng cách giữa 2 tâm điện cực (Inter-Electrode Distance - IED) từ **1.5 cm đến 2.0 cm**.
   * Cắm dây Đỏ vào miếng trên, dây Vàng vào miếng dưới (hoặc ngược lại, vì đo vi sai lấy chênh lệch điện áp và xử lý biên độ/RMS).

---

## 4. Lưu ý quan trọng để thu tín hiệu sEMG sạch

1. **Chuẩn bị bề mặt da:**
   * Dùng cồn y tế (70 độ) lau sạch mồ hôi, bụi bẩn và bã nhờn tại các vị trí dán. Chờ cồn khô hoàn toàn trước khi dán điện cực.
   * Nếu vùng da có nhiều lông, nên cạo bớt để gel dẫn điện tiếp xúc trực tiếp với da, giảm điện trở tiếp xúc (skin impedance).
2. **Cố định dây dẫn:**
   * Dùng băng dính y tế dán cố định phần dây dẫn sát với cánh tay để tránh nhiễu do rung lắc cáp khi cử động (Cable Motion Artifact).
3. **Kiểm tra tín hiệu:**
   * **Trạng thái nghỉ (Rest):** Tay thả lỏng hoàn toàn trên bàn/đùi -> Tín hiệu sEMG là đường dao động biên độ nhỏ sát 0.
   * **Trạng thái co cơ (Contraction):** Gập khuỷu tay và gồng bắp tay -> Biên độ tín hiệu dao động tăng vọt rõ rệt.

---

## 5. Thu thập dữ liệu tốc độ cao (2000 SPS) ra file CSV

ADC được cấu hình **2000 SPS (2000 mẫu/giây)**. Firmware đọc ADC bằng tác vụ riêng trên core 0, được đánh thức bởi ngắt DRDY, rồi chuyển mẫu qua hàng đợi 512 mẫu cho vòng xử lý DSP và gửi Serial. Tốc độ UART, Serial Monitor và hai chương trình Python đều dùng **2.000.000 baud**. Cần nạp lại firmware và khởi động lại chương trình Python sau khi cập nhật; adapter USB-UART phải hỗ trợ tốc độ này.

Ở 115200 baud, UART 8N1 chỉ truyền khoảng 11.520 byte/giây, không đủ cho 2000 dòng `$D` mỗi giây. Với định dạng hiện tại, ngay cả dòng dài 74 byte ở 2000 SPS cộng telemetry vẫn nằm dưới mức 200.000 byte/giây của UART 2 Mbaud. Bộ đệm giúp hấp thụ các lần chậm ngắn; khi đầy, firmware đếm mẫu bị bỏ thay vì chặn tác vụ đọc ADC.

Dùng script Python để ghi và kiểm tra tốc độ thực tế:

```bash
# Cài đặt thư viện pyserial (nếu chưa có)
pip install pyserial

# Chạy ghi dữ liệu (tự động nhận diện cổng COM của ESP32):
python record_emg_csv.py

# Hoặc chỉ định cổng COM cụ thể:
python record_emg_csv.py COM3 2000000
```

* **Dữ liệu lưu tại:** `data/sEMG_recording_YYYYMMDD_HHMMSS.csv`
* **Cấu trúc cột:** `sample_idx,timestamp_us,ch1_raw24,ch2_raw24,ch2_raw16,filtered16,lead_off,time_s`
* **Thời gian:** `timestamp_us` được chụp trong ngắt cạnh xuống DRDY, trước khi đọc SPI/xử lý DSP/gửi UART (vẫn chịu độ trễ ngắt); `time_s` là số giây từ mẫu đầu phiên ghi, có xử lý bộ đếm 32-bit quay vòng. Khi ESP32 khởi động lại, chương trình đóng phiên CSV để tránh trộn hai trục thời gian.
* **Số thứ tự:** `sample_idx` tăng theo ngắt DRDY, kể cả khi mẫu bị bỏ trước khi truyền. Khoảng trống số thứ tự giúp phát hiện mất mẫu ở bước đọc ADC, hàng đợi hoặc đường truyền.
* **Hiển thị trực tiếp:** SPS tính từ số mẫu nhận được và timestamp ESP32 trong cửa sổ ít nhất một giây, không dựa trên tốc độ nhận từng đợt USB. Visualizer chỉ đánh dấu tốc độ đạt khi nằm trong khoảng 1960–2040 SPS (dung sai kiểm tra ±2%); chưa có số đo sẽ hiển thị 0.
* Nhấn `Ctrl + C` để dừng ghi và đóng file an toàn.

Sau khi nạp, ghi thử ít nhất 30–60 giây. Dòng chẩn đoán mỗi giây có dạng:

```text
[SPS] DRDY=2000.0 READ=2000.0 ADC_MISSED=0 QUEUE_DROP=0
```

Đây là ví dụ giá trị mong đợi, không phải kết quả đo trên phần cứng. `DRDY` là tốc độ ngắt quan sát được; `READ` là tốc độ đọc thành công; `ADC_MISSED` là số mẫu đã biết bị bỏ/không hợp lệ khi đọc; `QUEUE_DROP` là số mẫu mất vì đầy hàng đợi. Kiểm tra đồng thời SPS trong CSV gần 2000, số mẫu mất bằng 0 và khoảng cách timestamp gần 500 µs. Lệnh `r` (khởi tạo lại ADC) và `d` (đọc thanh ghi) làm gián đoạn thu mẫu; tránh dùng trong một phiên ghi cần liên tục. SPI được khóa khi thực hiện các lệnh này để tránh xung đột với tác vụ đọc.

Kiểm tra phần mềm:

```bash
pio run
python -m unittest discover -s test -p "test_*.py" -v
```
