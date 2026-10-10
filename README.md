# GY-BMI160 — ESP32-S3 SPI

Branch `dev-bmi` chứa firmware độc lập cho **GY-BMI160**, đọc gia tốc 3 trục, tốc độ góc 3 trục và nhiệt độ chip qua **SPI 4 dây**. Dự án dùng PlatformIO và Arduino ESP32; board `4d_systems_esp32s3_gen4_r8n16`.

## Đấu dây

| GY-BMI160 | ESP32-S3 |
| --- | --- |
| VIN | Để trống |
| 3V3 | 3.3V |
| GND | GND |
| SCL/SCK | GPIO 6 |
| SDA/SDI/MOSI | GPIO 5 |
| SA0 / SDO / MISO | GPIO 7 |
| CS/CSB | GPIO 15 |
| INT1/INT2 | Không nối |
| Nút nhấn ngoài | GPIO 3 ↔ GND (INPUT_PULLUP) |

Bus **HSPI**, mode 0, MSB first, 1 MHz. CS do firmware điều khiển; không nối CS cố định lên nguồn hoặc SDO xuống GND. Các chân 5/6/7/15 được chọn để tránh các chân 4/8/9/10/11/12/13 đã dành cho phần cứng khác.

## Build và nạp

```powershell
pio run
pio run -t upload
pio device monitor
```

Environment duy nhất: `bmi160`. Serial **460800 baud**, dùng cổng USB-UART của board. Đổi chân SPI trong `platformio.ini` nếu cần.

## Web theo dõi trực tiếp

Đóng Serial Monitor, nạp firmware mới rồi chạy:

```powershell
python -m pip install -r requirements-visualizer.txt
python live_bmi_visualizer.py
```

Mở **http://localhost:8765** trong Chrome, Edge hoặc trình duyệt tích hợp VS Code. Python đọc USB-UART bằng pyserial ở 460800 baud và chuyển dữ liệu qua HTTP/SSE: **không cần hộp cấp quyền Serial của trình duyệt**. Nếu chỉ có một USB-UART phù hợp, server tự kết nối; khi có nhiều cổng, chọn COM trong dashboard rồi bấm **Kết nối cảm biến**. Có thể chỉ định `python live_bmi_visualizer.py --serial-port COM10`. Web hiển thị:

- Đồ thị accel/gyro XYZ: gốc + Kalman, chọn cửa sổ 6/12/20 giây.
- Góc roll/pitch Kalman, mô hình góc nghiêng, SPS và trạng thái nhận mẫu.
- Ghi CSV mọi frame nhận được; dừng/tải file, tự tách phiên khi cảm biến reset.
- Mốc cắt rep: button_state ở cuối CSV (1 = nhấn, 0 = thả), đồ thị nút và vạch đỏ tại cạnh nhấn; chống dội 30 ms. Nhấn nút không reset cảm biến.
- Demo có nhãn riêng để xem giao diện khi chưa có phần cứng.

Xem hướng dẫn tại **web/guide.html**. Với module có chân VIN/3V3: nối **3V3 → 3.3V**, để VIN trống; **SA0 → GPIO 7 (MISO)**. Hàng lỗ OCS/INT2/INT1/SCX/SDX để trống.

## Chức năng

- Cấu hình accel/gyro 100 Hz, ±4 g / ±500 °/s.
- Xuất CSV gồm số thứ tự, timestamp, dữ liệu thô, gia tốc (g), tốc độ góc (°/s), nhiệt độ (°C).
- Kiểm tra CHIP_ID, cấu hình và trạng thái nguồn; tự thử kết nối lại khi cảm biến lỗi hoặc không có mẫu mới.
- Kalman làm mượt sáu trục và kết hợp accel/gyro để ước lượng roll/pitch.
- Lệnh Serial: `s` hoặc `?` xem trạng thái, `r` khởi tạo lại cảm biến, `k` reset Kalman.

## Cấu trúc

```text
include/BMI160.h             Giao diện driver
src/BMI160.cpp               Driver SPI và chuyển đổi đơn vị
src/main.cpp                Khởi tạo, thu mẫu, xuất CSV và phục hồi lỗi
include/ImuKalman.h         Kalman sáu trục và roll/pitch
include/DebouncedButton.h   Chống dội nút đánh dấu rep
web/                        Dashboard HTTP/SSE, dự phòng Web Serial
live_bmi_visualizer.py       Tự dò COM, đọc Serial và phục vụ web cục bộ
requirements-visualizer.txt  Phụ thuộc pyserial cho visualizer
test/bmi160/                Test driver bằng SPI mô phỏng trên máy tính
docs/BMI160.md              Hướng dẫn chi tiết và lệnh chạy test
platformio.ini              Cấu hình build và chân SPI
```

Xem [hướng dẫn BMI160](docs/BMI160.md) để biết định dạng CSV, cách kiểm tra cảm biến và giới hạn của polling/SPI. Build firmware và các test mô phỏng đã đạt. Máy chủ đã tự kết nối COM10 và nhận frame thật 28 cột, gồm Kalman và roll/pitch; chưa đánh giá độ chính xác cảm biến/góc trên phần cứng.
