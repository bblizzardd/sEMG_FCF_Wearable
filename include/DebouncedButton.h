#pragma once
#include <stdint.h>

class DebouncedButton {
 public:
  void reset(bool pressed, uint32_t nowMs) {
    stable_ = raw_ = pressed;
    changedMs_ = nowMs;
  }
  void update(bool pressed, uint32_t nowMs) {
    if (pressed != raw_) {
      raw_ = pressed;
      changedMs_ = nowMs;
    }
    if (uint32_t(nowMs - changedMs_) >= 30) stable_ = raw_;
  }
  bool pressed() const { return stable_; }
 private:
  bool stable_ = false, raw_ = false;
  uint32_t changedMs_ = 0;
};
