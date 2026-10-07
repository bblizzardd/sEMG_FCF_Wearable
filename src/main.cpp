#include <Arduino.h>
#include <SPI.h>
#include <esp_timer.h>

#include "BMI160.h"
#include "ImuKalman.h"

#ifndef BMI160_MOSI_PIN
#define BMI160_MOSI_PIN 5
#endif
#ifndef BMI160_SCK_PIN
#define BMI160_SCK_PIN 6
#endif
#ifndef BMI160_MISO_PIN
#define BMI160_MISO_PIN 7
#endif
#ifndef BMI160_CS_PIN
#define BMI160_CS_PIN 15
#endif

namespace {
constexpr uint32_t SERIAL_BAUD = 460800;
constexpr uint32_t RETRY_MS = 2000;
constexpr uint32_t STALE_MS = 1000;
// Dedicated SPI controller; GPIO 4,8,9,10,11,12,13 remain available.
SPIClass bmiSpi(HSPI);
BMI160 imu(bmiSpi, BMI160_CS_PIN);
ImuKalman kalman;
bool connected = false;
uint32_t lastAttemptMs = 0;
uint32_t lastSampleMs = 0;
uint32_t lastStatsMs = 0;
uint32_t session = 0;
uint32_t sequence = 0;
uint32_t received = 0;
uint32_t previousReceived = 0;
uint32_t ioErrors = 0;
uint32_t serialDrops = 0;
uint8_t consecutiveErrors = 0;

void printHeader() {
  Serial.println("session,seq,host_us,sensor_ticks,ax_raw,ay_raw,az_raw,gx_raw,gy_raw,gz_raw,ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps,temp_c,ax_kal_g,ay_kal_g,az_kal_g,gx_kal_dps,gy_kal_dps,gz_kal_dps,roll_acc_deg,pitch_acc_deg,roll_kal_deg,pitch_kal_deg,accel_trusted");
}

void printStatus() {
  Serial.printf("# connected=%u spi_cs=%d session=%lu received=%lu io_errors=%lu serial_drops=%lu error=%s\n",
                connected, BMI160_CS_PIN, (unsigned long)session,
                (unsigned long)received, (unsigned long)ioErrors,
                (unsigned long)serialDrops, imu.error());
}

void connectSensor() {
  connected = false;
  connected = imu.begin();
  if (connected) {
    kalman.reset();
    ++session;
    consecutiveErrors = 0;
    lastSampleMs = millis();
    Serial.printf("# BMI160 ready on SPI CS=%d: 100 Hz, +/-4 g, +/-500 dps; session=%lu\n",
                  BMI160_CS_PIN, (unsigned long)session);
    printHeader();
  } else {
    Serial.printf("# %s; check power, SCK, MOSI, MISO, CS; retry in 2 s\n", imu.error());
  }
  lastAttemptMs = millis();
}

void emitSample(const BMI160::Sample &sample, uint64_t hostUs) {
  const float accel[] = {BMI160::accelG(sample.accel[0]), BMI160::accelG(sample.accel[1]), BMI160::accelG(sample.accel[2])};
  const float gyro[] = {BMI160::gyroDps(sample.gyro[0]), BMI160::gyroDps(sample.gyro[1]), BMI160::gyroDps(sample.gyro[2])};
  const ImuKalman::Output filtered = kalman.update(accel, gyro, hostUs);
  char line[512];
  const int length = snprintf(line, sizeof(line),
      "%lu,%lu,%llu,%lu,%d,%d,%d,%d,%d,%d,%.5f,%.5f,%.5f,%.3f,%.3f,%.3f,%.2f,"
      "%.5f,%.5f,%.5f,%.3f,%.3f,%.3f,%.2f,%.2f,%.2f,%.2f,%u\n",
      (unsigned long)session, (unsigned long)sequence++,
      (unsigned long long)hostUs, (unsigned long)sample.sensorTime,
      sample.accel[0], sample.accel[1], sample.accel[2],
      sample.gyro[0], sample.gyro[1], sample.gyro[2],
      accel[0], accel[1], accel[2], gyro[0], gyro[1], gyro[2],
      BMI160::temperatureC(sample.temperature),
      filtered.accel[0], filtered.accel[1], filtered.accel[2],
      filtered.gyro[0], filtered.gyro[1], filtered.gyro[2],
      filtered.rollAccel, filtered.pitchAccel, filtered.roll, filtered.pitch,
      unsigned(filtered.accelTrusted));
  if (length <= 0 || size_t(length) >= sizeof(line) || Serial.availableForWrite() < length) {
    ++serialDrops;
    return;
  }
  Serial.write(reinterpret_cast<const uint8_t *>(line), size_t(length));
}
} // namespace

void setup() {
  Serial.setTxBufferSize(4096);
  Serial.begin(SERIAL_BAUD);
  delay(1000);
  digitalWrite(BMI160_CS_PIN, HIGH);
  pinMode(BMI160_CS_PIN, OUTPUT);
  bmiSpi.begin(BMI160_SCK_PIN, BMI160_MISO_PIN, BMI160_MOSI_PIN, -1);
  Serial.printf("# GY-BMI160 / ESP32-S3: SPI mode 0, 1 MHz; SCK=%d MOSI=%d MISO=%d CS=%d baud=%lu\n",
                BMI160_SCK_PIN, BMI160_MOSI_PIN, BMI160_MISO_PIN, BMI160_CS_PIN,
                (unsigned long)SERIAL_BAUD);
  Serial.println("# Commands: r = reinitialize, s or ? = status, k = reset Kalman. CSV units: g, deg/s, deg C.");
  connectSensor();
  lastStatsMs = millis();
}

void loop() {
  // Bound command work so a continuous stream of input cannot starve reads.
  if (Serial.available()) {
    const char command = Serial.read();
    if (command == 'r' || command == 'R') connectSensor();
    else if (command == 's' || command == '?') printStatus();
    else if (command == 'k' || command == 'K') { kalman.reset(); Serial.println("# Kalman reset"); }
  }

  if (!connected) {
    if (millis() - lastAttemptMs >= RETRY_MS) connectSensor();
    delay(1);
    return;
  }

  BMI160::Sample sample{};
  // Host time marks the start of polling; it is not a DRDY interrupt timestamp.
  const uint64_t hostUs = esp_timer_get_time();
  const BMI160::Result result = imu.read(sample);
  if (result == BMI160::Result::Ok) {
    consecutiveErrors = 0;
    lastSampleMs = millis();
    ++received;
    emitSample(sample, hostUs);
  } else if (result == BMI160::Result::IoError) {
    ++ioErrors;
    ++consecutiveErrors;
  } else {
    consecutiveErrors = 0;
  }
  if (consecutiveErrors >= 3 || millis() - lastSampleMs >= STALE_MS) {
    Serial.printf("# Sensor offline or stale: %s; retry in 2 s\n", imu.error());
    connected = false;
    lastAttemptMs = millis();
  }

  const uint32_t now = millis();
  if (now - lastStatsMs >= 1000) {
    Serial.printf("# SPS=%.1f io_errors=%lu serial_drops=%lu\n",
                  (received - previousReceived) * 1000.0f / (now - lastStatsMs),
                  (unsigned long)ioErrors, (unsigned long)serialDrops);
    previousReceived = received;
    lastStatsMs = now;
  }
  delay(1); // Poll DRDY faster than 100 Hz; never emit stale data as a new sample.
}
