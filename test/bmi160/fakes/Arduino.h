#pragma once
#include <stdint.h>
extern unsigned long fakeDelayMs;
extern uint64_t fakeTimeUs;
constexpr uint8_t LOW = 0, HIGH = 1, OUTPUT = 1;
inline void delay(unsigned long ms) { fakeDelayMs += ms; fakeTimeUs += ms * 1000; }
inline void delayMicroseconds(unsigned int us) { fakeTimeUs += us; }
void digitalWrite(uint8_t pin, uint8_t value);
void pinMode(uint8_t pin, uint8_t mode);
