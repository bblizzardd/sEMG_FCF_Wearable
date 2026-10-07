#include "BMI160.h"

#include <Arduino.h>
#include <math.h>

namespace {
constexpr uint8_t CHIP_ID = 0x00;
constexpr uint8_t ERR_REG = 0x02;
constexpr uint8_t PMU_STATUS = 0x03;
constexpr uint8_t GYRO_DATA = 0x0C;
constexpr uint8_t REG_STATUS = 0x1B;
constexpr uint8_t TEMPERATURE = 0x20;
constexpr uint8_t ACC_CONF = 0x40;
constexpr uint8_t COMMAND = 0x7E;
constexpr uint8_t CONFIG[] = {0x28, 0x05, 0x28, 0x02};

int16_t signedLE(const uint8_t *bytes) {
  const uint16_t value = uint16_t(bytes[0]) | (uint16_t(bytes[1]) << 8);
  return static_cast<int16_t>(value < 0x8000 ? int32_t(value) : int32_t(value) - 65536);
}
} // namespace

void BMI160::readRegisters(uint8_t reg, uint8_t *data, size_t count) {
  spi_.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
  digitalWrite(csPin_, LOW);
  delayMicroseconds(1);
  spi_.transfer(reg | 0x80); // Bit 7 = read; first data byte follows immediately.
  for (size_t i = 0; i < count; ++i) data[i] = spi_.transfer(0x00);
  delayMicroseconds(1);
  digitalWrite(csPin_, HIGH);
  spi_.endTransaction();
  delayMicroseconds(1);
}

void BMI160::writeRegister(uint8_t reg, uint8_t value) {
  spi_.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
  digitalWrite(csPin_, LOW);
  delayMicroseconds(1);
  spi_.transfer(reg & 0x7F);
  spi_.transfer(value);
  delayMicroseconds(1);
  digitalWrite(csPin_, HIGH);
  spi_.endTransaction();
  delayMicroseconds(500); // Covers even suspend-mode post-write idle (450 us).
}

void BMI160::selectSpi() {
  uint8_t ignored;
  // The CS rising edge after this throwaway read selects SPI after power/reset.
  // This is a separate transaction, NOT a dummy byte in every register read.
  readRegisters(0x7F, &ignored, 1);
  delay(1);
}

bool BMI160::checkHealth() {
  uint8_t state[4]; // CHIP_ID, reserved, ERR_REG, PMU_STATUS.
  readRegisters(CHIP_ID, state, sizeof(state));
  if (state[0] != 0xD1) {
    error_ = "SPI CHIP_ID invalid (check wiring/power)";
    return false;
  }
  if (state[2] != 0 || (state[3] & 0x3C) != 0x14) {
    error_ = "sensor error or unexpected power mode";
    return false;
  }
  return true;
}

bool BMI160::fail(const char *message) {
  ready_ = false;
  error_ = message;
  return false;
}

bool BMI160::begin() {
  ready_ = false;
  uint8_t id = 0;
  digitalWrite(csPin_, HIGH);
  pinMode(csPin_, OUTPUT);
  delay(10); // Power-on/soft-reset settling margin.
  selectSpi();
  readRegisters(CHIP_ID, &id, 1);
  if (id != 0xD1) return fail("BMI160 CHIP_ID 0xD1 not found on SPI");
  writeRegister(COMMAND, 0xB6);
  delay(10);
  selectSpi();
  readRegisters(CHIP_ID, &id, 1);
  if (id != 0xD1) return fail("CHIP_ID invalid after reset");

  writeRegister(COMMAND, 0x11);
  delay(5); // Datasheet maximum: 3.8 ms.
  writeRegister(COMMAND, 0x15);
  delay(85); // Datasheet maximum: 80 ms from suspend.

  // ACC_CONF, ACC_RANGE, GYR_CONF, GYR_RANGE: normal bandwidth, 100 Hz.
  for (uint8_t i = 0; i < sizeof(CONFIG); ++i) {
    writeRegister(ACC_CONF + i, CONFIG[i]);
    delay(1);
  }
  uint8_t actual[4], pmu = 0, errors = 0;
  readRegisters(ACC_CONF, actual, sizeof(actual));
  readRegisters(PMU_STATUS, &pmu, 1);
  readRegisters(ERR_REG, &errors, 1);
  for (uint8_t i = 0; i < sizeof(CONFIG); ++i) {
    if (actual[i] != CONFIG[i]) return fail("config readback mismatch");
  }
  if ((pmu & 0x3C) != 0x14) return fail("accel/gyro not in normal mode");
  if (errors != 0) return fail("sensor ERR_REG is nonzero");
  delay(50); // Let filters settle, then discard data from configuration changes.
  uint8_t discard[12];
  readRegisters(GYRO_DATA, discard, sizeof(discard));
  if (!checkHealth()) return false;
  ready_ = true;
  error_ = "none";
  return true;
}

BMI160::Result BMI160::read(Sample &sample) {
  if (!ready_) return Result::IoError;
  if (!checkHealth()) return Result::IoError;
  uint8_t status = 0;
  readRegisters(REG_STATUS, &status, 1);
  if (status == 0xFF) {
    error_ = "invalid SPI status";
    return Result::IoError;
  }
  // Read only when BOTH sensors have fresh data. Reading the data clears DRDY.
  if ((status & 0xC0) != 0xC0) return Result::NotReady;
  uint8_t data[15], temperature[2];
  readRegisters(GYRO_DATA, data, sizeof(data));
  readRegisters(TEMPERATURE, temperature, sizeof(temperature));
  // Catch a persistent disconnect/reset during the burst before publishing it.
  // SPI has no CRC: transient data corruption cannot be detected reliably.
  if (!checkHealth()) return Result::IoError;
  Sample next{};
  for (uint8_t i = 0; i < 3; ++i) {
    next.gyro[i] = signedLE(data + 2 * i);
    next.accel[i] = signedLE(data + 6 + 2 * i);
  }
  next.sensorTime = uint32_t(data[12]) | (uint32_t(data[13]) << 8) |
                    (uint32_t(data[14]) << 16);
  next.temperature = signedLE(temperature);
  sample = next;
  error_ = "none";
  return Result::Ok;
}

float BMI160::temperatureC(int16_t raw) {
  return raw == INT16_MIN ? NAN : 23.0f + raw / 512.0f;
}
