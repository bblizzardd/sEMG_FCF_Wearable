#include <Arduino.h>
#include <SPI.h>
#include <math.h>

#include "SampleAcquisition.h"
#include "protocentralAds1292r.h"

// ============================================================================
// CẤU HÌNH PHẦN CỨNG
// ============================================================================
constexpr int PIN_ADS_CS = 10;   // CS active LOW.
constexpr int PIN_ADS_PWDN = 9;  // PWDN/reset.
constexpr int PIN_ADS_SCK = 12;  // Clock SPI.
constexpr int PIN_ADS_MOSI = 11; // ESP32 -> ADS.
constexpr int PIN_ADS_MISO = 13; // ADS -> ESP32.
constexpr int PIN_ADS_START = 8; // HIGH: bắt đầu chuyển đổi.
constexpr int PIN_ADS_DRDY = 4;  // Cạnh xuống: mẫu mới sẵn sàng.

// ============================================================================
// CẤU HÌNH BỘ LỌC: sửa các giá trị ở đây rồi build/nạp lại.
// fc, f0, DC_filter_50 và DC_filter_100 có đơn vị Hz; fs có đơn vị mẫu/giây.
// Khi đổi fs, đối chiếu baud/SPS mục tiêu của công cụ Python đang sử dụng;
// các hệ số EMA/adaptive phía dưới vẫn tính theo mỗi mẫu nhận được.
// ============================================================================
constexpr float fc = 450.0f;    // Tần số cắt low-pass.
constexpr float fs = 2000.0f;   // Tốc độ ADC và tần số lấy mẫu dùng cho DSP.
constexpr float f0 = 20.0f;     // Tần số cắt high-pass.
constexpr float DC_filter_50 = 50.0f;   // Tần số notch thứ nhất, mặc định điện lưới 50 Hz.
constexpr float DC_filter_100 = 100.0f; // Tần số notch thứ hai, mặc định hài 100 Hz.
// Hai tên DC_filter là tên cấu hình notch; thành phần DC (0 Hz) do high-pass giảm.
constexpr float NOTCH_RADIUS = 0.98f; // Gần 1: notch hẹp hơn, đuôi đáp ứng dài hơn.

// ADS1292R hỗ trợ các tốc độ rời rạc với clock mặc định của driver.
static_assert(fs == 125.0f || fs == 250.0f || fs == 500.0f || fs == 1000.0f || fs == 2000.0f || fs == 4000.0f || fs == 8000.0f,
  "fs must be a supported ADS1292R sample rate");
static_assert(f0 > 0.0f && f0 < fc && fc < fs / 2.0f,
              "Require 0 < high-pass cutoff < low-pass cutoff < fs/2");
static_assert(DC_filter_50 > 0.0f && DC_filter_50 < fs / 2.0f &&
                  DC_filter_100 > 0.0f && DC_filter_100 < fs / 2.0f,
              "Both notch frequencies must be between 0 and fs/2");
static_assert(NOTCH_RADIUS > 0.0f && NOTCH_RADIUS < 1.0f,
              "Notch pole radius must be between 0 and 1");

constexpr uint8_t ADC_DATA_RATE =
    fs == 125.0f ? 0x00 : fs == 250.0f ? 0x01 : fs == 500.0f ? 0x02 :
    fs == 1000.0f ? 0x03 : fs == 2000.0f ? 0x04 : fs == 4000.0f ? 0x05 : 0x06;

SPIClass adsSpiBus(FSPI);
unsigned long lastSamplePrint = 0;
uint32_t sampleCounter = 0;

// ============================================================================
// BỘ LỌC BIQUAD: hệ số được tính một lần; mỗi tầng có lịch sử mẫu riêng.
// ============================================================================
enum class PassType { HighPass, LowPass };

struct Biquad {
  float b0, b1, b2, a1, a2;
  float x1 = 0.0f, x2 = 0.0f;
  float y1 = 0.0f, y2 = 0.0f;

  // Lưu 5 hệ số đã chuẩn hóa a0=1; lịch sử đầu vào/đầu ra khởi tạo bằng 0.
  Biquad(float b0Value, float b1Value, float b2Value,
         float a1Value, float a2Value)
      : b0(b0Value), b1(b1Value), b2(b2Value),
        a1(a1Value), a2(a2Value) {}

  // Lọc một mẫu bằng hồi tiếp bậc 2 và cập nhật lịch sử trễ 1/2 mẫu.
  float process(float input) {
    const float output = b0 * input + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
    x2 = x1;
    x1 = input;
    y2 = y1;
    y1 = output;
    return output;
  }
};

/**
 * Tính hệ số Butterworth bậc 2 cho high-pass hoặc low-pass từ cutoff và fs.
 * Q=1/sqrt(2); w0=2*pi*cutoff/fs; alpha=sin(w0)/(2*Q).
 * Chia các hệ số cho D=1+alpha để chuẩn hóa a0=1.
 * Tại cutoff, biên độ khoảng 0.707 (-3 dB); đáp ứng không cắt đứt tại đó.
 * Công thức: https://www.w3.org/TR/audio-eq-cookbook/
 */
Biquad makeButterworth(float cutoff, PassType type) {
  const float Q = 1.0f / sqrtf(2.0f);
  const float w0 = 2.0f * PI * cutoff / fs;
  const float cosine = cosf(w0);
  const float alpha = sinf(w0) / (2.0f * Q);
  const float D = 1.0f + alpha;
  const bool highPass = type == PassType::HighPass;
  const float b0 = (highPass ? 1.0f + cosine : 1.0f - cosine) / (2.0f * D);
  const float b1 = (highPass ? -2.0f : 2.0f) * b0;
  return Biquad(b0, b1, b0, -2.0f * cosine / D, (1.0f - alpha) / D);
}

/**
 * Tính hệ số notch từ tần số chặn, fs và bán kính cực r=NOTCH_RADIUS.
 * w0=2*pi*frequency/fs; K=(1-2*r*cos(w0)+r^2)/(2-2*cos(w0)).
 * b0=b2=K; b1=-2*K*cos(w0); a1=-2*r*cos(w0); a2=r^2.
 * K chuẩn hóa gain tại DC về 1. Notch cũng giảm EMG thật quanh tần số chặn.
 */
Biquad makeNotch(float frequency) {
  const float w0 = 2.0f * PI * frequency / fs;
  const float cosine = cosf(w0);
  const float r = NOTCH_RADIUS;
  const float K = (1.0f - 2.0f * r * cosine + r * r) / (2.0f - 2.0f * cosine);
  return Biquad(K, -2.0f * K * cosine, K, -2.0f * r * cosine, r * r);
}

// Giảm DC và thành phần chậm, dùng tần số cắt f0.
float filterHighPass(float input) {
  static Biquad filter = makeButterworth(f0, PassType::HighPass);
  return filter.process(input);
}

// Giảm nhiễu tại DC_filter_50, mặc định 50 Hz; hệ số tính một lần.
float filterNotchFirst(float input) {
  static Biquad filter = makeNotch(DC_filter_50);
  return filter.process(input);
}

// Giảm nhiễu tại DC_filter_100, mặc định 100 Hz; lịch sử riêng với notch trước.
float filterNotchSecond(float input) {
  static Biquad filter = makeNotch(DC_filter_100);
  return filter.process(input);
}

// Giảm thành phần cao tần, dùng tần số cắt fc.
float filterLowPass(float input) {
  static Biquad filter = makeButterworth(fc, PassType::LowPass);
  return filter.process(input);
}

/**
 * Ghép thông báo theo định dạng printf và gửi Serial.
 * Bộ đệm 256 byte chứa tối đa 255 byte nội dung + NUL; chuỗi dài hơn bị cắt.
 */
void printMsg(const char *format, ...) {
  char buffer[256];
  va_list args;
  va_start(args, format);
  vsnprintf(buffer, sizeof(buffer), format, args);
  va_end(args);
  Serial.print(buffer);
}

/**
 * Ghi tốc độ ADC theo fs khi driver đã ở SDATAC và START LOW sau init.
 * Sau đó bật RDATAC và START; bên gọi phải khóa SPI nếu task thu đã chạy.
 */
void startAdcConversions() {
  ads1292r::ads1292RegWrite(ADS1292_REG_CONFIG1, ADC_DATA_RATE, PIN_ADS_CS);
  delay(10);
  ads1292r::ads1292StartReadDataContinuous(PIN_ADS_CS);
  delay(10);
  digitalWrite(PIN_ADS_START, HIGH);
  delay(10);
}

// Khởi tạo Serial/GPIO/SPI, cấu hình ADS và bắt đầu tác vụ thu mẫu.
void setup() {
  Serial.setTxBufferSize(8192);
  Serial.begin(2000000);
  delay(1000);

  pinMode(PIN_ADS_CS, OUTPUT);
  digitalWrite(PIN_ADS_CS, HIGH);
  pinMode(PIN_ADS_DRDY, INPUT_PULLUP);
  pinMode(PIN_ADS_START, OUTPUT);
  digitalWrite(PIN_ADS_START, LOW);

  // -1: driver tự điều khiển CS, SPI.begin không dùng SS tự động.
  adsSpiBus.begin(PIN_ADS_SCK, PIN_ADS_MISO, PIN_ADS_MOSI, -1);
  ads1292r::ads1292Init(adsSpiBus, PIN_ADS_CS, PIN_ADS_PWDN, PIN_ADS_START);
  startAdcConversions();

  if (!beginAcquisition(PIN_ADS_DRDY, PIN_ADS_CS)) {
    while (true) delay(1000);
  }
}

// Tham số khởi tạo để tính mức kích hoạt tương đối; đơn vị biên độ là count.
// 10/120/5 là giá trị khởi đầu được chọn trong code, không phải số đo đã xác nhận.
float emgEnvelope = 0.0f; // Envelope chưa có mẫu, khởi tạo bằng 0.
float baselineNoise = 10.0f; // Mức nền khởi đầu 10 count; sau đó được cập nhật.
float mvcPeak = 120.0f; // Đỉnh khởi đầu 120 count; tên MVC nhưng chưa đo MVC chuẩn.
float sensitivityMultiplier = 1.0f; // x1: độ nhạy mặc định, không đổi gain ADC.
float noiseThreshold = 5.0f; // Gate khởi đầu 5 count, dùng khi tính phần trăm UI.

bool filterEnabled = true; // Mặc định bật chuỗi 4 bộ lọc.
float dcOffset = 0.0f; // Ước lượng DC khởi đầu bằng 0, dùng khi DSP tắt.

/**
 * Công dụng: lấy envelope hiện tại làm nền, đặt lại đỉnh/gate/độ nhạy UI.
 * Nên gọi lúc cơ nghỉ nếu muốn lấy nền nghỉ; hàm không đo một đoạn nghỉ riêng.
 * Các ngưỡng ở đây là tham số hiển thị được chọn trong code, không phải hệ số IIR.
 * Hàm không xóa lịch sử x/y của các bộ lọc, envelope, dcOffset, sequence hay
 * cờ baselineInitialized trong loop(); vì vậy đây là reset tham số cân chỉnh.
 */
void resetCalibration() {
  baselineNoise = emgEnvelope;
  if (baselineNoise < 1.0f) baselineNoise = 1.0f; // Nền tối thiểu 1 count.
  float defaultSpan = filterEnabled ? 80.0f : 400.0f; // Dải ban đầu: DSP 80, tắt DSP 400 count.
  mvcPeak = baselineNoise + defaultSpan;
  noiseThreshold = (baselineNoise * 0.25f < 2.5f) ? 2.5f : (baselineNoise * 0.25f); // Gate = 25% nền, tối thiểu 2.5 count.
  if (noiseThreshold > 20.0f) noiseThreshold = 20.0f; // Gate tối đa 20 count.
  sensitivityMultiplier = 1.0f; // Trở về độ nhạy x1.
  printMsg("\n>>> [CÂN CHỈNH LẠI] Mức nghỉ = %.0f | Đỉnh = %.0f | Ngưỡng ồn = %.1f | Độ nhạy = x1.00 <<<\n\n",
           baselineNoise, mvcPeak, noiseThreshold);
}

/**
 * Công dụng: nhận lệnh Serial; lấy mẫu từ queue; xử lý kênh 2; gửi từng mẫu $D;
 * tính envelope/nền/đỉnh và phần trăm; in UI và thống kê SPS.
 * Lệnh: c cân chỉnh; r init lại ADS; f bật/tắt DSP;
 * +/- đổi độ nhạy hiển thị; s/? xem trạng thái. r cần khóa SPI và ngắt quãng thu.
 * fs là tốc độ mẫu mục tiêu; thống kê SPS báo tốc độ thực tế nhận được.
 * Các hệ số làm mượt/adaptive được áp dụng theo mỗi mẫu NHẬN ĐƯỢC; thời gian
 * tương đương bên dưới chỉ đúng gần đúng khi mẫu đều 2000 Hz và điều kiện cập nhật bật.
 * Phần trăm là chỉ số tương đối, phụ thuộc nền/đỉnh/gate/độ nhạy tự thích ứng.
 */
void loop() {
  // Lắng nghe lệnh từ bàn phím qua Serial Monitor hoặc Web Visualizer
  if (Serial.available()) {
    char cmd = Serial.read();
    if (cmd == 'c' || cmd == 'C') {
      resetCalibration();
    } else if (cmd == 'r' || cmd == 'R') {
      lockAcquisitionSpi();
      ads1292r::ads1292Init(adsSpiBus, PIN_ADS_CS, PIN_ADS_PWDN, PIN_ADS_START);
      startAdcConversions();
      unlockAcquisitionSpi();
      resetCalibration();
    } else if (cmd == 'f' || cmd == 'F') {
      filterEnabled = !filterEnabled;
      resetCalibration();
      printMsg("\n[DSP FILTER] Đã chuyển sang: %s\n\n",
               filterEnabled ? "BẬT (Khử nhiễu 4 tầng)" : "TẮT (Trừ DC)");
    } else if (cmd == '+' || cmd == '=') {
      sensitivityMultiplier *= 1.40f; // Nhân 1.40: tăng 40% mỗi lần bấm.
      if (sensitivityMultiplier > 50.0f) sensitivityMultiplier = 50.0f; // Trần độ nhạy x50.
      printMsg("\n[ĐỘ NHẠY] Tăng nhạy lên x%.2f (Dễ đạt 100%% hơn)\n\n", sensitivityMultiplier);
    } else if (cmd == '-' || cmd == '_') {
      sensitivityMultiplier *= 0.70f; // Nhân 0.70: giảm 30%, không đảo đúng thao tác +.
      if (sensitivityMultiplier < 0.1f) sensitivityMultiplier = 0.1f; // Sàn độ nhạy x0.1.
      printMsg("\n[ĐỘ NHẠY] Giảm nhạy xuống x%.2f\n\n", sensitivityMultiplier);
    } else if (cmd == 's' || cmd == '?') {
      float effG = noiseThreshold / sensitivityMultiplier;
      if (effG < 0.8f) effG = 0.8f; // Gate hiệu dụng tối thiểu 0.8 count, giống nhánh UI.
      printMsg("\n=======================================================\n");
      printMsg(">>> THÔNG TIN ĐỘ NHẠY & CÂN CHỈNH HIỆN TẠI <<<\n");
      printMsg("   - Chế độ Giảm nhiễu (DSP)    : %s\n", filterEnabled ? "BẬT" : "TẮT (RAW)");
      printMsg("   - Hệ số độ nhạy (Sensitivity): x%.2f\n", sensitivityMultiplier);
      printMsg("   - Mức nghỉ (Baseline)       : %.1f\n", baselineNoise);
      printMsg("   - Ngưỡng ồn hiệu dụng (Gate) : %.1f\n", effG);
      printMsg("   - Mức gồng đỉnh (Peak)      : %.1f\n", mvcPeak);
      printMsg("   - Dải lực hiệu dụng (Span)   : %.1f\n", (mvcPeak - (baselineNoise + effG)) / sensitivityMultiplier);
      printMsg("=======================================================\n\n");
    }
  }

  // Lấy một mẫu đã được task thu đọc từ ADC và đưa vào queue.
  AcquiredSample sample;
  if (receiveSample(sample)) {
    sampleCounter = sample.sequence;

    // Hai kênh ADC có dấu 24 bit; lưu trong int32_t để giữ raw cho dataset.
    int32_t ch1_raw24 = sample.ch1;
    int32_t ch2_raw24 = sample.ch2;
    int32_t ch2_16 = (int32_t)(ch2_raw24 >> 8); // Bỏ 8 bit thấp, thu nhỏ thang khoảng 256 lần; vẫn chứa trong 32 bit.

    // Kênh 2 cố định cho DSP; kênh 1 vẫn được gửi ra CSV.
    int32_t emgRaw = ch2_16;

    float emgSignal = 0.0f; // Khởi tạo kết quả; mỗi nhánh phía dưới đều gán lại.
    if (filterEnabled) {
      // HP(f0) -> notch(DC_filter_50) -> notch(DC_filter_100) -> LP(fc).
      const float highPassed = filterHighPass((float)emgRaw);
      const float lineRemoved = filterNotchFirst(highPassed);
      const float harmonicRemoved = filterNotchSecond(lineRemoved);
      emgSignal = filterLowPass(harmonicRemoved);
    } else {
      // Khi DSP tắt vẫn trừ DC; chỉ các cột raw24/raw16 giữ dữ liệu trước bước này.
      if (sampleCounter < 100) { // Sequence <100: lấy raw làm DC; khoảng 50 ms đầu nếu đủ ngắt/mẫu.
        dcOffset = (float)emgRaw;
      } else {
        dcOffset = 0.999f * dcOffset + 0.001f * (float)emgRaw; // 99.9% DC cũ + 0.1% mẫu mới; tau khoảng 0.50 s.
      }
      emgSignal = (float)emgRaw - dcOffset;
    }

    uint32_t sampleTimeUs = sample.timestampUs;

    // Gửi mỗi mẫu đã nhận; timestamp là lúc phần mềm phục vụ ISR DRDY, có độ trễ ngắt.
    // Định dạng: $D,sampleIndex,timestampUs,ch1_raw24,ch2_raw24,ch2_raw16,filtered16,leadOff
    // %u/%lu/%ld là định dạng số nguyên. Cast emgSignal sang long bỏ phần lẻ.
    // leadOff ? 1 : 0 mã hóa cờ thành số; không khẳng định tiếp xúc tốt khi false.
    Serial.printf("$D,%u,%lu,%ld,%ld,%ld,%ld,%d\n",
                  sampleCounter, (unsigned long)sampleTimeUs, (long)ch1_raw24, (long)ch2_raw24, (long)emgRaw, (long)emgSignal, sample.leadOff ? 1 : 0);

    // Envelope: lấy trị tuyệt đối rồi EMA. Với y=a*y_cũ+(1-a)*x,
    // tau=-1/(Fs*ln(a)); a=0.993356 tại 2000 Hz cho tau khoảng 75 ms.
    float emgRectified = fabsf(emgSignal);
    emgEnvelope = 0.993356f * emgEnvelope + 0.006644f * emgRectified; // 99.3356% cũ + 0.6644% mới; tổng trọng số 1.

    // Khởi tạo nền một lần khi sequence >400 (khoảng 0.2 s tính từ cạnh đầu).
    // Sequence đếm ngắt, không phải số mẫu main nhận; mất mẫu có thể làm ít hơn
    // 400 mẫu được xử lý. Mốc này là thời gian chờ được chọn, không đo độ ổn định lọc.
    static bool baselineInitialized = false;
    if (!baselineInitialized && sampleCounter > 400) {
      baselineNoise = emgEnvelope;
      if (baselineNoise < 1.0f) baselineNoise = 1.0f; // Nền tối thiểu 1 count.
      float defaultSpan = filterEnabled ? 80.0f : 400.0f; // Đỉnh = nền + dải ban đầu 80/400 count.
      mvcPeak = baselineNoise + defaultSpan;
      noiseThreshold = (baselineNoise * 0.25f < 2.5f) ? 2.5f : (baselineNoise * 0.25f); // Gate = 25% nền, sàn 2.5.
      if (noiseThreshold > 20.0f) noiseThreshold = 20.0f; // Trần gate 20 count.
      baselineInitialized = true;
    }

    // Bám nền/gate/đỉnh để đổi dải hiển thị; các bước này không sửa raw trong $D.
    if (baselineInitialized) {
      if (emgEnvelope < baselineNoise) {
        // Hạ mức nghỉ nhanh hơn để dập tắt nhiễu sau khi gồng
        baselineNoise = 0.85f * baselineNoise + 0.15f * emgEnvelope; // 85% nền cũ + 15% envelope: hạ nhanh, tau khoảng 3.08 ms.
      } else if (emgEnvelope < baselineNoise + noiseThreshold * 1.5f) { // Chỉ tăng nền trong vùng dưới nền + 1.5 lần gate.
        // Chỉ bám tăng nhẹ mức nghỉ khi cơ thực sự đang thả lỏng
        baselineNoise = baselineNoise + 0.00005f * (emgEnvelope - baselineNoise); // Bám 0.005% sai lệch mỗi mẫu; tau khoảng 10 s.
      }

      // Giữ noiseThreshold tự thích ứng nhẹ theo mức nghỉ
      float targetGate = baselineNoise * 0.25f; // Gate mục tiêu = 25% mức nền.
      if (targetGate < 2.5f) targetGate = 2.5f; // Sàn gate mục tiêu 2.5 count.
      if (targetGate > 20.0f) targetGate = 20.0f; // Trần gate mục tiêu 20 count.
      noiseThreshold = 0.999f * noiseThreshold + 0.001f * targetGate; // Bám 0.1% gate mục tiêu/mẫu; tau khoảng 0.50 s.

      // Tự động bám mức gồng tối đa (Dynamic Peak Tracking)
      if (emgEnvelope > mvcPeak) {
        mvcPeak = 0.90f * mvcPeak + 0.10f * emgEnvelope; // 90% đỉnh cũ + 10% envelope; tăng nhanh, tau khoảng 4.75 ms.
      } else {
        // Thu hẹp trần từ từ nếu lâu không gồng
        float minSpan = filterEnabled ? 20.0f : 80.0f; // Chỉ cho đỉnh giảm khi còn cao hơn nền + 20/80 count.
        if (mvcPeak > baselineNoise + minSpan) {
          mvcPeak *= 0.99998f; // Giảm 0.002%/mẫu; tau khoảng 25 s khi nhánh giảm liên tục.
        }
      }
    }

    // UI: ít nhất 20 ms giữa hai lần in, tối đa khoảng 50 lần/s; $D vẫn gửi từng mẫu.
    if (millis() - lastSamplePrint >= 20) {
      lastSamplePrint = millis();

      // Ngưỡng chết chống rung sàn (Noise Gate) thích ứng theo hệ số độ nhạy
      // Tăng nhạy làm gate nhỏ và dải phần trăm hẹp hơn; cũng dễ hiện nhiễu hơn.
      float effectiveGate = noiseThreshold / sensitivityMultiplier;
      if (effectiveGate < 0.8f) effectiveGate = 0.8f; // Sàn gate hiệu dụng 0.8 count; ngưỡng UI, không lọc raw.

      float effectiveEnvelope = emgEnvelope - (baselineNoise + effectiveGate);

      int percent = 0; // Mặc định 0% khi envelope chưa vượt nền + gate.
      if (effectiveEnvelope > 0.0f) {
        float minSpan = filterEnabled ? 15.0f : 50.0f; // Dải chuẩn hóa tối thiểu 15/50 count, tránh mẫu số quá nhỏ.
        float rawSpan = mvcPeak - (baselineNoise + effectiveGate);
        if (rawSpan < minSpan) rawSpan = minSpan;
        float span = rawSpan / sensitivityMultiplier;

        float rawPercent = (effectiveEnvelope / span) * 100.0f; // Nhân 100 đổi tỷ lệ thành phần trăm.
        percent = (int)rawPercent; // Bỏ phần thập phân để in số nguyên.
        if (percent > 100) percent = 100; // Chặn trần hiển thị 100%; không phải lực Newton.
      }

      // Vẽ thanh hiển thị lực gồm 20 vạch
      int barLength = percent / 5; // Mỗi vạch = 5%; chia nguyên cho kết quả 0..20.
      char bar[21]; // 20 ký tự hiển thị + 1 byte kết thúc chuỗi.
      for (int i = 0; i < 20; i++) {
        bar[i] = (i < barLength) ? '=' : ' ';
      }
      bar[20] = '\0'; // Chỉ số 20 là byte thứ 21; NUL kết thúc chuỗi C.

      const char *trangThai = "THA LONG";
      // Ngưỡng nhãn được chọn cho UI: [0,8) nghỉ; [8,25) nhẹ; [25,60) vừa;
      // [60,100] mạnh. Đây là nhóm phần trăm tương đối của thuật toán hiện tại.
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

  // Thống kê độc lập: mỗi >=1000 ms (1 s), dùng chênh lệch bộ đếm để tính SPS.
  static uint32_t statsTime = millis();
  static AcquisitionStats previousStats = acquisitionStats();
  const uint32_t nowMs = millis();
  if (nowMs - statsTime >= 1000) {
    const AcquisitionStats current = acquisitionStats();
    const float scale = 1000.0f / (nowMs - statsTime); // 1000 ms/s: đổi số mẫu trong khoảng đo thành mẫu/s.
    printMsg("[SPS] DRDY=%.1f READ=%.1f ADC_MISSED=%lu QUEUE_DROP=%lu\n",
             (current.edges - previousStats.edges) * scale,
             (current.captured - previousStats.captured) * scale,
             (unsigned long)current.missed, (unsigned long)current.queueDrops);
    previousStats = current;
    statsTime = nowMs;
  }

}

