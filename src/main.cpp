/*
  IMU Capture with Button Trigger & 100 Hz Sampling Rate

  Thu thập dữ liệu Gia tốc kế (Accelerometer) và Con quay hồi chuyển (Gyroscope)
  từ cảm biến IMU (LSM9DS1) trên board Arduino Nano 33 BLE với tốc độ 100 sample
  / 1s (100 Hz).

  - Đã loại bỏ ngưỡng kích hoạt tự động (threshold).
  - Sử dụng nút bấm (kết nối chân D2 với GND) để kích hoạt thu thập đúng 100
  sample (1 giây dữ liệu).
  - Tích hợp đèn LED báo hiệu khi đang thu thập.

  Sơ đồ đấu nối nút bấm:
  - Một chân nút bấm -> Chân D2 của Arduino Nano 33 BLE
  - Chân còn lại của nút bấm -> Chân GND (Sử dụng điện trở kéo lên nội
  INPUT_PULLUP)
*/
#include <Arduino.h>
#include <Arduino_LSM9DS1.h>

// Cấu hình chân kết nối
const int BUTTON_PIN = 2;        // Chân kết nối nút bấm (nối D2 với GND)
const int LED_PIN = LED_BUILTIN; // Đèn LED tích hợp trên bo mạch để báo hiệu

// Cấu hình tần số lấy mẫu (100 sample / 1s)
const int numSamples =
    100; // Số mẫu mỗi lần thu thập (100 sample = 1 giây ở 100 Hz)
const unsigned long SAMPLE_INTERVAL_US =
    10000; // Chu kỳ lấy mẫu: 10,000 us = 10 ms = 100 Hz

int samplesRead =
    numSamples; // Khởi tạo bằng numSamples để ở trạng thái chờ nhấn nút
unsigned long previousMicros = 0;

// Biến quản lý chống rung phím (Debounce)
int buttonState = HIGH;
int lastButtonState = HIGH;
unsigned long lastDebounceTime = 0;
const unsigned long debounceDelay = 50; // Thời gian chống rung (50ms)

void setup() {
  // Khởi tạo Serial ở tốc độ 115200 baud để đảm bảo truyền dữ liệu 100Hz không
  // bị nghẽn
  Serial.begin(115200);
  while (!Serial)
    ;

  // Cấu hình nút bấm với điện trở kéo lên nội (khi nhấn nút chân D2 sẽ về mức
  // LOW)
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW); // Tắt LED lúc khởi động

  // Khởi tạo cảm biến IMU
  if (!IMU.begin()) {
    Serial.println("Failed to initialize IMU!");
    while (1)
      ;
  }

  // In tiêu đề dữ liệu CSV
  Serial.println("aX,aY,aZ,gX,gY,gZ");
}

void loop() {
  // 1. Đọc và xử lý chống rung phím nút bấm
  int reading = digitalRead(BUTTON_PIN);

  if (reading != lastButtonState) {
    lastDebounceTime = millis();
  }

  if ((millis() - lastDebounceTime) > debounceDelay) {
    if (reading != buttonState) {
      buttonState = reading;

      // Khi nút được nhấn (chuyển sang LOW) và hiện tại không trong tiến trình
      // lấy mẫu
      if (buttonState == LOW && samplesRead >= numSamples) {
        samplesRead = 0;
        previousMicros = micros();
        digitalWrite(LED_PIN, HIGH); // Bật LED báo hiệu bắt đầu thu thập
      }
    }
  }

  lastButtonState = reading;

  // 2. Thu thập dữ liệu IMU với tốc độ chính xác 100 sample / 1s
  if (samplesRead < numSamples) {
    unsigned long currentMicros = micros();

    // Kiểm tra xem đã đến thời điểm lấy mẫu tiếp theo chưa (mỗi 10,000 us = 10
    // ms)
    if (currentMicros - previousMicros >= SAMPLE_INTERVAL_US) {
      previousMicros += SAMPLE_INTERVAL_US; // Giữ nhịp lấy mẫu chính xác không
                                            // bị trôi thời gian

      float aX = 0, aY = 0, aZ = 0;
      float gX = 0, gY = 0, gZ = 0;

      // Đọc dữ liệu Gia tốc kế
      if (IMU.accelerationAvailable()) {
        IMU.readAcceleration(aX, aY, aZ);
      }

      // Đọc dữ liệu Con quay hồi chuyển
      if (IMU.gyroscopeAvailable()) {
        IMU.readGyroscope(gX, gY, gZ);
      }

      samplesRead++;

      // In dữ liệu ra Serial dưới dạng CSV
      Serial.print(aX, 3);
      Serial.print(',');
      Serial.print(aY, 3);
      Serial.print(',');
      Serial.print(aZ, 3);
      Serial.print(',');
      Serial.print(gX, 3);
      Serial.print(',');
      Serial.print(gY, 3);
      Serial.print(',');
      Serial.print(gZ, 3);
      Serial.println();

      // Khi đã thu thập đủ 100 mẫu (1 giây)
      if (samplesRead == numSamples) {
        digitalWrite(LED_PIN, LOW); // Tắt LED báo hiệu kết thúc
        Serial.println(); // Thêm 1 dòng trống phân cách giữa các lần thu thập
      }
    }
  }
}