#include "ADS1292R.h"

ADS1292R::ADS1292R()
    : _spiSpeed(2000000),
      _spiSettings(2000000, MSBFIRST, SPI_MODE1),
      _spi(&SPI),
      _isContinuousMode(false),
      _ch1Gain(ADS_GAIN_6X),
      _ch2Gain(ADS_GAIN_6X),
      _ch1Scale_mV(0.0f),
      _ch2Scale_mV(0.0f) {
    _pins = {-1, -1, -1, -1, -1, -1, -1};
    updateScales();
}

float ADS1292R::getGainMultiplier(ADS1292R_Gain gain) const {
    switch (gain) {
        case ADS_GAIN_1X:  return 1.0f;
        case ADS_GAIN_2X:  return 2.0f;
        case ADS_GAIN_3X:  return 3.0f;
        case ADS_GAIN_4X:  return 4.0f;
        case ADS_GAIN_6X:  return 6.0f;
        case ADS_GAIN_8X:  return 8.0f;
        case ADS_GAIN_12X: return 12.0f;
        default:           return 6.0f;
    }
}

void ADS1292R::updateScales() {
    // VREF nội bộ = 2.42V = 2420.0 mV
    // Dải đo cực đại: Full Scale (2^23 - 1) = 8388607
    const float VREF_MV = 2420.0f;
    const float FULL_SCALE = 8388607.0f;

    float gain1 = getGainMultiplier(_ch1Gain);
    float gain2 = getGainMultiplier(_ch2Gain);

    _ch1Scale_mV = VREF_MV / (FULL_SCALE * gain1);
    _ch2Scale_mV = VREF_MV / (FULL_SCALE * gain2);
}

bool ADS1292R::begin(const ADS1292R_Pins& pins, uint32_t spiSpeed) {
    _pins = pins;
    _spiSpeed = spiSpeed;
    _spiSettings = SPISettings(_spiSpeed, MSBFIRST, SPI_MODE1);

    // 1. Cấu hình chân GPIO
    if (_pins.cs >= 0) {
        pinMode(_pins.cs, OUTPUT);
        digitalWrite(_pins.cs, HIGH);
    }
    if (_pins.drdy >= 0) {
        pinMode(_pins.drdy, INPUT_PULLUP);
    }
    if (_pins.start >= 0) {
        pinMode(_pins.start, OUTPUT);
        digitalWrite(_pins.start, LOW);
    }
    if (_pins.reset >= 0) {
        pinMode(_pins.reset, OUTPUT);
        digitalWrite(_pins.reset, HIGH);
    }

    // 2. Khởi tạo SPI bus trên ESP32-S3 với các chân được chọn
    _spi->begin(_pins.sck, _pins.miso, _pins.mosi, -1);

    // 3. Chu trình Reset phần cứng
    hardwareReset();

    // 4. Dừng chế độ đọc liên tục (RDATAC) để có thể ghi/đọc thanh ghi
    sendCommand(ADS1292R_CMD_SDATAC);
    delayMicroseconds(100);
    _isContinuousMode = false;

    // 5. Đọc Device ID để kiểm tra kết nối phần cứng
    uint8_t devId = getDeviceID();
    Serial.printf("[ADS1292R] Chip ID read: 0x%02X\n", devId);

    // ID hợp lệ: ADS1292R = 0x73, ADS1292 = 0x53 (Upper 5 bits = 0b01110)
    if (devId == 0x00 || devId == 0xFF) {
        Serial.println("[ADS1292R] ERROR: Khong tim thay chip! Kiem tra lai day SPI & nguon 3.3V.");
        return false;
    }

    // 6. Cấu hình các thanh ghi mặc định tối ưu cho sEMG:
    // CONFIG1: 500 SPS (0x02) hoặc 1000 SPS (0x03)
    writeRegister(ADS1292R_REG_CONFIG1, ADS_DR_500SPS);
    delayMicroseconds(50);

    // CONFIG2: Bật nguồn điện áp tham chiếu nội 2.42V (PDB_REFBUF = 1) -> 0b10100000 = 0xA0
    writeRegister(ADS1292R_REG_CONFIG2, 0xA0);
    delayMicroseconds(50);

    // RLD_SENS: Bật RLD buffer (PDB_RLD = 1) và lấy mẫu common mode kênh 1, kênh 2 -> 0x2C
    writeRegister(ADS1292R_REG_RLD_SENS, 0x2C);
    delayMicroseconds(50);

    // RESP2: Bật điện áp tham chiếu RLD nội (AVDD+AVSS)/2 = 1.65V (RLDREF_INT = 1) -> 0x87
    writeRegister(ADS1292R_REG_RESP2, 0x87);
    delayMicroseconds(50);

    // LOFF: Mặc định
    writeRegister(ADS1292R_REG_LOFF, 0x10);
    delayMicroseconds(50);

    // RESP1: Tắt demodulation hô hấp (chỉ dùng cho EMG thông thường)
    writeRegister(ADS1292R_REG_RESP1, 0x02);
    delayMicroseconds(50);

    // Cấu hình Kênh 1 và Kênh 2: Gain 6x, đo vi sai điện cực bình thường
    configChannel(1, ADS_GAIN_6X, ADS_INPUT_NORMAL);
    configChannel(2, ADS_GAIN_6X, ADS_INPUT_NORMAL);

    // 7. Bắt đầu chuyển đổi và chuyển sang chế độ RDATAC
    start();
    sendCommand(ADS1292R_CMD_RDATAC);
    _isContinuousMode = true;
    delayMicroseconds(50);

    Serial.println("[ADS1292R] Khoi tao thanh cong! Da vao che do RDATAC.");
    return true;
}

void ADS1292R::hardwareReset() {
    if (_pins.reset >= 0) {
        digitalWrite(_pins.reset, HIGH);
        delay(20);
        digitalWrite(_pins.reset, LOW);
        delay(2); // Giữ mức thấp ít nhất 2*tCLK (~4us)
        digitalWrite(_pins.reset, HIGH);
        delay(100); // Chờ 18*tCLK (~35us) sau reset
    } else {
        sendCommand(ADS1292R_CMD_RESET);
        delay(100);
    }
}

void ADS1292R::sendCommand(uint8_t cmd) {
    _spi->beginTransaction(_spiSettings);
    if (_pins.cs >= 0) digitalWrite(_pins.cs, LOW);

    _spi->transfer(cmd);
    delayMicroseconds(10); // Đảm bảo timing tSDECODE

    if (_pins.cs >= 0) digitalWrite(_pins.cs, HIGH);
    _spi->endTransaction();

    delayMicroseconds(10);
}

uint8_t ADS1292R::readRegister(uint8_t reg) {
    uint8_t val = 0;
    readRegisters(reg, 1, &val);
    return val;
}

void ADS1292R::writeRegister(uint8_t reg, uint8_t value) {
    writeRegisters(reg, 1, &value);
}

void ADS1292R::readRegisters(uint8_t startReg, uint8_t count, uint8_t* buffer) {
    bool wasContinuous = _isContinuousMode;
    if (wasContinuous) {
        sendCommand(ADS1292R_CMD_SDATAC);
        _isContinuousMode = false;
        delayMicroseconds(20);
    }

    _spi->beginTransaction(_spiSettings);
    if (_pins.cs >= 0) digitalWrite(_pins.cs, LOW);

    _spi->transfer(ADS1292R_CMD_RREG | (startReg & 0x1F));
    _spi->transfer((count - 1) & 0x1F);

    delayMicroseconds(10);

    for (uint8_t i = 0; i < count; i++) {
        buffer[i] = _spi->transfer(0x00);
    }

    if (_pins.cs >= 0) digitalWrite(_pins.cs, HIGH);
    _spi->endTransaction();

    if (wasContinuous) {
        sendCommand(ADS1292R_CMD_RDATAC);
        _isContinuousMode = true;
        delayMicroseconds(20);
    }
}

void ADS1292R::writeRegisters(uint8_t startReg, uint8_t count, const uint8_t* data) {
    bool wasContinuous = _isContinuousMode;
    if (wasContinuous) {
        sendCommand(ADS1292R_CMD_SDATAC);
        _isContinuousMode = false;
        delayMicroseconds(20);
    }

    _spi->beginTransaction(_spiSettings);
    if (_pins.cs >= 0) digitalWrite(_pins.cs, LOW);

    _spi->transfer(ADS1292R_CMD_WREG | (startReg & 0x1F));
    _spi->transfer((count - 1) & 0x1F);

    for (uint8_t i = 0; i < count; i++) {
        _spi->transfer(data[i]);
    }

    delayMicroseconds(10);

    if (_pins.cs >= 0) digitalWrite(_pins.cs, HIGH);
    _spi->endTransaction();

    if (wasContinuous) {
        sendCommand(ADS1292R_CMD_RDATAC);
        _isContinuousMode = true;
        delayMicroseconds(20);
    }
}

uint8_t ADS1292R::getDeviceID() {
    return readRegister(ADS1292R_REG_ID);
}

void ADS1292R::setSampleRate(ADS1292R_Rate rate) {
    uint8_t cfg1 = readRegister(ADS1292R_REG_CONFIG1);
    cfg1 = (cfg1 & 0xF8) | (rate & 0x07);
    writeRegister(ADS1292R_REG_CONFIG1, cfg1);
}

void ADS1292R::configChannel(uint8_t channel, ADS1292R_Gain gain, ADS1292R_InputType inputType) {
    uint8_t val = (gain & 0x70) | (inputType & 0x07);
    if (channel == 1) {
        _ch1Gain = gain;
        writeRegister(ADS1292R_REG_CH1SET, val);
    } else if (channel == 2) {
        _ch2Gain = gain;
        writeRegister(ADS1292R_REG_CH2SET, val);
    }
    updateScales();
}

void ADS1292R::setTestSignal(bool enable) {
    if (enable) {
        // Cấu hình phát xung vuông 1Hz, biên độ ±1mV
        writeRegister(ADS1292R_REG_CONFIG2, 0xA3); // INT_TEST = 1, TEST_FREQ = 1Hz
        configChannel(1, _ch1Gain, ADS_INPUT_TEST_SIGNAL);
        configChannel(2, _ch2Gain, ADS_INPUT_TEST_SIGNAL);
        Serial.println("[ADS1292R] Da bat che do test xung vuong noi bo 1Hz!");
    } else {
        writeRegister(ADS1292R_REG_CONFIG2, 0xA0); // INT_TEST = 0
        configChannel(1, _ch1Gain, ADS_INPUT_NORMAL);
        configChannel(2, _ch2Gain, ADS_INPUT_NORMAL);
        Serial.println("[ADS1292R] Da ve che do do dien cuc binh thuong!");
    }
}

void ADS1292R::start() {
    if (_pins.start >= 0) {
        digitalWrite(_pins.start, HIGH);
    } else {
        sendCommand(ADS1292R_CMD_START);
    }
}

void ADS1292R::stop() {
    if (_pins.start >= 0) {
        digitalWrite(_pins.start, LOW);
    } else {
        sendCommand(ADS1292R_CMD_STOP);
    }
}

bool ADS1292R::isDataReady() const {
    if (_pins.drdy >= 0) {
        return (digitalRead(_pins.drdy) == LOW);
    }
    return false;
}

bool ADS1292R::readSample(ADS1292R_Sample& sample) {
    uint8_t raw[9] = {0};

    _spi->beginTransaction(_spiSettings);
    if (_pins.cs >= 0) digitalWrite(_pins.cs, LOW);

    // Trong che do RDATAC, chi can gui 9 byte xung clock de doc 9 byte data
    for (uint8_t i = 0; i < 9; i++) {
        raw[i] = _spi->transfer(0x00);
    }

    if (_pins.cs >= 0) digitalWrite(_pins.cs, HIGH);
    _spi->endTransaction();

    // 1. Status Word (24-bit): byte 0, 1, 2
    // Header hop le: 4 bit cao cua byte 0 phai la 0b1100 (0xC0)
    sample.status = ((uint32_t)raw[0] << 16) | ((uint32_t)raw[1] << 8) | raw[2];
    sample.valid = ((raw[0] & 0xF0) == 0xC0);

    // 2. Channel 1 (24-bit bù 2): byte 3, 4, 5
    int32_t ch1 = ((int32_t)raw[3] << 16) | ((int32_t)raw[4] << 8) | raw[5];
    if (ch1 & 0x800000) { // Sign extension
        ch1 |= 0xFF000000;
    }
    sample.ch1_raw = ch1;
    sample.ch1_mv = (float)ch1 * _ch1Scale_mV;

    // 3. Channel 2 (24-bit bù 2): byte 6, 7, 8
    int32_t ch2 = ((int32_t)raw[6] << 16) | ((int32_t)raw[7] << 8) | raw[8];
    if (ch2 & 0x800000) { // Sign extension
        ch2 |= 0xFF000000;
    }
    sample.ch2_raw = ch2;
    sample.ch2_mv = (float)ch2 * _ch2Scale_mV;

    return sample.valid;
}
