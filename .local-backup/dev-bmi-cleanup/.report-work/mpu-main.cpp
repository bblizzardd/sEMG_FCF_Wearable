// ESP32-S3 MPU6050 Driver & Silent I2C Error Handling

#include <Arduino.h>
#include <Wire.h>

// --- CẤU HÌNH PHẦN CỨNG ---
// Bạn có thể chọn GPIO 16 hoặc GPIO 17 cho chân SDA
#define I2C_SDA_PIN 18
#define I2C_SCL_PIN 17
#define BUTTON_PIN 5
#define MPU_ADDR 0x68

// Thanh ghi MPU6050
#define MPU6050_SMPLRT_DIV 0x19
#define MPU6050_CONFIG 0x1A
#define MPU6050_GYRO_CONFIG 0x1B
#define MPU6050_ACCEL_CONFIG 0x1C
#define MPU6050_ACCEL_XOUT_H 0x3B
#define MPU6050_PWR_MGMT_1 0x6B
#define MPU6050_PWR_MGMT_2 0x6C
#define MPU6050_WHO_AM_I 0x75
#define MPU6050_SIG_RESET 0x68

const unsigned long SAMPLE_INTERVAL_US = 10000; // 100Hz (10ms)
unsigned long previousMicros = 0;

uint8_t readReg(uint8_t reg) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(true) != 0)
    return 0xFF;
  if (Wire.requestFrom((uint8_t)MPU_ADDR, (uint8_t)1, (uint8_t)true) != 1)
    return 0xFF;
  return Wire.read();
}

uint8_t writeReg(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission(true); // 0 = ACK thành công
}

// Khởi tạo và đánh thức MPU6050
bool initMPU6050() {
  // 1. Device Reset
  writeReg(MPU6050_PWR_MGMT_1, 0x80);
  delay(100);

  // 2. Reset Signal Path
  writeReg(MPU6050_SIG_RESET, 0x07);
  delay(50);

  // 3. Đánh thức bằng Internal 8MHz (0x00)
  writeReg(MPU6050_PWR_MGMT_1, 0x00);
  delay(50);

  uint8_t pwr1 = readReg(MPU6050_PWR_MGMT_1);
  if (pwr1 & 0x40) {
    // Thử chuyển sang PLL Gyro X
    writeReg(MPU6050_PWR_MGMT_1, 0x01);
    delay(50);
  }

  // 4. Bật tất cả các trục
  writeReg(MPU6050_PWR_MGMT_2, 0x00);
  delay(20);

  // 5. Cấu hình bộ lọc & dải đo
  writeReg(MPU6050_CONFIG, 0x03);       // DLPF 44Hz
  writeReg(MPU6050_GYRO_CONFIG, 0x08);  // Gyro +/- 500 dps (65.5 LSB/dps)
  writeReg(MPU6050_ACCEL_CONFIG, 0x08); // Accel +/- 4g (8192 LSB/g)
  writeReg(MPU6050_SMPLRT_DIV, 0x00);   // 1kHz
  delay(50);

  return ((readReg(MPU6050_PWR_MGMT_1) & 0x40) == 0);
}

// Đọc 14 byte dữ liệu - trả về false nếu mất kết nối I2C hoặc chip chưa sẵn
// sàng
bool readSensorData(float &acc_x, float &acc_y, float &acc_z, float &gyro_x,
                    float &gyro_y, float &gyro_z, float &temperature) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(MPU6050_ACCEL_XOUT_H);
  if (Wire.endTransmission(true) != 0) {
    return false; // Lỗi truyền I2C -> Dừng in
  }

  if (Wire.requestFrom((uint8_t)MPU_ADDR, (uint8_t)14, (uint8_t)true) != 14) {
    return false; // Không nhận đủ 14 byte -> Dừng in
  }

  int16_t raw_ax = (Wire.read() << 8) | Wire.read();
  int16_t raw_ay = (Wire.read() << 8) | Wire.read();
  int16_t raw_az = (Wire.read() << 8) | Wire.read();
  int16_t raw_temp = (Wire.read() << 8) | Wire.read();
  int16_t raw_gx = (Wire.read() << 8) | Wire.read();
  int16_t raw_gy = (Wire.read() << 8) | Wire.read();
  int16_t raw_gz = (Wire.read() << 8) | Wire.read();

  // Kiểm tra nếu chip đang bị Sleep (tất cả giá trị thô bằng 0) -> Dừng in
  if (raw_ax == 0 && raw_ay == 0 && raw_az == 0 && raw_gx == 0 && raw_gy == 0 &&
      raw_gz == 0) {
    return false;
  }

  // Quy đổi: Accel +/-4g (8192 LSB/g)
  acc_x = (float)raw_ax / 8192.0f;
  acc_y = (float)raw_ay / 8192.0f;
  acc_z = (float)raw_az / 8192.0f;

  // Gyro +/-500 dps (65.5 LSB/dps)
  gyro_x = (float)raw_gx / 65.5f;
  gyro_y = (float)raw_gy / 65.5f;
  gyro_z = (float)raw_gz / 65.5f;

  // Nhiệt độ °C
  temperature = ((float)raw_temp / 340.0f) + 36.53f;

  return true;
}

void setup() {
  Serial.begin(921600);

  unsigned long startWait = millis();
  while (!Serial && (millis() - startWait < 1500)) {
    delay(10);
  }
  delay(200);

  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN, 100000);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  delay(100);

  initMPU6050();

  Serial.print("timestamp_ms,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,temp,button\n");
  Serial.flush();

  previousMicros = micros();
}

void loop() {
  unsigned long currentMicros = micros();

  // Chu kỳ lấy mẫu cố định 10.0 ms (100 Hz)
  if (currentMicros - previousMicros >= SAMPLE_INTERVAL_US) {
    previousMicros += SAMPLE_INTERVAL_US;

    float acc_x = 0, acc_y = 0, acc_z = 0;
    float gyro_x = 0, gyro_y = 0, gyro_z = 0;
    float temp = 0;

    // CHỈ IN RA SERIAL KHI ĐỌC I2C THÀNH CÔNG (NẾU MẤT I2C HOẶC KHÔNG NHẬN SẼ
    // TỰ ĐỘNG DỪNG IN HOÀN TOÀN)
    if (readSensorData(acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z, temp)) {
      int buttonState = digitalRead(BUTTON_PIN);
      int isButtonPressed = (buttonState == LOW) ? 1 : 0;

      // Xuất dữ liệu CSV 9 cột qua Serial
      Serial.printf("%lu,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.2f,%d\n",
                    millis(), acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z,
                    temp, isButtonPressed);
    }
  }
}