/*
  IMU Capture & Stream with 100 Hz Sampling Rate (Arduino Nano 33 BLE)

  Thu thập dữ liệu từ cảm biến IMU LSM9DS1 (Gia tốc kế, Con quay hồi chuyển, Nhiệt độ)
  và trạng thái nút bấm với tốc độ chính xác 100 Hz (10 ms / mẫu).

  Định dạng dữ liệu xuất ra Serial (CSV):
  timestamp_ms,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,temp,button

  Sơ đồ đấu nối nút bấm:
  - Một chân nút bấm -> Chân D2 (Arduino Nano 33 BLE)
  - Chân còn lại      -> GND (sử dụng điện trở kéo lên nội INPUT_PULLUP)
*/

#include <Arduino.h>
#include <Arduino_LSM9DS1.h>
#include <Wire.h>

#ifdef ARDUINO_ARDUINO_NANO33BLE
#define IMU_WIRE Wire1
#else
#define IMU_WIRE Wire
#endif

// Cấu hình chân kết nối
const int BUTTON_PIN = 2;        // Chân kết nối nút bấm (nối D2 với GND)
const int LED_PIN = LED_BUILTIN; // Đèn LED tích hợp (sáng khi bấm nút)

// Cấu hình tần số lấy mẫu 100 Hz (chu kỳ 10,000 us = 10 ms)
const unsigned long SAMPLE_INTERVAL_US = 10000;
unsigned long previousMicros = 0;

// Hàm đọc nhiệt độ trực tiếp từ thanh ghi cảm biến LSM9DS1 qua I2C (0x6B)
float readTemperature() {
  float temp = 0.0f;
  IMU_WIRE.beginTransmission(0x6B);
  IMU_WIRE.write(0x80 | 0x15); // Auto-increment đọc từ thanh ghi OUT_TEMP_L (0x15)
  if (IMU_WIRE.endTransmission(false) == 0) {
    if (IMU_WIRE.requestFrom(0x6B, (size_t)2) == 2) {
      uint8_t temp_l = IMU_WIRE.read();
      uint8_t temp_h = IMU_WIRE.read();
      int16_t raw_temp = (int16_t)((temp_h << 8) | temp_l);
      // LSM9DS1: Độ nhạy 16 LSB/°C, điểm chuẩn 25°C
      temp = 25.0f + ((float)raw_temp / 16.0f);
    }
  }
  return temp;
}

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000) {
    // Chờ kết nối Serial trong tối đa 3 giây
  }

  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // Khởi tạo cảm biến IMU
  if (!IMU.begin()) {
    Serial.println(F("[ERROR] Khong the khoi dong LSM9DS1!"));
    while (1) {
      digitalWrite(LED_PIN, !digitalRead(LED_PIN));
      delay(200);
    }
  }

  // In tiêu đề dữ liệu CSV chuẩn
  Serial.println(F("timestamp_ms,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,temp,button"));

  previousMicros = micros();
}

void loop() {
  unsigned long currentMicros = micros();

  // Non-blocking timer: đảm bảo chu kỳ lấy mẫu chính xác 10.0 ms (100 Hz)
  if (currentMicros - previousMicros >= SAMPLE_INTERVAL_US) {
    previousMicros += SAMPLE_INTERVAL_US;

    float acc_x = 0.0f, acc_y = 0.0f, acc_z = 0.0f;
    float gyro_x = 0.0f, gyro_y = 0.0f, gyro_z = 0.0f;

    // Đọc Gia tốc kế
    if (IMU.accelerationAvailable()) {
      IMU.readAcceleration(acc_x, acc_y, acc_z);
    }

    // Đọc Con quay hồi chuyển
    if (IMU.gyroscopeAvailable()) {
      IMU.readGyroscope(gyro_x, gyro_y, gyro_z);
    }

    // Đọc Nhiệt độ cảm biến
    float temp = readTemperature();

    // Đọc trạng thái nút bấm (INPUT_PULLUP: LOW khi nhấn -> 1, HIGH khi nhả -> 0)
    int buttonState = digitalRead(BUTTON_PIN);
    int isButtonPressed = (buttonState == LOW) ? 1 : 0;
    digitalWrite(LED_PIN, isButtonPressed ? HIGH : LOW);

    // In dữ liệu CSV: timestamp_ms,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,temp,button
    Serial.print(millis());
    Serial.print(',');
    Serial.print(acc_x, 4);
    Serial.print(',');
    Serial.print(acc_y, 4);
    Serial.print(',');
    Serial.print(acc_z, 4);
    Serial.print(',');
    Serial.print(gyro_x, 4);
    Serial.print(',');
    Serial.print(gyro_y, 4);
    Serial.print(',');
    Serial.print(gyro_z, 4);
    Serial.print(',');
    Serial.print(temp, 2);
    Serial.print(',');
    Serial.println(isButtonPressed);
  }
}