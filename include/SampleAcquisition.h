#pragma once

#include <Arduino.h>

struct AcquiredSample {
  uint32_t sequence;
  uint32_t timestampUs;
  int32_t ch1;
  int32_t ch2;
  bool leadOff;
};

struct AcquisitionStats {
  uint32_t edges;
  uint32_t captured;
  uint32_t missed;
  uint32_t queueDrops;
};

// Initialize after ADC setup. Only the acquisition task reads conversion data.
bool beginAcquisition(int drdyPin, int csPin);
bool receiveSample(AcquiredSample &sample);
AcquisitionStats acquisitionStats();
// Serialize register commands with SPI reads; commands interrupt acquisition.
void lockAcquisitionSpi();
void unlockAcquisitionSpi();
