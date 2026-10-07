#include "BMI160.h"
#include <cassert>
#include <cmath>
#include <iostream>

unsigned long fakeDelayMs = 0;
uint64_t fakeTimeUs = 0;
SPIClass *fakeBus = nullptr;
constexpr uint8_t CS_PIN = 15;

void digitalWrite(uint8_t pin, uint8_t value) {
  assert(pin == CS_PIN && fakeBus);
  fakeBus->setCs(value);
}
void pinMode(uint8_t pin, uint8_t mode) { assert(pin == CS_PIN && mode == OUTPUT); }

void putWord(SPIClass &bus, uint8_t reg, int16_t value) {
  const uint16_t word = static_cast<uint16_t>(value);
  bus.regs[reg] = word & 0xFF;
  bus.regs[reg + 1] = word >> 8;
}

int main() {
  // A different device on CS must never receive reset commands.
  {
    SPIClass bus;
    bus.regs[0] = 0x68;
    BMI160 sensor(bus, CS_PIN);
    assert(!sensor.begin());
    assert(bus.writes == 0 && bus.csHigh && !bus.active);
  }
  // SPI is explicitly selected before CHIP_ID and again after soft reset.
  {
    SPIClass bus;
    BMI160 sensor(bus, CS_PIN);
    fakeDelayMs = 0;
    assert(sensor.begin());
    assert(bus.selections == 2 && fakeDelayMs >= 100);
    assert(bus.frames[0] == std::vector<uint8_t>({0xFF, 0x00}));
    assert(bus.frames[1] == std::vector<uint8_t>({0x80, 0x00}));
    assert(bus.frames[2] == std::vector<uint8_t>({0x7E, 0xB6}));
    assert(bus.frames[3] == std::vector<uint8_t>({0xFF, 0x00}));
    assert(bus.regs[0x41] == 0x05 && bus.regs[0x43] == 0x02);
  }
  for (bool badPmu : {false, true}) {
    SPIClass bus;
    bus.badPmu = badPmu;
    if (!badPmu) bus.corruptRegister = 0x41;
    BMI160 sensor(bus, CS_PIN);
    assert(!sensor.begin()); // SPI transfers alone cannot prove configuration.
    assert(bus.csHigh && !bus.active);
  }

  SPIClass bus;
  BMI160 sensor(bus, CS_PIN);
  BMI160::Sample sample{};
  sample.accel[0] = 1234;
  assert(sensor.read(sample) == BMI160::Result::IoError);
  assert(sensor.begin());
  const unsigned initialReads = bus.dataReads;
  for (uint8_t status : {0x00, 0x40, 0x80}) {
    bus.regs[0x1B] = status;
    assert(sensor.read(sample) == BMI160::Result::NotReady);
    assert(sample.accel[0] == 1234 && bus.dataReads == initialReads);
  }
  bus.regs[0x1B] = 0xC0;
  putWord(bus, 0x0C, -32768);
  putWord(bus, 0x0E, 32767);
  putWord(bus, 0x10, -656);
  putWord(bus, 0x12, 8192);
  putWord(bus, 0x14, -8192);
  putWord(bus, 0x16, -1);
  putWord(bus, 0x20, -512);
  bus.regs[0x18] = 0xFE; bus.regs[0x19] = 0xDC; bus.regs[0x1A] = 0xBA;
  assert(sensor.read(sample) == BMI160::Result::Ok);
  assert(sample.accel[0] == 8192 && sample.accel[1] == -8192 && sample.accel[2] == -1);
  assert(sample.gyro[0] == -32768 && sample.gyro[1] == 32767 && sample.gyro[2] == -656);
  assert(sample.sensorTime == 0xBADCFE);
  assert(BMI160::accelG(sample.accel[0]) == 1.0f);
  assert(std::fabs(BMI160::gyroDps(sample.gyro[2]) + 10.0f) < 0.001f);
  assert(BMI160::temperatureC(sample.temperature) == 22.0f);
  assert(std::isnan(BMI160::temperatureC(-32768)));
  assert(sensor.read(sample) == BMI160::Result::NotReady); // No duplicate frame.

  // SPI has no ACK: constant-low/high MISO must fail health checks, even if the
  // floating status appears to indicate both data-ready bits are set.
  for (uint8_t value : {0x00, 0xFF}) {
    bus.floatingByte = value;
    bus.disconnected = true;
    assert(sensor.read(sample) == BMI160::Result::IoError);
    assert(sample.accel[0] == 8192 && sample.sensorTime == 0xBADCFE);
    assert(!sensor.begin());
    bus.disconnected = false;
    assert(sensor.begin());
  }
  // A disconnect during the frame is caught by the post-read health check.
  bus.disconnectDuringData = true;
  bus.regs[0x1B] = 0xC0;
  assert(sensor.read(sample) == BMI160::Result::IoError);
  assert(sample.accel[0] == 8192 && sample.sensorTime == 0xBADCFE);
  bus.disconnectDuringData = false;
  bus.disconnected = false;
  assert(sensor.begin());
  // Sensor reset or ERR_REG failure should not emit data with wrong units.
  for (int reg : {0x02, 0x03}) {
    bus.regs[0x1B] = 0xC0;
    bus.regs[reg] = reg == 0x02 ? 1 : 0;
    assert(sensor.read(sample) == BMI160::Result::IoError);
    assert(sample.accel[0] == 8192 && sample.sensorTime == 0xBADCFE);
    assert(sensor.begin());
  }
  assert(bus.csHigh && !bus.active);
  std::cout << "BMI160 SPI driver tests passed\n";
}
