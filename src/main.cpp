// Basic demo for accelerometer readings from Adafruit MPU6050

#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Arduino.h>
#include <Wire.h>

#define BUTTON_PIN 5
Adafruit_MPU6050 mpu;

// Cấu hình tần số lấy mẫu chính xác 100Hz (chu kỳ 10,000 us = 10ms)
const unsigned long SAMPLE_INTERVAL_US = 10000; 
unsigned long previousMicros = 0;

void setup(void) {
  Serial.begin(921600);
  delay(1000); // Cho Serial ổn định sau khi reset

  Serial.println("\n=================================");
  Serial.println("ESP32-S3 khoi dong thanh cong!");
  Serial.println("Adafruit MPU6050 100Hz Non-blocking Test");
  Serial.println("=================================");

  // Khoi tao I2C: SDA = GPIO 18, SCL = GPIO 17 và bật tốc độ 400kHz Fast Mode
  Wire.begin(18, 17);
  Wire.setClock(400000);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  delay(100);

  // Thu khoi tao voi dia chi mac dinh 0x68 hoac 0x69
  if (!mpu.begin(0x68, &Wire) && !mpu.begin(0x69, &Wire)) {
    Serial.println("[LOI] Khong the khoi dong MPU6050!");
    while (1) {
      delay(2000);
      if (mpu.begin(0x68, &Wire) || mpu.begin(0x69, &Wire)) {
        break;
      }
    }
  }
  Serial.println("[OK] Da tim thay va ket noi thanh cong voi MPU6050!");

  mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_44_HZ); // 44Hz phù hợp với tần số lấy mẫu 100Hz

  Serial.print("\n--- BAT DAU DU LIEU CSV ---\n");
  Serial.print("timestamp_ms,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,temp,button\n");
  delay(500);
  previousMicros = micros();
}

void loop() {
  unsigned long currentMicros = micros();

  // Non-blocking timer: đảm bảo chu kỳ đúng chuẩn 10.0 ms (100 Hz)
  if (currentMicros - previousMicros >= SAMPLE_INTERVAL_US) {
    previousMicros += SAMPLE_INTERVAL_US;

    sensors_event_t a, g, temp;
    mpu.getEvent(&a, &g, &temp);

    int buttonState = digitalRead(BUTTON_PIN);
    int isButtonPressed = (buttonState == LOW) ? 1 : 0;

    Serial.printf("%lu,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.2f,%d\n",
                  millis(),
                  a.acceleration.x, a.acceleration.y, a.acceleration.z,
                  g.gyro.x, g.gyro.y, g.gyro.z,
                  temp.temperature,
                  isButtonPressed);
  }
}