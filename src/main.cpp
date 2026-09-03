// ESP32-S3 ADS1292R High-Precision 24-bit sEMG Acquisition Firmware
// Tương thích PlatformIO & ESP32-S3 DevKitC-1

#include "ADS1292R.h"
#include <Arduino.h>
#include <SPI.h>

// ============================================================================
// CẤU HÌNH PHẦN CỨNG CHÂN GPIO (ESP32-S3)
// ============================================================================
#define ADS_PIN_SCK 12  // SPI Clock
#define ADS_PIN_MOSI 11 // SPI MOSI (DIN trên module ADS1292R)
#define ADS_PIN_MISO 13 // SPI MISO (DOUT trên module ADS1292R)
#define ADS_PIN_CS 10   // Chip Select (Active LOW)
#define ADS_PIN_DRDY 4  // Data Ready (Ngắt phần cứng ngõ vào)
#define ADS_PIN_START 6 // START pin (hoặc nối thẳng 3.3V)
#define ADS_PIN_RESET 7 // RESET pin (hoặc nối qua tụ/trở pull-up)

#define BUTTON_PIN 5 // Nút bấm đánh dấu sự kiện

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
        int buttonState = digitalRead(BUTTON_PIN);
        int isButtonPressed = (buttonState == LOW) ? 1 : 0;

        // Xuất dòng dữ liệu chuẩn CSV tốc độ cao (921600 baud)
        // Định dạng: timestamp_ms,raw_ch1,raw_ch2,emg_ch1_mv,emg_ch2_mv,button
        Serial.printf("%lu,%ld,%ld,%.4f,%.4f,%d\n", millis(), sample.ch1_raw,
                      sample.ch2_raw, sample.ch1_mv, sample.ch2_mv,
                      isButtonPressed);
      }
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

  // Cấu hình nút bấm
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  // Thiết lập sơ đồ chân cho ADS1292R
  ADS1292R_Pins pins;
  pins.sck = ADS_PIN_SCK;
  pins.mosi = ADS_PIN_MOSI;
  pins.miso = ADS_PIN_MISO;
  pins.cs = ADS_PIN_CS;
  pins.drdy = ADS_PIN_DRDY;
  pins.start = ADS_PIN_START;
  pins.reset = ADS_PIN_RESET;

  // Khởi tạo ADS1292R với SPI tốc độ 2MHz
  if (!ads.begin(pins, 2000000)) {
    Serial.println("[!] LOI: Khoi tao ADS1292R that bai! Dung chuong trinh.");
    while (1) {
      delay(1000);
    }
  }

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

  // Tạo FreeRTOS Task thu thập dữ liệu sEMG trên Core 1 (độ ưu tiên cao)
  xTaskCreatePinnedToCore(adsAcquisitionTask, "ADSTask", 4096, NULL,
                          configMAX_PRIORITIES - 1, &adsTaskHandle, 1);

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
