// Basic demo for accelerometer readings from Adafruit MPU6050

// ESP32 Guide:
// https://RandomNerdTutorials.com/esp32-mpu-6050-accelerometer-gyroscope-arduino/
// ESP8266 Guide:
// https://RandomNerdTutorials.com/esp8266-nodemcu-mpu-6050-accelerometer-gyroscope-arduino/
// Arduino Guide:
// https://RandomNerdTutorials.com/arduino-mpu-6050-accelerometer-gyroscope/
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Arduino.h>
#include <Wire.h>

#define BUTTON_PIN 5
Adafruit_MPU6050 mpu;
int lastState = LOW;

void scanI2C() {
  Serial.println("--- Dang quet dia chi I2C tren chan (SDA=4, SCL=5)... ---");
  byte count = 0;
  for (byte address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    byte error = Wire.endTransmission();
    if (error == 0) {
      Serial.print("  [+] Tim thay thiet bi I2C tai dia chi: 0x");
      if (address < 16)
        Serial.print("0");
      Serial.print(address, HEX);
      if (address == 0x68 || address == 0x69) {
        Serial.print(" (Chinh la MPU6050)");
      }
      Serial.println();
      count++;
    }
  }
  if (count == 0) {
    Serial.println("  [-] Khong phat hien thiet bi I2C nao!");
  }
  Serial.println("--------------------------------------------------");
}

void setup(void) {
  Serial.begin(115200);
  delay(1000); // Cho Serial ổn định sau khi reset

  Serial.println("\n=================================");
  Serial.println("ESP32-S3 khoi dong thanh cong!");
  Serial.println("Adafruit MPU6050 Test...");
  Serial.println("=================================");

  // Khoi tao I2C: SDA = GPIO 18, SCL = GPIO 17
  Wire.begin(18, 17);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  delay(100);

  // Quet xem ESP32 co nhin thay MPU6050 tren bus I2C khong
  scanI2C();

  // Thu khoi tao voi dia chi mac dinh 0x68 hoac 0x69
  if (!mpu.begin(0x68, &Wire) && !mpu.begin(0x69, &Wire)) {
    Serial.println("[LOI] Khong the khoi dong MPU6050!");
    Serial.println(
        "-> Kiem tra lai: VCC (3.3V/5V), GND, SDA (GPIO 4), SCL (GPIO 5)");
    while (1) {
      delay(2000);
      scanI2C();
      if (mpu.begin(0x68, &Wire) || mpu.begin(0x69, &Wire)) {
        break;
      }
    }
  }
  Serial.println("[OK] Da tim thay va ket noi thanh cong voi MPU6050!");

  mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
  Serial.print("Accelerometer range set to: ");
  switch (mpu.getAccelerometerRange()) {
  case MPU6050_RANGE_2_G:
    Serial.println("+-2G");
    break;
  case MPU6050_RANGE_4_G:
    Serial.println("+-4G");
    break;
  case MPU6050_RANGE_8_G:
    Serial.println("+-8G");
    break;
  case MPU6050_RANGE_16_G:
    Serial.println("+-16G");
    break;
  }
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  Serial.print("Gyro range set to: ");
  switch (mpu.getGyroRange()) {
  case MPU6050_RANGE_250_DEG:
    Serial.println("+- 250 deg/s");
    break;
  case MPU6050_RANGE_500_DEG:
    Serial.println("+- 500 deg/s");
    break;
  case MPU6050_RANGE_1000_DEG:
    Serial.println("+- 1000 deg/s");
    break;
  case MPU6050_RANGE_2000_DEG:
    Serial.println("+- 2000 deg/s");
    break;
  }

  mpu.setFilterBandwidth(MPU6050_BAND_10_HZ);
  Serial.print("Filter bandwidth set to: ");
  switch (mpu.getFilterBandwidth()) {
  case MPU6050_BAND_260_HZ:
    Serial.println("260 Hz");
    break;
  case MPU6050_BAND_184_HZ:
    Serial.println("184 Hz");
    break;
  case MPU6050_BAND_94_HZ:
    Serial.println("94 Hz");
    break;
  case MPU6050_BAND_44_HZ:
    Serial.println("44 Hz");
    break;
  case MPU6050_BAND_21_HZ:
    Serial.println("21 Hz");
    break;
  case MPU6050_BAND_10_HZ:
    Serial.println("10 Hz");
    break;
  case MPU6050_BAND_5_HZ:
    Serial.println("5 Hz");
    break;
  }

  Serial.print("\n--- BAT DAU DU LIEU CSV ---\n");
  Serial.print("timestamp_ms,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,temp,button\n");
  delay(500);
}

void loop() {
  /* Get new sensor events with the readings */
  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);

  int buttonState = digitalRead(BUTTON_PIN);
  // Button dùng INPUT_PULLUP: LOW (0) khi nhấn, HIGH (1) khi nhả.
  // Gán 1 khi nhấn nút (dùng đánh dấu Rep / Sự kiện), 0 khi bình thường.
  int isButtonPressed = (buttonState == LOW) ? 1 : 0;

  /* In dữ liệu dạng CSV:
   * timestamp,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,temp,button
   * Sử dụng ký tự '\n' (thay vì println có cả '\r\n') để tránh bị nhân đôi dòng trống trong file log trên Windows
   */
  Serial.print(millis());
  Serial.print(",");
  Serial.print(a.acceleration.x, 4);
  Serial.print(",");
  Serial.print(a.acceleration.y, 4);
  Serial.print(",");
  Serial.print(a.acceleration.z, 4);
  Serial.print(",");
  Serial.print(g.gyro.x, 4);
  Serial.print(",");
  Serial.print(g.gyro.y, 4);
  Serial.print(",");
  Serial.print(g.gyro.z, 4);
  Serial.print(",");
  Serial.print(temp.temperature, 2);
  Serial.print(",");
  Serial.print(isButtonPressed);
  Serial.print("\n");

  delay(10); // Chu kỳ ~10ms (tần số lấy mẫu khoảng 100Hz)
}