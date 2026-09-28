#include "ecgRespirationAlgo.h"
#include "protocentralAds1292r.h"
#include <Arduino.h>
#include <SPI.h>

/**
 * ============================================================================
 * CHƯƠNG TRÌNH KIỂM TRA GIAO TIẾP SPI VỚI MODULE PROTOCENTRAL ADS1292R
 * CHO ESP32-S3 (SPI_MODE1, 1MHz, ĐỌC DEVICE ID & DỮ LIỆU sEMG)
 * ============================================================================
 *
 * SƠ ĐỒ ĐẤU DÂY:
 *   ADS1292R Pin       ESP32-S3 Pin          Ghi chú
 *   --------------------------------------------------------------------------
 *   CS   (SS)    ---> GPIO 10               Chip Select
 *   SCK  (CLK)   ---> GPIO 12               Xung Clock SPI (Chế độ SPI_MODE1)
 *   MOSI (DIN)   ---> GPIO 11               ESP32 -> ADS1292R
 *   MISO (DOUT)  <--- GPIO 13               ADS1292R -> ESP32
 *   PWDN / RESET ---> GPIO 9                Reset phần cứng
 *   START        ---> GPIO 8                Start conversion (hoặc chân bất kỳ)
 *   DRDY         <--- GPIO 4                Data Ready báo mẫu mới (active LOW)
 *   3.3V         ---> 3.3V                  Nguồn nuôi 3.3V
 *   GND          ---> GND                   Nối chung mass
 */

#define PIN_ADS_CS 10
#define PIN_ADS_PWDN 9
#define PIN_ADS_SCK 12
#define PIN_ADS_MOSI 11
#define PIN_ADS_MISO 13

// Nếu bạn nối START hoặc DRDY vào chân khác, hãy đổi số chân tại đây:
#define PIN_ADS_START 8
#define PIN_ADS_DRDY 4

ads1292r ads1292;
ads1292OutputValues ecgData;
SPIClass adsSpiBus(FSPI);

void printMsg(const char *format, ...) {
  char locBuf[256];
  va_list arg;
  va_start(arg, format);
  vsnprintf(locBuf, sizeof(locBuf), format, arg);
  va_end(arg);

  Serial.print(locBuf);
}

// In danh sách các thanh ghi quan trọng của ADS1292 và khởi động ADC
void dumpRegisters() {

  printMsg("\n--- BẢNG THANH GHI ADS1292R ---\n");
  const char *regNames[] = {
      "ID       (0x00)", "CONFIG1  (0x01)", "CONFIG2  (0x02)",
      "LOFF     (0x03)", "CH1SET   (0x04)", "CH2SET   (0x05)",
      "RLDSENS  (0x06)", "LOFFSENS (0x07)", "LOFFSTAT (0x08)",
      "RESP1    (0x09)", "RESP2    (0x0A)", "GPIO     (0x0B)"};

  // Đảm bảo thanh ghi CONFIG2 (bật VREF buffer), RLDSENS và CH1SET/CH2SET chuẩn xác
  uint8_t cfg2 = ads1292r::ads1292RegRead(ADS1292_REG_CONFIG2, PIN_ADS_CS);
  if (cfg2 != 0xA0) {
    ads1292r::ads1292RegWrite(ADS1292_REG_CONFIG2, 0xA0, PIN_ADS_CS); // Bật Reference Buffer (VREF = 2.42V)
    delay(10);
  }
  uint8_t rldVal = ads1292r::ads1292RegRead(ADS1292_REG_RLDSENS, PIN_ADS_CS);
  if (rldVal != 0x2C) {
    ads1292r::ads1292RegWrite(ADS1292_REG_RLDSENS, 0x2C, PIN_ADS_CS);
    delay(10);
  }
  uint8_t ch1Val = ads1292r::ads1292RegRead(ADS1292_REG_CH1SET, PIN_ADS_CS);
  if (ch1Val != 0x40) {
    ads1292r::ads1292RegWrite(ADS1292_REG_CH1SET, 0x40, PIN_ADS_CS); // Gain = 4x chuẩn
    delay(10);
  }
  uint8_t ch2Val = ads1292r::ads1292RegRead(ADS1292_REG_CH2SET, PIN_ADS_CS);
  if (ch2Val != 0x40) {
    ads1292r::ads1292RegWrite(ADS1292_REG_CH2SET, 0x40, PIN_ADS_CS); // Gain = 4x chuẩn
    delay(10);
  }

  for (uint8_t i = 0; i <= 0x0B; i++) {
    uint8_t val = ads1292r::ads1292RegRead(i, PIN_ADS_CS);
    printMsg("  [%02d] %-16s = 0x%02X\n", i, regNames[i], val);
  }

  // TRÌNH TỰ KHỞI ĐỘNG CHUẨN CỦA ADS1292:
  // 1. Gửi lệnh RDATAC (0x10) TRƯỚC khi kéo START pin lên HIGH (tránh xung đột DRDY)
  ads1292r::ads1292StartReadDataContinuous(PIN_ADS_CS);
  delay(10);

  // 2. Kéo chân START lên HIGH để phần cứng bắt đầu chuyển đổi ADC
  pinMode(PIN_ADS_START, OUTPUT);
  digitalWrite(PIN_ADS_START, HIGH);
  delay(10);

  printMsg("-------------------------------\n\n");
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  printMsg("\n==================================================\n");
  printMsg("     ESP32-S3 KIỂM TRA PROTOCENTRAL ADS1292R     \n");
  printMsg("==================================================\n");
  printMsg(" Cấu hình chân SPI:\n");
  printMsg("   - CS   (SS)  : GPIO %d\n", PIN_ADS_CS);
  printMsg("   - SCK  (CLK) : GPIO %d\n", PIN_ADS_SCK);
  printMsg("   - MOSI (DIN) : GPIO %d\n", PIN_ADS_MOSI);
  printMsg("   - MISO (DOUT): GPIO %d\n", PIN_ADS_MISO);
  printMsg("   - PWDN/RESET : GPIO %d\n", PIN_ADS_PWDN);
  printMsg("   - START      : GPIO %d\n", PIN_ADS_START);
  printMsg("   - DRDY       : GPIO %d\n", PIN_ADS_DRDY);
  printMsg("==================================================\n");

  pinMode(PIN_ADS_DRDY, INPUT_PULLUP);
  pinMode(PIN_ADS_START, OUTPUT);
  digitalWrite(PIN_ADS_START, LOW);

  // 1. Khởi động SPI bus cho ESP32-S3 với chân tùy chỉnh
  adsSpiBus.begin(PIN_ADS_SCK, PIN_ADS_MISO, PIN_ADS_MOSI, PIN_ADS_CS);

  // 2. Khởi tạo chip ADS1292R với SPI bus và cấu hình thanh ghi mặc định
  printMsg("-> Đang thiết lập phần cứng ADS1292R...\n");
  ads1292r::ads1292Init(adsSpiBus, PIN_ADS_CS, PIN_ADS_PWDN, PIN_ADS_START);

  // 3. Đọc mã định danh Device ID
  uint8_t devId = ads1292r::ads1292GetDeviceID(PIN_ADS_CS);
  printMsg("-> Mã Device ID đọc được: 0x%02X\n", devId);

  if (devId == 0x73) {
    printMsg(
        ">>> [THÀNH CÔNG RỰC RỠ] ĐÃ NHẬN DIỆN CHÍNH XÁC CHIP ADS1292R! <<<\n");
  } else if (devId == 0x53 || devId == 0x72 || devId == 0x52) {
    printMsg(
        ">>> [THÀNH CÔNG] ĐÃ KẾT NỐI VỚI CHIP DÒNG ADS1291 / ADS1292! <<<\n");
  } else if (devId == 0x00) {
    printMsg(">>> [CHƯA CÓ TÍN HIỆU] MISO = 0x00 (Kiểm tra nguồn 3.3V, tiếp "
             "xúc chân DOUT/SCK) <<<\n");
  } else if (devId == 0xFF) {
    printMsg(
        ">>> [TREO MỨC CAO] MISO = 0xFF (Kiểm tra dây CS, SCK, nguồn) <<<\n");
  } else {
    printMsg(">>> [PHẢN HỒI LẠ: 0x%02X] (Đã có phản hồi nhưng mã ID chưa khớp) "
             "<<<\n",
             devId);
  }

  // In toàn bộ giá trị thanh ghi sau khi cấu hình và kích hoạt chuyển đổi
  dumpRegisters();
}

unsigned long lastSamplePrint = 0;
uint32_t sampleCounter = 0;

// ============================================================================
// CÁC BỘ LỌC XỬ LÝ TÍN HIỆU sEMG (Fs = 1000 Hz)
// ============================================================================

// 1. Bộ lọc High-Pass 20Hz (Bậc 1) khử trôi DC và nhiễu cử động chậm
float filterHighPass20Hz(float input) {
  const float alpha = 0.888365f; // Fs=1000Hz, fc=20Hz
  static float prevIn = 0.0f;
  static float prevOut = 0.0f;

  float output = alpha * (prevOut + input - prevIn);
  prevIn = input;
  prevOut = output;
  return output;
}

// 2. Bộ lọc IIR Notch 50Hz (Bậc 2, r=0.96) triệt tiêu sóng điện lưới 50Hz
float filterNotch50Hz(float input) {
  const float b0 =  0.976345f;
  const float b1 = -1.857119f;
  const float b2 =  0.976345f;
  const float a1 = -1.826029f;
  const float a2 =  0.921600f;

  static float x1 = 0.0f, x2 = 0.0f;
  static float y1 = 0.0f, y2 = 0.0f;

  float output = b0 * input + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
  x2 = x1;
  x1 = input;
  y2 = y1;
  y1 = output;
  return output;
}

// 3. Bộ lọc IIR Notch 100Hz (Bậc 2, r=0.96) triệt tiêu sóng hài 100Hz (từ sạc laptop, nguồn xung)
float filterNotch100Hz(float input) {
  const float b0 =  0.964189f;
  const float b1 = -1.560090f;
  const float b2 =  0.964189f;
  const float a1 = -1.553313f;
  const float a2 =  0.921600f;

  static float x1 = 0.0f, x2 = 0.0f;
  static float y1 = 0.0f, y2 = 0.0f;

  float output = b0 * input + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
  x2 = x1;
  x1 = input;
  y2 = y1;
  y1 = output;
  return output;
}

// 4. Bộ lọc Low-Pass 150Hz (Butterworth Bậc 2) cắt sạch nhiễu cao tần (RF, WiFi, Switching Noise)
float filterLowPass150Hz(float input) {
  const float b0 =  0.131106f;
  const float b1 =  0.262213f;
  const float b2 =  0.131106f;
  const float a1 = -0.747789f;
  const float a2 =  0.272215f;

  static float x1 = 0.0f, x2 = 0.0f;
  static float y1 = 0.0f, y2 = 0.0f;

  float output = b0 * input + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
  x2 = x1;
  x1 = input;
  y2 = y1;
  y1 = output;
  return output;
}

// Biến lưu trữ bao hình lực cơ (Envelope) và tự động thích ứng dải lực
float emgEnvelope = 0.0f;
float baselineNoise = 800.0f; // Tự động bám mức nghỉ thấp nhất thực tế
float mvcPeak = 3000.0f;      // Tự động bám mức đỉnh khi gồng
float sensitivityMultiplier = 1.0f; // Hệ số nhạy (+/- từ bàn phím)

void resetCalibration() {
  baselineNoise = emgEnvelope;
  mvcPeak = baselineNoise + 2000.0f;
  sensitivityMultiplier = 1.0f;
  printMsg("\n>>> [CÂN CHỈNH LẠI] Đã gán Mức nghỉ = %.0f | Đỉnh = %.0f | Độ nhạy = x1.00 <<<\n\n",
           baselineNoise, mvcPeak);
}

void loop() {
  // Lắng nghe lệnh từ bàn phím qua Serial Monitor
  if (Serial.available()) {
    char cmd = Serial.read();
    if (cmd == 'c' || cmd == 'C' || cmd == 'r' || cmd == 'R') {
      resetCalibration();
    } else if (cmd == '+' || cmd == '=') {
      sensitivityMultiplier *= 1.25f;
      if (sensitivityMultiplier > 10.0f) sensitivityMultiplier = 10.0f;
      printMsg("\n[ĐỘ NHẠY] Tăng nhạy lên x%.2f (Dễ đạt 100%% hơn)\n\n", sensitivityMultiplier);
    } else if (cmd == '-' || cmd == '_') {
      sensitivityMultiplier *= 0.8f;
      if (sensitivityMultiplier < 0.2f) sensitivityMultiplier = 0.2f;
      printMsg("\n[ĐỘ NHẠY] Giảm nhạy xuống x%.2f\n\n", sensitivityMultiplier);
    } else if (cmd == 's' || cmd == 'S' || cmd == '?') {
      printMsg("\n=======================================================\n");
      printMsg(">>> THÔNG TIN ĐỘ NHẠY & CÂN CHỈNH HIỆN TẠI <<<\n");
      printMsg("   - Hệ số độ nhạy (Sensitivity): x%.2f\n", sensitivityMultiplier);
      printMsg("   - Mức nghỉ (Baseline)       : %.0f\n", baselineNoise);
      printMsg("   - Mức gồng đỉnh (Peak)      : %.0f\n", mvcPeak);
      printMsg("   - Dải lực hiệu dụng (Span)   : %.0f\n", (mvcPeak - baselineNoise) / sensitivityMultiplier);
      printMsg("=======================================================\n\n");
    }
  }

  // Đọc một mẫu mới mỗi khi DRDY báo dữ liệu sẵn sàng (1 kSPS).
  if (ads1292.getAds1292EcgAndRespirationSamples(PIN_ADS_DRDY, PIN_ADS_CS,
                                                 &ecgData)) {
    sampleCounter++;

    int32_t ch1Raw = ecgData.sDaqVals[0];
    int32_t ch2Raw = ecgData.sDaqVals[1];
    // Jack 3.5mm của ProtoCentral ADS1292R nối vào Channel 2 (IN2P/IN2N).
    // Tự động chọn kênh có biên độ dao động lớn hơn giữa Ch1 và Ch2:
    int32_t emgRaw = (labs(ch2Raw) > labs(ch1Raw)) ? ch2Raw : ch1Raw;

    // CHUỖI LỌC SỐ ĐA TẦNG (DSP CASCADE FILTER CHAIN):
    // 1. High-Pass 20Hz (khử DC, drift, cử động dây)
    // 2. Notch 50Hz (triệt sóng điện lưới 50Hz)
    // 3. Notch 100Hz (triệt sóng hài 100Hz từ sạc laptop/nguồn xung)
    // 4. Low-Pass 150Hz (cắt nhiễu cao tần RF/WiFi/Clock)
    float emgHp = filterHighPass20Hz((float)emgRaw);
    float emgN50 = filterNotch50Hz(emgHp);
    float emgN100 = filterNotch100Hz(emgN50);
    float emgClean = filterLowPass150Hz(emgN100);

    // 5. Tính bao hình lực cơ (Chỉnh lưu Rectify + Lọc làm mượt ~75ms)
    float emgRectified = fabsf(emgClean);
    emgEnvelope = 0.985f * emgEnvelope + 0.015f * emgRectified;

    // Tự động khởi tạo mức nghỉ ban đầu khi tín hiệu đã có mẫu thực
    static bool baselineInitialized = false;
    if (!baselineInitialized && sampleCounter > 300 && emgEnvelope > 50.0f) {
      baselineNoise = emgEnvelope;
      mvcPeak = baselineNoise + 2000.0f;
      baselineInitialized = true;
    }

    // 3. Thuật toán tự động bám mức nghỉ (Continuous Adaptive Baseline)
    if (baselineInitialized) {
      if (emgEnvelope < baselineNoise) {
        // Nếu đo được mức êm hơn, lập tức hạ mức nghỉ xuống
        baselineNoise = 0.98f * baselineNoise + 0.02f * emgEnvelope;
      } else {
        // Tăng cực kỳ chậm để chống trôi khi đang nghỉ
        baselineNoise = baselineNoise + 0.00005f * (emgEnvelope - baselineNoise);
      }

      // Tự động bám mức gồng tối đa (Dynamic Peak Tracking)
      if (emgEnvelope > mvcPeak) {
        mvcPeak = 0.95f * mvcPeak + 0.05f * emgEnvelope; // Mở rộng trần khi gồng mạnh hơn
      } else {
        // Thu hẹp trần từ từ nếu lâu không gồng
        float minSpan = 700.0f;
        if (mvcPeak > baselineNoise + minSpan) {
          mvcPeak *= 0.99995f;
        }
      }
    }

    // 4. In kết quả định kỳ mỗi 60ms (~16 dòng/giây)
    if (millis() - lastSamplePrint >= 60) {
      lastSamplePrint = millis();

      // Dải lực động thực tế
      float rawSpan = (mvcPeak - baselineNoise);
      if (rawSpan < 600.0f) rawSpan = 600.0f;
      float span = rawSpan / sensitivityMultiplier;

      float rawPercent = (emgEnvelope - baselineNoise) / span * 100.0f;
      int percent = (int)rawPercent;
      if (percent < 0) percent = 0;
      if (percent > 100) percent = 100;

      // Vẽ thanh hiển thị lực gồm 20 vạch
      int barLength = percent / 5; // 0 -> 20
      char bar[21];
      for (int i = 0; i < 20; i++) {
        bar[i] = (i < barLength) ? '=' : ' ';
      }
      bar[20] = '\0';

      const char *trangThai = "THA LONG";
      if (percent >= 60) {
        trangThai = "GONG MANH!";
      } else if (percent >= 25) {
        trangThai = "GONG VUA";
      } else if (percent >= 8) {
        trangThai = "GONG NHE";
      }

      printMsg("Raw:%6ld | Env:%4ld | Base:%4ld | x%.2f | Luc:[%-20s] %3d%% | %s | C1:%ld C2:%ld\n",
               (long)emgRaw, (long)emgEnvelope, (long)baselineNoise, sensitivityMultiplier, bar, percent, trangThai, (long)ch1Raw, (long)ch2Raw);
    }
  }

  // Nếu chân DRDY chưa được nối hoặc kiểm tra định kỳ mỗi 3 giây
  static unsigned long lastCheckTime = 0;
  if (millis() - lastCheckTime > 3000) {
    lastCheckTime = millis();
    if (sampleCounter == 0) {
      uint8_t currentId = ads1292r::ads1292GetDeviceID(PIN_ADS_CS);
      printMsg(
          "[Chờ mẫu] Chưa thấy xung DRDY (GPIO %d = %d) | Device ID = 0x%02X\n",
          PIN_ADS_DRDY, digitalRead(PIN_ADS_DRDY), currentId);
    }
  }
}

