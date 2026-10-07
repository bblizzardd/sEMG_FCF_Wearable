#pragma once
#include "Arduino.h"
#include <array>
#include <cassert>
#include <cstddef>
#include <vector>

constexpr uint8_t MSBFIRST = 1, SPI_MODE0 = 0;
struct SPISettings {
  uint32_t hz;
  uint8_t order, mode;
  SPISettings(uint32_t h, uint8_t o, uint8_t m) : hz(h), order(o), mode(m) {}
};
class SPIClass;
extern SPIClass *fakeBus;

// Models SPI framing, CS selection, reset back to I2C, and bus disconnects.
class SPIClass {
 public:
  std::array<uint8_t, 128> regs{};
  bool disconnected = false, badPmu = false, disconnectDuringData = false;
  uint8_t floatingByte = 0xFF;
  int corruptRegister = -1;
  unsigned writes = 0, dataReads = 0, selections = 0;
  bool selected = false, csHigh = true, active = false;
  std::vector<std::vector<uint8_t>> frames;

  SPIClass() { regs[0] = 0xD1; fakeBus = this; }
  void beginTransaction(const SPISettings &settings) {
    assert(!active && csHigh);
    assert(settings.hz == 1000000 && settings.order == MSBFIRST && settings.mode == SPI_MODE0);
    if (hasWritten_) assert(fakeTimeUs - lastWriteUs_ >= 450);
    active = true;
  }
  void setCs(uint8_t value) {
    if (value == LOW) {
      assert(active && csHigh);
      frame_.clear();
      csHigh = false;
    } else if (!csHigh) {
      assert(active && frame_.size() >= 2);
      frames.push_back(frame_);
      if (frame_[0] == 0xFF) { selected = true; ++selections; }
      if (resetPending_) { selected = false; resetPending_ = false; }
      csHigh = true;
    }
  }
  uint8_t transfer(uint8_t value) {
    assert(active && !csHigh);
    frame_.push_back(value);
    if (frame_.size() == 1) {
      reg_ = value & 0x7F;
      read_ = (value & 0x80) != 0;
      if (selected && read_ && reg_ == 0x0C) ++dataReads;
      return 0;
    }
    if (disconnected || !selected) return floatingByte;
    if (read_) {
      assert(value == 0); // Master clocks receive bytes.
      if (disconnectDuringData && reg_ == 0x0F) disconnected = true;
      if (disconnected) return floatingByte;
      const uint8_t offset = reg_++;
      if (offset == 0x17) regs[0x1B] &= ~0xC0;
      return offset == corruptRegister ? regs[offset] ^ 1 : regs[offset];
    }
    assert(frame_.size() == 2); // Driver writes single registers.
    ++writes;
    hasWritten_ = true;
    lastWriteUs_ = fakeTimeUs;
    if (reg_ == 0x7E) {
      if (value == 0xB6) {
        regs.fill(0); regs[0] = 0xD1; resetPending_ = true;
      }
      if (value == 0x11 && !badPmu) regs[3] |= 0x10;
      if (value == 0x15 && !badPmu) regs[3] |= 0x04;
    } else regs[reg_] = value;
    return 0;
  }
  void endTransaction() { assert(active && csHigh); active = false; }

 private:
  uint8_t reg_ = 0;
  bool read_ = false, resetPending_ = false, hasWritten_ = false;
  uint64_t lastWriteUs_ = 0;
  std::vector<uint8_t> frame_;
};
