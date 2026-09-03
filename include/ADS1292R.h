#ifndef ADS1292R_H
#define ADS1292R_H

#include <Arduino.h>
#include <SPI.h>

// ============================================================================
// ADS1292R REGISTER MAP
// ============================================================================
#define ADS1292R_REG_ID          0x00
#define ADS1292R_REG_CONFIG1     0x01
#define ADS1292R_REG_CONFIG2     0x02
#define ADS1292R_REG_LOFF        0x03
#define ADS1292R_REG_CH1SET      0x04
#define ADS1292R_REG_CH2SET      0x05
#define ADS1292R_REG_RLD_SENS    0x06
#define ADS1292R_REG_LOFF_SENS   0x07
#define ADS1292R_REG_LOFF_STAT   0x08
#define ADS1292R_REG_RESP1       0x09
#define ADS1292R_REG_RESP2       0x0A

// ============================================================================
// ADS1292R SPI COMMAND OPCODES
// ============================================================================
#define ADS1292R_CMD_WAKEUP      0x02
#define ADS1292R_CMD_STANDBY     0x04
#define ADS1292R_CMD_RESET       0x06
#define ADS1292R_CMD_START       0x08
#define ADS1292R_CMD_STOP        0x0A
#define ADS1292R_CMD_OFFSETCAL   0x1A
#define ADS1292R_CMD_RDATAC      0x10
#define ADS1292R_CMD_SDATAC      0x11
#define ADS1292R_CMD_RDATA       0x12
#define ADS1292R_CMD_RREG        0x20
#define ADS1292R_CMD_WREG        0x40

// ============================================================================
// CONFIGURATION ENUMS
// ============================================================================
enum ADS1292R_Rate {
    ADS_DR_125SPS  = 0x00,
    ADS_DR_250SPS  = 0x01,
    ADS_DR_500SPS  = 0x02,  // Default sEMG recommended
    ADS_DR_1000SPS = 0x03,  // High bandwidth sEMG (up to 450Hz)
    ADS_DR_2000SPS = 0x04,
    ADS_DR_4000SPS = 0x05,
    ADS_DR_8000SPS = 0x06
};

enum ADS1292R_Gain {
    ADS_GAIN_6X  = 0x00,    // 000: 6 (Default for ECG/sEMG)
    ADS_GAIN_1X  = 0x10,    // 001: 1
    ADS_GAIN_2X  = 0x20,    // 010: 2
    ADS_GAIN_3X  = 0x30,    // 011: 3
    ADS_GAIN_4X  = 0x40,    // 100: 4
    ADS_GAIN_8X  = 0x50,    // 101: 8
    ADS_GAIN_12X = 0x60     // 110: 12
};

enum ADS1292R_InputType {
    ADS_INPUT_NORMAL      = 0x00, // Điện cực đo vi sai thông thường
    ADS_INPUT_SHORTED     = 0x01, // Chập ngõ vào (đo nhiễu offset)
    ADS_INPUT_RLD         = 0x02, // Đo RLD
    ADS_INPUT_MVDD        = 0x03, // Đo nguồn cung cấp
    ADS_INPUT_TEMP        = 0x04, // Cảm biến nhiệt độ tích hợp
    ADS_INPUT_TEST_SIGNAL = 0x05  // Xung kiểm tra chuẩn 1Hz (±1mV)
};

// ============================================================================
// HARDWARE PIN DEFINITIONS
// ============================================================================
struct ADS1292R_Pins {
    int8_t sck;     // SPI Clock
    int8_t mosi;    // SPI Master Out Slave In (DIN trên ADS)
    int8_t miso;    // SPI Master In Slave Out (DOUT trên ADS)
    int8_t cs;      // Chip Select (Active LOW)
    int8_t drdy;    // Data Ready (Active LOW ngắt ngõ vào)
    int8_t start;   // START pin (-1 nếu nối thẳng 3.3V)
    int8_t reset;   // RESET pin (-1 nếu nối qua tụ/trở pull-up)
};

// ============================================================================
// SAMPLE DATA STRUCTURE
// ============================================================================
struct ADS1292R_Sample {
    uint32_t status;        // 24-bit Status word (header 0xC0xxxx)
    int32_t  ch1_raw;       // 24-bit bù 2 mở rộng sang 32-bit có dấu
    int32_t  ch2_raw;       // 24-bit bù 2 mở rộng sang 32-bit có dấu
    float    ch1_mv;        // Điện áp quy đổi milivolt (mV)
    float    ch2_mv;        // Điện áp quy đổi milivolt (mV)
    bool     valid;         // Trạng thái gói dữ liệu hợp lệ (Sync header = 0xC0)
};

// ============================================================================
// DRIVER CLASS
// ============================================================================
class ADS1292R {
public:
    ADS1292R();

    // Khởi tạo SPI và thiết lập trạng thái ban đầu cho chip
    bool begin(const ADS1292R_Pins& pins, uint32_t spiSpeed = 2000000);

    // Reset phần cứng và lệnh mềm
    void hardwareReset();
    void sendCommand(uint8_t cmd);

    // Đọc/Ghi thanh ghi
    uint8_t readRegister(uint8_t reg);
    void writeRegister(uint8_t reg, uint8_t value);
    void readRegisters(uint8_t startReg, uint8_t count, uint8_t* buffer);
    void writeRegisters(uint8_t startReg, uint8_t count, const uint8_t* data);

    // Cấu hình hoạt động
    uint8_t getDeviceID();
    void setSampleRate(ADS1292R_Rate rate);
    void configChannel(uint8_t channel, ADS1292R_Gain gain, ADS1292R_InputType inputType);
    void setTestSignal(bool enable);
    
    // Điều khiển chuyển đổi
    void start();
    void stop();

    // Đọc dữ liệu mẫu (9 bytes: 3 status + 3 ch1 + 3 ch2)
    bool readSample(ADS1292R_Sample& sample);
    
    // Kiểm tra chân DRDY
    bool isDataReady() const;

    // Helper tính toán hệ số Gain hiện tại để đổi mV
    float getGainMultiplier(ADS1292R_Gain gain) const;

private:
    ADS1292R_Pins _pins;
    uint32_t _spiSpeed;
    SPISettings _spiSettings;
    SPIClass* _spi;
    bool _isContinuousMode;

    ADS1292R_Gain _ch1Gain;
    ADS1292R_Gain _ch2Gain;

    float _ch1Scale_mV;
    float _ch2Scale_mV;

    void updateScales();
};

#endif // ADS1292R_H
