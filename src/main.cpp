#include <Arduino.h>
#include <SPI.h>
#include <esp_timer.h>

#include "protocentralAds1292r.h"
#include "ecgRespirationAlgo.h"
#include "BMI160.h"
#include "ImuKalman.h"
#include "DebouncedButton.h"

/**
 * ============================================================================
 * FIRMWARE TÍCH HỢP ĐỒNG THỜI 2 CẢM BIẾN TRÊN 1 ESP32-S3:
 * 1. ADS1292R (sEMG Điện cơ sinh học) trên FSPI (SPI2)
 * 2. GY-BMI160 (IMU 6 trục + Kalman) trên HSPI (SPI3)
 * Truyền dữ liệu song song qua 1 cổng Serial duy nhất @ 460800 baud.
 * ============================================================================
 * SƠ ĐỒ NỐI DÂY (ESP32-S3):
 * 
 * [ADS1292R - FSPI]                [BMI160 - HSPI]
 * CS    ---> GPIO 10               CS   ---> GPIO 15
 * SCK   ---> GPIO 12               SCK  ---> GPIO 6
 * MOSI  ---> GPIO 11               MOSI ---> GPIO 5
 * MISO  ---> GPIO 13               MISO ---> GPIO 7
 * PWDN  ---> GPIO 9                [Nút nhấn mốc Rep]
 * START ---> GPIO 8                BTN  ---> GPIO 3 <-> GND
 * DRDY  ---> GPIO 4
 * ============================================================================
 */

// --- Cấu hình chân ADS1292R (FSPI) ---
#define PIN_ADS_CS    10
#define PIN_ADS_PWDN  9
#define PIN_ADS_SCK   12
#define PIN_ADS_MOSI  11
#define PIN_ADS_MISO  13
#define PIN_ADS_START 8
#define PIN_ADS_DRDY  4

// --- Cấu hình chân BMI160 (HSPI) ---
#ifndef BMI160_MOSI_PIN
#define BMI160_MOSI_PIN 5
#endif
#ifndef BMI160_SCK_PIN
#define BMI160_SCK_PIN  6
#endif
#ifndef BMI160_MISO_PIN
#define BMI160_MISO_PIN 7
#endif
#ifndef BMI160_CS_PIN
#define BMI160_CS_PIN   15
#endif

#ifndef BUTTON_PIN
#define BUTTON_PIN      3
#endif

constexpr uint32_t SERIAL_BAUD = 2000000;

// ============================================================================
// KHỞI TẠO CÁC BUS VÀ ĐỐI TƯỢNG CẢM BIẾN
// ============================================================================
// 1. ADS1292R
SPIClass adsSpiBus(FSPI);
ads1292r ads1292;
ads1292OutputValues ecgData;

// 2. BMI160
SPIClass bmiSpi(HSPI);
BMI160 imu(bmiSpi, BMI160_CS_PIN);
ImuKalman kalman;
DebouncedButton button;

// Trạng thái BMI160
bool bmiConnected = false;
uint32_t bmiLastAttemptMs = 0;
uint32_t bmiLastSampleMs = 0;
uint32_t bmiLastStatsMs = 0;
uint32_t bmiSession = 0;
uint32_t bmiSequence = 0;
uint32_t bmiReceived = 0;
uint32_t bmiPrevReceived = 0;
uint32_t bmiIoErrors = 0;
uint32_t bmiSerialDrops = 0;
uint8_t bmiConsecutiveErrors = 0;

// Trạng thái & DSP của ADS1292R
uint32_t adsSampleCounter = 0;
unsigned long adsLastSamplePrint = 0;
float emgEnvelope = 0.0f;
float baselineNoise = 10.0f;
float mvcPeak = 120.0f;
float sensitivityMultiplier = 1.0f;
float noiseThreshold = 5.0f;
bool filterEnabled = true;

// ============================================================================
// BỘ LỌC TÍN HIỆU sEMG (Fs = 2000 Hz)
// ============================================================================
float filterHighPass20Hz(float input) {
  const float b0 =  0.956543f, b1 = -1.913086f, b2 = 0.956543f;
  const float a1 = -1.911197f, a2 =  0.914976f;
  static float x1 = 0, x2 = 0, y1 = 0, y2 = 0;
  float out = b0 * input + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
  x2 = x1; x1 = input; y2 = y1; y1 = out;
  return out;
}

float filterNotch50Hz(float input) {
  const float b0 =  0.996245f, b1 = -1.967959f, b2 = 0.996245f;
  const float a1 = -1.935869f, a2 =  0.960400f;
  static float x1 = 0, x2 = 0, y1 = 0, y2 = 0;
  float out = b0 * input + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
  x2 = x1; x1 = input; y2 = y1; y1 = out;
  return out;
}

float filterNotch100Hz(float input) {
  const float b0 =  0.984086f, b1 = -1.871843f, b2 = 0.984086f;
  const float a1 = -1.864071f, a2 =  0.960400f;
  static float x1 = 0, x2 = 0, y1 = 0, y2 = 0;
  float out = b0 * input + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
  x2 = x1; x1 = input; y2 = y1; y1 = out;
  return out;
}

float filterLowPass450Hz(float input) {
  const float b0 = 0.248341f, b1 = 0.496682f, b2 = 0.248341f;
  const float a1 = -0.184214f, a2 = 0.177578f;
  static float x1 = 0, x2 = 0, y1 = 0, y2 = 0;
  float out = b0 * input + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
  x2 = x1; x1 = input; y2 = y1; y1 = out;
  return out;
}

void resetAdsCalibration() {
  baselineNoise = emgEnvelope;
  if (baselineNoise < 1.0f) baselineNoise = 1.0f;
  float defaultSpan = filterEnabled ? 80.0f : 400.0f;
  mvcPeak = baselineNoise + defaultSpan;
  noiseThreshold = (baselineNoise * 0.25f < 2.5f) ? 2.5f : (baselineNoise * 0.25f);
  if (noiseThreshold > 20.0f) noiseThreshold = 20.0f;
  sensitivityMultiplier = 1.0f;
  Serial.printf("\n# [ADS CÂN CHỈNH LẠI] Mức nghỉ = %.0f | Đỉnh = %.0f | Ngưỡng ồn = %.1f | Độ nhạy = x1.00\n",
                baselineNoise, mvcPeak, noiseThreshold);
}

// Cấu hình thanh ghi ADS1292R
void configAdsRegisters() {
  ads1292r::ads1292StopReadDataContinuous(PIN_ADS_CS);
  delay(10);
  ads1292r::ads1292RegWrite(ADS1292_REG_CONFIG1, 0x04, PIN_ADS_CS); // 2000 SPS
  delay(10);
  ads1292r::ads1292RegWrite(ADS1292_REG_CONFIG2, 0xA0, PIN_ADS_CS); // VREF nội 2.42V
  delay(10);
  ads1292r::ads1292RegWrite(ADS1292_REG_RLDSENS, 0x00, PIN_ADS_CS); // RLDSENS tắt (tránh nối common-mode đè lên kênh đo)
  delay(10);
  ads1292r::ads1292RegWrite(ADS1292_REG_CH1SET, 0x40, PIN_ADS_CS);  // CH1 4x
  delay(10);
  ads1292r::ads1292RegWrite(ADS1292_REG_CH2SET, 0x40, PIN_ADS_CS);  // CH2 4x (sEMG electrode)
  delay(10);
  ads1292r::ads1292RegWrite(ADS1292_REG_RESP1, 0x02, PIN_ADS_CS);
  delay(10);
  ads1292r::ads1292RegWrite(ADS1292_REG_RESP2, 0x03, PIN_ADS_CS);
  delay(10);

  // Đọc kiểm tra toàn bộ 12 thanh ghi
  const char *regNames[] = {
      "ID       (0x00)", "CONFIG1  (0x01)", "CONFIG2  (0x02)",
      "LOFF     (0x03)", "CH1SET   (0x04)", "CH2SET   (0x05)",
      "RLDSENS  (0x06)", "LOFFSENS (0x07)", "LOFFSTAT (0x08)",
      "RESP1    (0x09)", "RESP2    (0x0A)", "GPIO     (0x0B)"};
  Serial.println("\n# --- BẢNG THANH GHI ADS1292R (CẤU HÌNH THỰC TẾ) ---");
  for (uint8_t i = 0; i <= 0x0B; i++) {
    uint8_t val = ads1292r::ads1292RegRead(i, PIN_ADS_CS);
    Serial.printf("#   [%02d] %-16s = 0x%02X\n", i, regNames[i], val);
  }

  ads1292r::ads1292StartReadDataContinuous(PIN_ADS_CS);
  delay(10);
  pinMode(PIN_ADS_START, OUTPUT);
  digitalWrite(PIN_ADS_START, HIGH);
  delay(10);
}

// ============================================================================
// HÀM QUẢN LÝ BMI160
// ============================================================================
void connectBmiSensor() {
  bmiConnected = false;
  bmiConnected = imu.begin();
  if (bmiConnected) {
    kalman.reset();
    ++bmiSession;
    bmiConsecutiveErrors = 0;
    bmiLastSampleMs = millis();
    Serial.printf("# BMI160 ready on SPI CS=%d: 100 Hz, +/-4 g, +/-500 dps; session=%lu\n",
                  BMI160_CS_PIN, (unsigned long)bmiSession);
    Serial.println("session,seq,host_us,sensor_ticks,ax_raw,ay_raw,az_raw,gx_raw,gy_raw,gz_raw,ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps,temp_c,ax_kal_g,ay_kal_g,az_kal_g,gx_kal_dps,gy_kal_dps,gz_kal_dps,roll_acc_deg,pitch_acc_deg,roll_kal_deg,pitch_kal_deg,accel_trusted,button_state");
  } else {
    Serial.printf("# BMI160 init: %s; check wiring SCK=%d MOSI=%d MISO=%d CS=%d\n",
                  imu.error(), BMI160_SCK_PIN, BMI160_MOSI_PIN, BMI160_MISO_PIN, BMI160_CS_PIN);
  }
  bmiLastAttemptMs = millis();
}

void emitBmiSample(const BMI160::Sample &sample, uint64_t hostUs) {
  const float accel[] = {BMI160::accelG(sample.accel[0]), BMI160::accelG(sample.accel[1]), BMI160::accelG(sample.accel[2])};
  const float gyro[] = {BMI160::gyroDps(sample.gyro[0]), BMI160::gyroDps(sample.gyro[1]), BMI160::gyroDps(sample.gyro[2])};
  const ImuKalman::Output filtered = kalman.update(accel, gyro, hostUs);
  char line[384];
  const int length = snprintf(line, sizeof(line),
      "%lu,%lu,%llu,%lu,%d,%d,%d,%d,%d,%d,%.5f,%.5f,%.5f,%.3f,%.3f,%.3f,%.2f,"
      "%.5f,%.5f,%.5f,%.3f,%.3f,%.3f,%.2f,%.2f,%.2f,%.2f,%u,%u\n",
      (unsigned long)bmiSession, (unsigned long)bmiSequence++,
      (unsigned long long)hostUs, (unsigned long)sample.sensorTime,
      sample.accel[0], sample.accel[1], sample.accel[2],
      sample.gyro[0], sample.gyro[1], sample.gyro[2],
      accel[0], accel[1], accel[2], gyro[0], gyro[1], gyro[2],
      BMI160::temperatureC(sample.temperature),
      filtered.accel[0], filtered.accel[1], filtered.accel[2],
      filtered.gyro[0], filtered.gyro[1], filtered.gyro[2],
      filtered.rollAccel, filtered.pitchAccel, filtered.roll, filtered.pitch,
      unsigned(filtered.accelTrusted), unsigned(button.pressed()));
  if (length > 0 && size_t(length) < sizeof(line)) {
    if (Serial.availableForWrite() >= length) {
      Serial.write(reinterpret_cast<const uint8_t *>(line), size_t(length));
    } else {
      ++bmiSerialDrops;
    }
  }
}

// ============================================================================
// SETUP
// ============================================================================
void setup() {
  Serial.setTxBufferSize(16384);
  Serial.begin(SERIAL_BAUD);
  delay(800);

  Serial.println("\n# ==================================================");
  Serial.println("#   ESP32-S3 DUAL-SENSOR: ADS1292R sEMG + BMI160 IMU");
  Serial.printf("#   Serial baud: %lu | TX buffer: 8192 bytes\n", (unsigned long)SERIAL_BAUD);
  Serial.println("# ==================================================");

  // 1. Khởi tạo nút nhấn
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  button.reset(digitalRead(BUTTON_PIN) == LOW, millis());

  // 2. Khởi tạo BMI160 (HSPI)
  digitalWrite(BMI160_CS_PIN, HIGH);
  pinMode(BMI160_CS_PIN, OUTPUT);
  bmiSpi.begin(BMI160_SCK_PIN, BMI160_MISO_PIN, BMI160_MOSI_PIN, -1);
  connectBmiSensor();

  // 3. Khởi tạo ADS1292R (FSPI)
  pinMode(PIN_ADS_CS, OUTPUT);
  digitalWrite(PIN_ADS_CS, HIGH);
  pinMode(PIN_ADS_DRDY, INPUT_PULLUP);
  pinMode(PIN_ADS_START, OUTPUT);
  digitalWrite(PIN_ADS_START, LOW);
  adsSpiBus.begin(PIN_ADS_SCK, PIN_ADS_MISO, PIN_ADS_MOSI, -1);
  ads1292r::ads1292Init(adsSpiBus, PIN_ADS_CS, PIN_ADS_PWDN, PIN_ADS_START);
  uint8_t devId = ads1292r::ads1292GetDeviceID(PIN_ADS_CS);
  Serial.printf("# ADS1292R Device ID = 0x%02X\n", devId);
  configAdsRegisters();

  bmiLastStatsMs = millis();
}

// ============================================================================
// LOOP
// ============================================================================
void loop() {
  // --- 1. Nút bấm mốc Rep ---
  button.update(digitalRead(BUTTON_PIN) == LOW, millis());

  // --- 2. Lắng nghe lệnh điều khiển Serial ---
  if (Serial.available()) {
    char cmd = Serial.read();
    if (cmd == 'c' || cmd == 'C') {
      resetAdsCalibration();
    } else if (cmd == 'f' || cmd == 'F') {
      filterEnabled = !filterEnabled;
      resetAdsCalibration();
      Serial.printf("# [DSP FILTER] %s\n", filterEnabled ? "BẬT" : "TẮT");
    } else if (cmd == '+' || cmd == '=') {
      sensitivityMultiplier *= 1.4f;
      if (sensitivityMultiplier > 50.0f) sensitivityMultiplier = 50.0f;
      Serial.printf("# [ĐỘ NHẠY] Tăng nhạy: x%.2f\n", sensitivityMultiplier);
    } else if (cmd == '-' || cmd == '_') {
      sensitivityMultiplier *= 0.7f;
      if (sensitivityMultiplier < 0.1f) sensitivityMultiplier = 0.1f;
      Serial.printf("# [ĐỘ NHẠY] Giảm nhạy: x%.2f\n", sensitivityMultiplier);
    } else if (cmd == 'k' || cmd == 'K') {
      kalman.reset();
      Serial.println("# [BMI] Reset Kalman filter");
    } else if (cmd == 's' || cmd == '?') {
      Serial.printf("# connected=%u spi_cs=%d session=%lu received=%lu io_errors=%lu drops=%lu error=%s\n",
                    bmiConnected, BMI160_CS_PIN, (unsigned long)bmiSession,
                    (unsigned long)bmiReceived, (unsigned long)bmiIoErrors,
                    (unsigned long)bmiSerialDrops, imu.error());
    } else if (cmd == 'r' || cmd == 'R') {
      connectBmiSensor();
      configAdsRegisters();
      resetAdsCalibration();
    }
  }

  // --- 3. ĐỌC DỮ LIỆU sEMG ADS1292R (2000 SPS khi DRDY LOW) ---
  if (ads1292.getAds1292EcgAndRespirationSamples(PIN_ADS_DRDY, PIN_ADS_CS, &ecgData)) {
      adsSampleCounter++;
      uint64_t hwTimestampUs = esp_timer_get_time();

      int32_t ch1Raw = ecgData.sDaqVals[0];
      int32_t ch2Raw = ecgData.sDaqVals[1];
      // Tự động nhận diện kênh đo sEMG: chọn kênh có biên độ dao động lớn hơn
      int32_t emgRaw = (labs(ch2Raw) >= labs(ch1Raw)) ? ch2Raw : ch1Raw;
      int16_t emgRaw16 = (int16_t)(emgRaw >> 8);

      // DSP Filtering (20-450 Hz)
      float emgSignal = (float)emgRaw16;
      if (filterEnabled) {
        emgSignal = filterHighPass20Hz(emgSignal);
        emgSignal = filterNotch50Hz(emgSignal);
        emgSignal = filterNotch100Hz(emgSignal);
        emgSignal = filterLowPass450Hz(emgSignal);
      }
      int16_t emgFiltered16 = (int16_t)emgSignal;

      // Tính bao hình Envelope (Moving Absolute Mean)
      float rectified = fabsf(emgSignal);
      float alpha = (rectified > emgEnvelope) ? 0.05f : 0.005f;
      emgEnvelope = (1.0f - alpha) * emgEnvelope + alpha * rectified;

      // Dynamic baseline & peak adaptation
      if (emgEnvelope < baselineNoise) {
        baselineNoise = 0.995f * baselineNoise + 0.005f * emgEnvelope;
      } else {
        baselineNoise = 0.99995f * baselineNoise + 0.00005f * emgEnvelope;
      }
      float targetGate = baselineNoise * 0.25f;
      if (targetGate < 2.5f) targetGate = 2.5f;
      if (targetGate > 20.0f) targetGate = 20.0f;
      noiseThreshold = 0.999f * noiseThreshold + 0.001f * targetGate;

      if (emgEnvelope > mvcPeak) {
        mvcPeak = 0.90f * mvcPeak + 0.10f * emgEnvelope;
      } else {
        float minSpan = filterEnabled ? 20.0f : 80.0f;
        if (mvcPeak > baselineNoise + minSpan) mvcPeak *= 0.99998f;
      }

      // Xuất mẫu sEMG dataset: 2000 SPS đầy đủ
      char adsDataset[96];
      int adsLen = snprintf(adsDataset, sizeof(adsDataset),
                            "$D,%lu,%llu,%ld,%ld,%d,%d,%d\n",
                            (unsigned long)adsSampleCounter,
                            (unsigned long long)hwTimestampUs,
                            (long)ch1Raw, (long)emgRaw,
                            (int)emgRaw16, (int)emgFiltered16, 0);
      if (adsLen > 0 && Serial.availableForWrite() >= adsLen) {
        Serial.write(reinterpret_cast<const uint8_t *>(adsDataset), adsLen);
      }

      // Telemetry UI Preview 20 Hz (mỗi 50ms)
      if (millis() - adsLastSamplePrint >= 50) {
        adsLastSamplePrint = millis();
        float effectiveGate = noiseThreshold / sensitivityMultiplier;
        if (effectiveGate < 0.8f) effectiveGate = 0.8f;
        float effectiveEnv = emgEnvelope - (baselineNoise + effectiveGate);
        int percent = 0;
        if (effectiveEnv > 0.0f) {
          float minSpan = filterEnabled ? 15.0f : 50.0f;
          float rawSpan = mvcPeak - (baselineNoise + effectiveGate);
          if (rawSpan < minSpan) rawSpan = minSpan;
          float span = rawSpan / sensitivityMultiplier;
          percent = (int)((effectiveEnv / span) * 100.0f);
          if (percent > 100) percent = 100;
        }

        const char *trangThai = "THA LONG";
        if (percent >= 60) trangThai = "GONG MANH!";
        else if (percent >= 25) trangThai = "GONG VUA";
        else if (percent >= 8) trangThai = "GONG NHE";

        char bar[21];
        int barLength = percent / 5;
        for (int i = 0; i < 20; i++) bar[i] = (i < barLength) ? '=' : ' ';
        bar[20] = '\0';

        char telemLine[192];
        int tLen = snprintf(telemLine, sizeof(telemLine),
                            "Raw:%6ld | Filt:%6ld | Env:%4ld | Base:%4ld | x%.2f | Luc:[%-20s] %3d%% | %s | %s\n",
                            (long)emgRaw, (long)emgSignal, (long)emgEnvelope, (long)baselineNoise,
                            sensitivityMultiplier, bar, percent, trangThai, filterEnabled ? "DSP:ON" : "DSP:OFF");
        if (tLen > 0 && Serial.availableForWrite() >= tLen) {
          Serial.write(reinterpret_cast<const uint8_t *>(telemLine), tLen);
        }
      }
    }

  // --- 4. ĐỌC DỮ LIỆU IMU BMI160 (100 Hz = mỗi 10ms) ---
  if (!bmiConnected) {
    if (millis() - bmiLastAttemptMs >= 2000) connectBmiSensor();
  } else {
    static uint32_t lastBmiPollMs = 0;
    uint32_t nowMs = millis();
    if (nowMs - lastBmiPollMs >= 10) { // 100 Hz
      lastBmiPollMs = nowMs;
      BMI160::Sample sample{};
      uint64_t hostUs = esp_timer_get_time();
      BMI160::Result result = imu.read(sample);
      if (result == BMI160::Result::Ok) {
        bmiConsecutiveErrors = 0;
        bmiLastSampleMs = nowMs;
        ++bmiReceived;
        emitBmiSample(sample, hostUs);
      } else if (result == BMI160::Result::IoError) {
        ++bmiIoErrors;
        ++bmiConsecutiveErrors;
      }
      if (bmiConsecutiveErrors >= 10 || (nowMs - bmiLastSampleMs >= 2000)) {
        Serial.printf("# BMI160 offline: %s; reconnecting...\n", imu.error());
        bmiConnected = false;
        bmiLastAttemptMs = nowMs;
      }
    }
  }

  // Thống kê định kỳ BMI160 mỗi 2 giây
  uint32_t curMs = millis();
  if (curMs - bmiLastStatsMs >= 2000) {
    if (bmiConnected) {
      Serial.printf("# SPS=%.1f io_errors=%lu serial_drops=%lu\n",
                    (bmiReceived - bmiPrevReceived) * 1000.0f / (curMs - bmiLastStatsMs),
                    (unsigned long)bmiIoErrors, (unsigned long)bmiSerialDrops);
      bmiPrevReceived = bmiReceived;
    }
    bmiLastStatsMs = curMs;
  }
}
