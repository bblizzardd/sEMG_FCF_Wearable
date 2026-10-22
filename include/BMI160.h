#pragma once

#include <SPI.h>

// Primary 4-wire SPI, mode 0, MSB first, 1 MHz. Bus must be started by caller.
// Fixed configuration: 100 Hz, +/-4 g, +/-500 dps.
// Bosch BST-BMI160-DS000-09, sections 2.11 and 3.2.1-3.2.4.
class BMI160 {
 public:
  struct Sample {
    int16_t accel[3];
    int16_t gyro[3];
    int16_t temperature;
    uint32_t sensorTime; // 24-bit readout-time counter, NOT a sample timestamp.
  };
  enum class Result { Ok, NotReady, IoError };

  BMI160(SPIClass &spi, uint8_t csPin) : spi_(spi), csPin_(csPin) {}
  bool begin(); // Select SPI before/after reset; require CHIP_ID = 0xD1.
  Result read(Sample &sample); // Leaves sample unchanged unless fully successful.
  const char *error() const { return error_; }
  static float accelG(int16_t raw) { return raw / 8192.0f; }
  static float gyroDps(int16_t raw) { return raw / 65.6f; }
  static float temperatureC(int16_t raw);

 private:
  void readRegisters(uint8_t reg, uint8_t *data, size_t count);
  void writeRegister(uint8_t reg, uint8_t value);
  void selectSpi();
  bool checkHealth(); // SPI has no ACK; validate identity, errors and power mode.
  bool fail(const char *message);
  SPIClass &spi_;
  const uint8_t csPin_;
  bool ready_ = false;
  const char *error_ = "not initialized";
  char errorBuf_[64] = {};
};
