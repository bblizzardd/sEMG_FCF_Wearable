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

  // Đảm bảo thanh ghi RLDSENS và CH1SET/CH2SET được thiết lập chuẩn xác
  uint8_t rldVal = ads1292r::ads1292RegRead(ADS1292_REG_RLDSENS, PIN_ADS_CS);
  if (rldVal != 0x2C) {
    ads1292r::ads1292RegWrite(ADS1292_REG_RLDSENS, 0x2C, PIN_ADS_CS);
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

// Biến lưu trữ bộ lọc DC offset và bao hình lực cơ (Envelope)
float emgDcOffset = 0.0f;
float emgEnvelope = 0.0f;
bool dcInitialized = false;

void loop() {
  // Đọc một mẫu mới mỗi khi DRDY báo dữ liệu sẵn sàng (1 kSPS).
  if (ads1292.getAds1292EcgAndRespirationSamples(PIN_ADS_DRDY, PIN_ADS_CS,
                                                 &ecgData)) {
    sampleCounter++;

    int32_t emgRaw = ecgData.sDaqVals[0]; // Kênh analog 1: IN1P - IN1N

    // Khóa ngay mức DC thực tế khi nhận mẫu đầu tiên để không bị sốc điện thế
    if (!dcInitialized && emgRaw != 0) {
      emgDcOffset = (float)emgRaw;
      dcInitialized = true;
    }

    // 1. Khử trôi DC (DC tracking filter) để đưa dao động về tâm 0
    emgDcOffset = 0.995f * emgDcOffset + 0.005f * (float)emgRaw;
    float emgAc = (float)emgRaw - emgDcOffset;

    // 2. Tính bao hình lực cơ (Rectification + Low-pass filter)
    float emgRectified = fabsf(emgAc);
    emgEnvelope = 0.95f * emgEnvelope + 0.05f * emgRectified;

    // 3. In kết quả định kỳ mỗi 60ms (~16 dòng/giây để mắt theo dõi mượt mà)
    if (millis() - lastSamplePrint >= 60) {
      lastSamplePrint = millis();

      // Giới hạn trần tối đa (15,000) và sàn tối thiểu (3,500) để chống nhiễu sốc/giật dây
      const float MAX_PEAK_CEILING = 15000.0f;
      const float MAX_PEAK_FLOOR   = 3500.0f;

      static float maxPeak = 4500.0f;
      if (emgEnvelope > maxPeak) {
        maxPeak = emgEnvelope;
        if (maxPeak > MAX_PEAK_CEILING) {
          maxPeak = MAX_PEAK_CEILING; // Khống chế trần an toàn
        }
      } else {
        maxPeak = maxPeak * 0.999f; // Hạ dần rất chậm để thích ứng
        if (maxPeak < MAX_PEAK_FLOOR) {
          maxPeak = MAX_PEAK_FLOOR;
        }
      }

      // Chuẩn hóa phần trăm: Nghỉ thả lỏng ~500-600, Gồng mạnh ~maxPeak (3500 - 10000)
      float baseline = 600.0f;
      float dynamicRange = maxPeak - baseline;
      if (dynamicRange < 1500.0f) dynamicRange = 1500.0f;

      int percent = (int)((emgEnvelope - baseline) / dynamicRange * 100.0f);
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
      if (percent >= 65) {
        trangThai = "GONG MANH!";
      } else if (percent >= 25) {
        trangThai = "GONG VUA";
      }

      printMsg("Raw:%6ld | Env:%5ld | Luc:[%-20s] %3d%% | %s\n",
               (long)emgRaw, (long)emgEnvelope, bar, percent, trangThai);
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
