// ESP32-S3 ADS1292R High-Precision 24-bit sEMG Acquisition Firmware
// Tương thích PlatformIO & ESP32-S3 DevKitC-1

#include "ADS1292R.h"
#include <Arduino.h>
#include <SPI.h>

// ============================================================================
// CẤU HÌNH PHẦN CỨNG CHÂN GPIO (ESP32-S3 kết nối ADS1292R)
// ============================================================================
#define ADS_PIN_CLK -1   // Không dùng external clock (module mặc định CLKSEL=HIGH, dùng internal oscillator)
#define ADS_PIN_GPIO2 8  // GPIO2 phụ của ADS1292R, kéo thấp nếu không dùng
#define ADS_PIN_GPIO1 18 // GPIO1 phụ của ADS1292R, kéo thấp nếu không dùng
#define ADS_PIN_SCK 17   // SCK / SCLK (SPI Clock)
#define ADS_PIN_MISO 16  // MISO / DOUT (SPI Master In Slave Out)
#define ADS_PIN_MOSI 15  // MOSI / DIN (SPI Master Out Slave In)
#define ADS_PIN_CS 7     // CS / SS (Chip Select, Active LOW)
#define ADS_PIN_DRDY 6   // DRDY (Data Ready, ngắt phần cứng ngõ vào)
#define ADS_PIN_START 5  // START pin (kích hoạt chuyển đổi)
#define ADS_PIN_RESET 4  // PWDN / RESET pin (Active LOW)

#define BUTTON_PIN                                                             \
  -1 // Đặt -1 nếu không dùng nút ngoài (tránh dùng GPIO 0 vì là chân BOOT
     // strapping)

// ============================================================================
// CẤU HÌNH TÙY CHỌN HOẠT ĐỘNG
// ============================================================================
// Đặt là true nếu muốn khởi động ở chế độ phát xung vuông nội 1Hz để kiểm tra
// phần cứng Đặt là false để đo tín hiệu điện cơ thực tế từ điện cực dán sEMG
bool testSignalMode = false;

// Đối tượng Driver ADS1292R
ADS1292R ads;

// FreeRTOS Task và Đồng bộ ngắt
static TaskHandle_t adsTaskHandle = NULL;
volatile unsigned long isrCount = 0;

static const char *logicLevelName(int pin) {
  if (pin < 0) {
    return "NC";
  }
  return digitalRead(pin) == HIGH ? "HIGH" : "LOW";
}

static void printAdsPinLevels() {
  Serial.println("  -> Muc logic hien tai tren ESP32:");
  Serial.printf("     CLK=%s, CS=%s, DRDY=%s, START=%s, RESET=%s\n",
                logicLevelName(ADS_PIN_CLK), logicLevelName(ADS_PIN_CS),
                logicLevelName(ADS_PIN_DRDY), logicLevelName(ADS_PIN_START),
                logicLevelName(ADS_PIN_RESET));
  Serial.printf("     SCK=%s, MISO=%s, MOSI=%s, GPIO1=%s, GPIO2=%s\n",
                logicLevelName(ADS_PIN_SCK), logicLevelName(ADS_PIN_MISO),
                logicLevelName(ADS_PIN_MOSI), logicLevelName(ADS_PIN_GPIO1),
                logicLevelName(ADS_PIN_GPIO2));
}

// Ngắt phần cứng chân DRDY (khi chân DRDY kéo xuống mức LOW = có mẫu mới)
void IRAM_ATTR drdyISR() {
  BaseType_t xHigherPriorityTaskWoken = pdFALSE;
  vTaskNotifyGiveFromISR(adsTaskHandle, &xHigherPriorityTaskWoken);
  portYIELD_FROM_ISR(xHigherPriorityTaskWoken);
}

// Tác vụ FreeRTOS chạy độc lập trên Core 1 để đọc dữ liệu SPI với độ trễ tối
// thiểu
void adsAcquisitionTask(void *pvParameters) {
  ADS1292R_Sample sample;

  while (true) {
    // Chờ thông báo từ ngắt DRDY (không tốn CPU khi đang chờ)
    if (ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(50)) == pdPASS) {
      if (ads.readSample(sample)) {
        int isButtonPressed =
            (BUTTON_PIN >= 0 && digitalRead(BUTTON_PIN) == LOW) ? 1 : 0;

        // Xuất dòng dữ liệu chuẩn CSV tốc độ cao (921600 baud)
        // Định dạng: timestamp_ms,raw_ch1,raw_ch2,emg_ch1_mv,emg_ch2_mv,button
        Serial.printf("%lu,%ld,%ld,%.4f,%.4f,%d\n", millis(), sample.ch1_raw,
                      sample.ch2_raw, sample.ch1_mv, sample.ch2_mv,
                      isButtonPressed);
      }
    } else {
      // Yield CPU để không chiếm dụng watchdog khi chưa có ngắt DRDY
      vTaskDelay(pdMS_TO_TICKS(10));
    }
  }
}

void setup() {
  Serial.begin(921600);

  // Chờ cổng USB CDC trên ESP32-S3 ổn định
  unsigned long startWait = millis();
  while (!Serial && (millis() - startWait < 1500)) {
    delay(10);
  }
  delay(200);

  Serial.println("\n==================================================");
  Serial.println("   ESP32-S3 + ADS1292R 24-bit sEMG Acquisition    ");
  Serial.println("==================================================");
  Serial.flush();

  // Cấu hình nút bấm (nếu có sử dụng)
  if (BUTTON_PIN >= 0) {
    pinMode(BUTTON_PIN, INPUT_PULLUP);
  }

  // Thiết lập sơ đồ chân cho ADS1292R
  ADS1292R_Pins pins;
  pins.sck = ADS_PIN_SCK;
  pins.mosi = ADS_PIN_MOSI;
  pins.miso = ADS_PIN_MISO;
  pins.cs = ADS_PIN_CS;
  pins.drdy = ADS_PIN_DRDY;
  pins.start = ADS_PIN_START;
  pins.reset = ADS_PIN_RESET;
  pins.clk = ADS_PIN_CLK;
  pins.gpio1 = ADS_PIN_GPIO1;
  pins.gpio2 = ADS_PIN_GPIO2;

  // Khởi tạo ADS1292R với SPI tốc độ thấp để debug chắc chắn trên dây cắm
  // breadboard. Với clock ADS 512kHz, SCLK đọc/ghi thanh ghi không nên chạy sát
  // giới hạn.
  int attempt = 1;
  while (!ads.begin(pins, 250000)) {
    uint8_t id = ads.getDeviceID();
    Serial.printf("\n[ADS1292R] Lan thu %d: Doc duoc ID = 0x%02X\n", attempt++,
                  id);

    // Đọc thử 4 thanh ghi đầu tiên để kiểm tra đường truyền SPI
    uint8_t regs[4] = {0};
    ads.readRegisters(0x00, 4, regs);
    Serial.printf(
        "  -> Gia tri 4 thanh ghi [0..3]: 0x%02X 0x%02X 0x%02X 0x%02X\n",
        regs[0], regs[1], regs[2], regs[3]);

    // Chẩn đoán dựa trên giá trị ID đọc được qua SPI (CS=LOW)
    if (id == 0xFF) {
      Serial.println("  -> ID=0xFF: ADS KHONG LAI MISO (MISO float HIGH do pull-up).");
      Serial.println("     Kiem tra: day MISO (GPIO16->DOUT), day CS (GPIO7->CS).");
    } else if (id == 0x00) {
      Serial.println("  -> ID=0x00: ADS tra toan bit 0 qua SPI. Chip khong dap ung lenh.");
      Serial.println("     Co the: chua co clock (CLKSEL?), reset chua xong, hoac mat nguon.");
    } else {
      Serial.printf("  -> ID doc duoc: 0x%02X (Ky vong ADS1292R: 0x73 hoac "
                    "ADS1292: 0x53)\n",
                    id);
    }
    printAdsPinLevels();

    // Kiểm tra xem chân DRDY (GPIO 6) có đang phát xung chuyển đổi hay không.
    // Lưu ý: START=HIGH trong begin(), nên nếu chip đã boot xong → DRDY phải
    // phát xung.
    int drdyTransitions = 0;
    int lastDrdyState = digitalRead(ADS_PIN_DRDY);
    unsigned long tCheck = millis();
    while (millis() - tCheck < 100) {
      int s = digitalRead(ADS_PIN_DRDY);
      if (s != lastDrdyState) {
        drdyTransitions++;
        lastDrdyState = s;
      }
    }

    if (drdyTransitions > 5) {
      Serial.printf("  [*] DRDY DANG PHAT XUNG! (%d canh/100ms)\n",
                    drdyTransitions);
      Serial.println(
          "      => Chip DA HOAT DONG. Loi nam o duong SPI (MISO/MOSI/SCK/CS):");
      Serial.println(
          "         - Thu doi cheo MOSI (15) va MISO (16) cho nhau.");
      Serial.println("         - Kiem tra day SCK (17) va CS (7).");
    } else {
      Serial.printf(
          "  [!] DRDY KHONG CO XUNG (treo %s, 0 canh/100ms)\n",
          lastDrdyState == HIGH ? "HIGH" : "LOW");
      Serial.println(
          "      => Chip chua boot hoac chua nhan clock. Kiem tra:");
      Serial.println(
          "         1. Nguon 3.3V (AVDD + DVDD) tren module ADS");
      Serial.println(
          "         2. Chan CLKSEL tren module phai = GND/LOW de dung clock ngoai");
      Serial.println(
          "         3. Noi PWDN/RESET truc tiep vao 3.3V de loai tru reset bi keo LOW");
      Serial.println(
          "         4. Day CLK tu GPIO 3 -> chan CLK tren ADS");
    }

    Serial.println("  -> Dang thu lai sau 3 giay...\n");
    Serial.flush();
    delay(3000);
  }

  Serial.println("[ADS1292R] >> KET NOI PHAN CUNG THANH CONG! <<");

  // Thiết lập tốc độ lấy mẫu: 500 SPS (hoặc ADS_DR_1000SPS)
  ads.setSampleRate(ADS_DR_500SPS);

  // Thiết lập chế độ kiểm tra xung nếu được kích hoạt
  if (testSignalMode) {
    ads.setTestSignal(true);
    Serial.println("[*] Che do: XUNG VUONG NOI BO 1Hz (TEST SIGNAL)");
  } else {
    ads.setTestSignal(false);
    Serial.println("[*] Che do: DO DIEN CUC sEMG THUC TE (NORMAL ELECTRODE)");
  }

  // Tạo FreeRTOS Task thu thập dữ liệu sEMG trên Core 1
  xTaskCreatePinnedToCore(adsAcquisitionTask, "ADSTask", 4096, NULL, 2,
                          &adsTaskHandle, 1);

  // Kích hoạt ngắt chân DRDY sườn xuống (FALLING)
  pinMode(ADS_PIN_DRDY, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(ADS_PIN_DRDY), drdyISR, FALLING);

  // Tiêu đề CSV tương thích với record_data.py và Serial Plotter
  Serial.println("timestamp_ms,raw_ch1,raw_ch2,emg_ch1_mv,emg_ch2_mv,button");
  Serial.flush();
}

void loop() {
  // Xử lý các phím lệnh qua Serial Monitor để tương tác thời gian thực
  if (Serial.available()) {
    char cmd = Serial.read();
    if (cmd == 't' || cmd == 'T') {
      testSignalMode = !testSignalMode;
      ads.setTestSignal(testSignalMode);
      if (testSignalMode) {
        Serial.println("# [COMMAND] Da CHUYEN sang che do test xung 1Hz");
      } else {
        Serial.println("# [COMMAND] Da CHUYEN sang che do do dien cuc sEMG");
      }
    } else if (cmd == 'h' || cmd == 'H' || cmd == '?') {
      Serial.println("\n--- BANG LENH DIEU KHIEN ---");
      Serial.println(" 't' : Bat/tat xung kiem tra 1Hz noi bo");
      Serial.println(" 'h' : Hien thi huong dan nay");
      Serial.println("---------------------------\n");
    }
  }

  vTaskDelay(pdMS_TO_TICKS(100));
}
