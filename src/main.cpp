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

  // BẮT BUỘC THEO DATASHEET TI: Gửi SDATAC (0x11) để chip chấp nhận đọc/ghi thanh ghi
  ads1292r::ads1292StopReadDataContinuous(PIN_ADS_CS);
  delay(10);

  // Đảm bảo các thanh ghi chuẩn xác:
  // - CONFIG1 (0x04): 2000 SPS
  // - CONFIG2 (0xA0): Bật Reference Buffer nội (VREF = 2.42V)
  // - RLDSENS (0xBC): BẬT RLD BUFFER (Bit 7=1) + RLD từ Ch1 & Ch2 (0xBC)
  // - CH1SET  (0x40): Kênh 1 bật, Gain 4x, normal electrode
  // - CH2SET  (0x40): Kênh 2 bật, Gain 4x (kết nối trực tiếp với jack 3.5mm điện cực)
  // - RESP1   (0x02): Tắt điều chế hô hấp
  // - RESP2   (0x03): RLDREF nội (AVDD+AVSS)/2
  uint8_t cfg1 = ads1292r::ads1292RegRead(ADS1292_REG_CONFIG1, PIN_ADS_CS);
  if (cfg1 != 0x04) {
    ads1292r::ads1292RegWrite(ADS1292_REG_CONFIG1, 0x04, PIN_ADS_CS);
    delay(10);
  }
  uint8_t cfg2 = ads1292r::ads1292RegRead(ADS1292_REG_CONFIG2, PIN_ADS_CS);
  if (cfg2 != 0xA0) {
    ads1292r::ads1292RegWrite(ADS1292_REG_CONFIG2, 0xA0, PIN_ADS_CS);
    delay(10);
  }
  uint8_t rldVal = ads1292r::ads1292RegRead(ADS1292_REG_RLDSENS, PIN_ADS_CS);
  if (rldVal != 0xBC) {
    ads1292r::ads1292RegWrite(ADS1292_REG_RLDSENS, 0xBC, PIN_ADS_CS);
    delay(10);
  }
  uint8_t ch1Val = ads1292r::ads1292RegRead(ADS1292_REG_CH1SET, PIN_ADS_CS);
  if (ch1Val != 0x40) {
    ads1292r::ads1292RegWrite(ADS1292_REG_CH1SET, 0x40, PIN_ADS_CS);
    delay(10);
  }
  uint8_t ch2Val = ads1292r::ads1292RegRead(ADS1292_REG_CH2SET, PIN_ADS_CS);
  if (ch2Val != 0x40) {
    ads1292r::ads1292RegWrite(ADS1292_REG_CH2SET, 0x40, PIN_ADS_CS);
    delay(10);
  }
  uint8_t resp1Val = ads1292r::ads1292RegRead(ADS1292_REG_RESP1, PIN_ADS_CS);
  if (resp1Val != 0x02) {
    ads1292r::ads1292RegWrite(ADS1292_REG_RESP1, 0x02, PIN_ADS_CS);
    delay(10);
  }
  uint8_t resp2Val = ads1292r::ads1292RegRead(ADS1292_REG_RESP2, PIN_ADS_CS);
  if (resp2Val != 0x03) {
    ads1292r::ads1292RegWrite(ADS1292_REG_RESP2, 0x03, PIN_ADS_CS);
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

  pinMode(PIN_ADS_CS, OUTPUT);
  digitalWrite(PIN_ADS_CS, HIGH);
  pinMode(PIN_ADS_DRDY, INPUT_PULLUP);
  pinMode(PIN_ADS_START, OUTPUT);
  digitalWrite(PIN_ADS_START, LOW);

  // 1. Khởi động SPI bus cho ESP32-S3 (dùng -1 cho SS để manual digitalWrite CS 100% tin cậy)
  adsSpiBus.begin(PIN_ADS_SCK, PIN_ADS_MISO, PIN_ADS_MOSI, -1);

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
// CÁC BỘ LỌC XỬ LÝ TÍN HIỆU sEMG (Fs = 2000 Hz / 2 kSPS)
// ============================================================================

// 1. Bộ lọc High-Pass 20Hz (Butterworth Bậc 2, Fs=2000Hz) khử triệt để trôi DC và nhiễu cử động cáp/da
float filterHighPass20Hz(float input) {
  const float b0 =  0.956543f;
  const float b1 = -1.913086f;
  const float b2 =  0.956543f;
  const float a1 = -1.911197f;
  const float a2 =  0.914976f;

  static float x1 = 0.0f, x2 = 0.0f;
  static float y1 = 0.0f, y2 = 0.0f;

  float output = b0 * input + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
  x2 = x1;
  x1 = input;
  y2 = y1;
  y1 = output;
  return output;
}

// 2. Bộ lọc IIR Notch 50Hz (Bậc 2, r=0.98) triệt tiêu sóng điện lưới 50Hz (Fs=2000Hz)
float filterNotch50Hz(float input) {
  const float b0 =  0.996245f;
  const float b1 = -1.967959f;
  const float b2 =  0.996245f;
  const float a1 = -1.935869f;
  const float a2 =  0.960400f;

  static float x1 = 0.0f, x2 = 0.0f;
  static float y1 = 0.0f, y2 = 0.0f;

  float output = b0 * input + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
  x2 = x1;
  x1 = input;
  y2 = y1;
  y1 = output;
  return output;
}

// 3. Bộ lọc IIR Notch 100Hz (Bậc 2, r=0.98) triệt tiêu sóng hài 100Hz (Fs=2000Hz)
float filterNotch100Hz(float input) {
  const float b0 =  0.984086f;
  const float b1 = -1.871843f;
  const float b2 =  0.984086f;
  const float a1 = -1.864071f;
  const float a2 =  0.960400f;

  static float x1 = 0.0f, x2 = 0.0f;
  static float y1 = 0.0f, y2 = 0.0f;

  float output = b0 * input + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
  x2 = x1;
  x1 = input;
  y2 = y1;
  y1 = output;
  return output;
}

// 4. Bộ lọc Low-Pass 450Hz (Butterworth Bậc 2, Fs=2000Hz) - Chuẩn SENIAM (Dải tần mỏi cơ 20 - 450 Hz)
float filterLowPass450Hz(float input) {
  const float b0 =  0.248341f;
  const float b1 =  0.496682f;
  const float b2 =  0.248341f;
  const float a1 = -0.184214f;
  const float a2 =  0.177578f;

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
float baselineNoise = 10.0f; // Mức nghỉ thực tế sau lọc DSP (thang 16-bit thường ~5-15)
float mvcPeak = 120.0f;       // Mức đỉnh danh định khi gồng (DSP ON: ~100-200, DSP OFF: ~500)
float sensitivityMultiplier = 1.0f; // Hệ số nhạy (+/- từ bàn phím)
float noiseThreshold = 5.0f;  // Ngưỡng Noise Gate tự thích ứng: triệt tiêu dao động sàn khi thả lỏng về chuẩn 0%

bool filterEnabled = true; // BẬT GIẢM NHIỄU mặc định để triệt tiêu điện lưới 50Hz và nhiễu sóng hài
float dcOffset = 0.0f;

void resetCalibration() {
  baselineNoise = emgEnvelope;
  if (baselineNoise < 1.0f) baselineNoise = 1.0f;
  float defaultSpan = filterEnabled ? 80.0f : 400.0f;
  mvcPeak = baselineNoise + defaultSpan;
  noiseThreshold = (baselineNoise * 0.25f < 2.5f) ? 2.5f : (baselineNoise * 0.25f);
  if (noiseThreshold > 20.0f) noiseThreshold = 20.0f;
  sensitivityMultiplier = 1.0f;
  printMsg("\n>>> [CÂN CHỈNH LẠI] Mức nghỉ = %.0f | Đỉnh = %.0f | Ngưỡng ồn = %.1f | Độ nhạy = x1.00 <<<\n\n",
           baselineNoise, mvcPeak, noiseThreshold);
}

void loop() {
  // Lắng nghe lệnh từ bàn phím qua Serial Monitor hoặc Web Visualizer
  if (Serial.available()) {
    char cmd = Serial.read();
    if (cmd == 'c' || cmd == 'C') {
      resetCalibration();
    } else if (cmd == 'r' || cmd == 'R') {
      printMsg("\n[ADS1292R] Đang khởi tạo lại chip phần cứng...\n");
      ads1292r::ads1292Init(adsSpiBus, PIN_ADS_CS, PIN_ADS_PWDN, PIN_ADS_START);
      dumpRegisters();
      resetCalibration();
    } else if (cmd == 'd' || cmd == 'D') {
      dumpRegisters();
    } else if (cmd == 'f' || cmd == 'F') {
      filterEnabled = !filterEnabled;
      resetCalibration();
      printMsg("\n[DSP FILTER] Đã chuyển sang: %s\n\n",
               filterEnabled ? "BẬT (Khử nhiễu 4 tầng)" : "TẮT (RAW PASSTHROUGH - Không giảm nhiễu)");
    } else if (cmd == '+' || cmd == '=') {
      sensitivityMultiplier *= 1.40f; // Tăng nhạy 40% mỗi lần bấm
      if (sensitivityMultiplier > 50.0f) sensitivityMultiplier = 50.0f;
      printMsg("\n[ĐỘ NHẠY] Tăng nhạy lên x%.2f (Dễ đạt 100%% hơn)\n\n", sensitivityMultiplier);
    } else if (cmd == '-' || cmd == '_') {
      sensitivityMultiplier *= 0.70f;
      if (sensitivityMultiplier < 0.1f) sensitivityMultiplier = 0.1f;
      printMsg("\n[ĐỘ NHẠY] Giảm nhạy xuống x%.2f\n\n", sensitivityMultiplier);
    } else if (cmd == 's' || cmd == '?') {
      uint8_t currentId = ads1292r::ads1292GetDeviceID(PIN_ADS_CS);
      float effG = noiseThreshold / sensitivityMultiplier;
      if (effG < 0.8f) effG = 0.8f;
      printMsg("\n=======================================================\n");
      printMsg(">>> THÔNG TIN ĐỘ NHẠY & CÂN CHỈNH HIỆN TẠI <<<\n");
      printMsg("   - Chip Device ID             : 0x%02X\n", currentId);
      printMsg("   - Chế độ Giảm nhiễu (DSP)    : %s\n", filterEnabled ? "BẬT" : "TẮT (RAW)");
      printMsg("   - Hệ số độ nhạy (Sensitivity): x%.2f\n", sensitivityMultiplier);
      printMsg("   - Mức nghỉ (Baseline)       : %.1f\n", baselineNoise);
      printMsg("   - Ngưỡng ồn hiệu dụng (Gate) : %.1f\n", effG);
      printMsg("   - Mức gồng đỉnh (Peak)      : %.1f\n", mvcPeak);
      printMsg("   - Dải lực hiệu dụng (Span)   : %.1f\n", (mvcPeak - (baselineNoise + effG)) / sensitivityMultiplier);
      printMsg("=======================================================\n\n");
    }
  }

  // Đọc một mẫu mới mỗi khi DRDY báo dữ liệu sẵn sàng (2000 SPS / 2 kSPS).
  if (ads1292.getAds1292EcgAndRespirationSamples(PIN_ADS_DRDY, PIN_ADS_CS,
                                                 &ecgData)) {
    sampleCounter++;

    // Đọc đồng thời 2 kênh (giữ cả 24-bit gốc cho dataset và 16-bit cho DSP)
    int32_t ch1_raw24 = ecgData.sDaqVals[0];
    int32_t ch2_raw24 = ecgData.sDaqVals[1];
    int32_t ch1_16 = (int32_t)(ch1_raw24 >> 8);
    int32_t ch2_16 = (int32_t)(ch2_raw24 >> 8);

    // KÊNH ĐIỆN CƠ CHÍNH: Cố định cứng Kênh 2 (Kênh gắn điện cực Biceps), không chuyển kênh động
    // Loại bỏ hoàn toàn hiện tượng pha giật (phase discontinuity) do chuyển kênh
    int32_t emgRaw = ch2_16;

    float emgSignal = 0.0f;
    if (filterEnabled) {
      // CHUỖI LỌC SỐ ĐA TẦNG CHUẨN SENIAM (20 - 450 Hz @ Fs=2000Hz):
      // 1. High-Pass 20Hz (Butterworth Bậc 2: Khử triệt để trôi DC và nhiễu cử động cáp)
      // 2. Notch 50Hz (IIR Bậc 2: Triệt tiêu sóng điện lưới 50Hz)
      // 3. Notch 100Hz (IIR Bậc 2: Triệt tiêu sóng hài 100Hz)
      // 4. Low-Pass 450Hz (Butterworth Bậc 2: Bảo toàn 100% phổ mỏi cơ 20-450Hz cho tính MDF/MNF)
      float emgHp = filterHighPass20Hz((float)emgRaw);
      float emgN50 = filterNotch50Hz(emgHp);
      float emgN100 = filterNotch100Hz(emgN50);
      emgSignal = filterLowPass450Hz(emgN100);
    } else {
      // TẮT GIẢM NHIỄU (RAW PASSTHROUGH):
      if (sampleCounter < 100) {
        dcOffset = (float)emgRaw;
      } else {
        dcOffset = 0.999f * dcOffset + 0.001f * (float)emgRaw;
      }
      emgSignal = (float)emgRaw - dcOffset;
    }

    // Thời gian lấy mẫu phần cứng chính xác tới microgiây (Hardware Timestamp)
    uint32_t sampleTimeUs = (uint32_t)esp_timer_get_time();

    // 1. STREAM TOÀN BỘ MẪU DATASET 2000 SPS VỚI TIMESTAMP PHẦN CỨNG VI GIÂY CHÍNH XÁC
    // Định dạng: $D,sampleIndex,timestampUs,ch1_raw24,ch2_raw24,ch2_raw16,filtered16,leadOff
    Serial.printf("$D,%u,%lu,%ld,%ld,%ld,%ld,%d\n",
                  sampleCounter, (unsigned long)sampleTimeUs, (long)ch1_raw24, (long)ch2_raw24, (long)emgRaw, (long)emgSignal, ecgData.leadoffDetected ? 1 : 0);

    // 5. Tính bao hình lực cơ (Chỉnh lưu Rectify + Lọc làm mượt ~75ms @ Fs=2000Hz)
    float emgRectified = fabsf(emgSignal);
    emgEnvelope = 0.993356f * emgEnvelope + 0.006644f * emgRectified;

    // Tự động khởi tạo mức nghỉ ban đầu khi bộ lọc đã ổn định (sau 400 mẫu = 0.2s)
    static bool baselineInitialized = false;
    if (!baselineInitialized && sampleCounter > 400) {
      baselineNoise = emgEnvelope;
      if (baselineNoise < 1.0f) baselineNoise = 1.0f;
      float defaultSpan = filterEnabled ? 80.0f : 400.0f;
      mvcPeak = baselineNoise + defaultSpan;
      noiseThreshold = (baselineNoise * 0.25f < 2.5f) ? 2.5f : (baselineNoise * 0.25f);
      if (noiseThreshold > 20.0f) noiseThreshold = 20.0f;
      baselineInitialized = true;
    }

    // 3. Thuật toán tự động bám mức nghỉ nhanh hơn khi nhả cơ
    if (baselineInitialized) {
      if (emgEnvelope < baselineNoise) {
        // Hạ mức nghỉ nhanh hơn để dập tắt nhiễu sau khi gồng
        baselineNoise = 0.85f * baselineNoise + 0.15f * emgEnvelope;
      } else if (emgEnvelope < baselineNoise + noiseThreshold * 1.5f) {
        // Chỉ bám tăng nhẹ mức nghỉ khi cơ thực sự đang thả lỏng
        baselineNoise = baselineNoise + 0.00005f * (emgEnvelope - baselineNoise);
      }

      // Giữ noiseThreshold tự thích ứng nhẹ theo mức nghỉ
      float targetGate = baselineNoise * 0.25f;
      if (targetGate < 2.5f) targetGate = 2.5f;
      if (targetGate > 20.0f) targetGate = 20.0f;
      noiseThreshold = 0.999f * noiseThreshold + 0.001f * targetGate;

      // Tự động bám mức gồng tối đa (Dynamic Peak Tracking)
      if (emgEnvelope > mvcPeak) {
        mvcPeak = 0.90f * mvcPeak + 0.10f * emgEnvelope; // Mở rộng trần khi gồng mạnh hơn
      } else {
        // Thu hẹp trần từ từ nếu lâu không gồng
        float minSpan = filterEnabled ? 20.0f : 80.0f;
        if (mvcPeak > baselineNoise + minSpan) {
          mvcPeak *= 0.99998f;
        }
      }
    }

    // 4. In kết quả định kỳ mỗi 20ms (50 mẫu/giây = 50 Hz, dành riêng cho UI Preview)
    if (millis() - lastSamplePrint >= 20) {
      lastSamplePrint = millis();

      // Ngưỡng chết chống rung sàn (Noise Gate) thích ứng theo hệ số độ nhạy
      // Tăng nhạy => gate thu nhỏ tỷ lệ thuận, phát hiện ngay các co thắt cơ nhẹ nhất
      float effectiveGate = noiseThreshold / sensitivityMultiplier;
      if (effectiveGate < 0.8f) effectiveGate = 0.8f; // Giữ tối thiểu 0.8 để triệt tiêu nhiễu ADC quantization

      float effectiveEnvelope = emgEnvelope - (baselineNoise + effectiveGate);

      int percent = 0;
      if (effectiveEnvelope > 0.0f) {
        float minSpan = filterEnabled ? 15.0f : 50.0f;
        float rawSpan = mvcPeak - (baselineNoise + effectiveGate);
        if (rawSpan < minSpan) rawSpan = minSpan;
        float span = rawSpan / sensitivityMultiplier;

        float rawPercent = (effectiveEnvelope / span) * 100.0f;
        percent = (int)rawPercent;
        if (percent > 100) percent = 100;
      }

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

      // In đầy đủ cả Raw (chưa lọc) và Filt (đã lọc DSP)
      printMsg("Raw:%6ld | Filt:%6ld | Env:%4ld | Base:%4ld | x%.2f | Luc:[%-20s] %3d%% | %s | %s\n",
               (long)emgRaw, (long)emgSignal, (long)emgEnvelope, (long)baselineNoise, sensitivityMultiplier, bar, percent, trangThai, filterEnabled ? "DSP:ON" : "DSP:OFF");
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

