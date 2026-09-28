//////////////////////////////////////////////////////////////////////////////////////////
//
//   Arduino Library for ADS1292R Shield/Breakout
//   Adapted and Optimized for ESP32 / ESP32-S3
//
//   Original Copyright (c) 2017 ProtoCentral
//   This software is licensed under the MIT License(http://opensource.org/licenses/MIT).
//
//   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
//   NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
//   IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
//   WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
//   SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
//
/////////////////////////////////////////////////////////////////////////////////////////
#include <Arduino.h>
#include <SPI.h>
#include "protocentralAds1292r.h"

// Default SPI bus and settings (1MHz, MSBFIRST, SPI_MODE1 as required by ADS1292)
SPIClass* ads1292r::_spi = &SPI;
SPISettings ads1292r::_spiSettings = SPISettings(ADS1292_SPI_CLOCK, ADS1292_SPI_BITORDER, ADS1292_SPI_MODE);

void ads1292r::setSPI(SPIClass *spiBus)
{
  if (spiBus != nullptr) {
    _spi = spiBus;
  }
}

void ads1292r::setSPISettings(SPISettings settings)
{
  _spiSettings = settings;
}

void ads1292r::setSPISettings(uint32_t clock, uint8_t bitOrder, uint8_t dataMode)
{
  _spiSettings = SPISettings(clock, bitOrder, dataMode);
}

void ads1292r::ads1292Init(SPIClass &spiBus, const int chipSelect, const int pwdnPin, const int startPin)
{
  _spi = &spiBus;
  ads1292Init(chipSelect, pwdnPin, startPin);
}

void ads1292r::ads1292Reset(const int pwdnPin)
{
  pinMode(pwdnPin, OUTPUT);
  digitalWrite(pwdnPin, HIGH);
  delay(100);                    // Wait for power supplies to stabilize
  digitalWrite(pwdnPin, LOW);
  delay(20);                     // Reset pulse: min 2 tCLK (>= 1us)
  digitalWrite(pwdnPin, HIGH);
  delay(100);                    // Wait for oscillator and reference to stabilize (min 18 tCLK)
}

void ads1292r::ads1292SoftReset(const int chipSelect)
{
  ads1292SPICommandData(CMD_RESET, chipSelect);
  delay(10);                     // Wait at least 18 tCLK after reset
}

void ads1292r::ads1292DisableStart(const int startPin)
{
  pinMode(startPin, OUTPUT);
  digitalWrite(startPin, LOW);
  delayMicroseconds(20);
}

void ads1292r::ads1292EnableStart(const int startPin)
{
  pinMode(startPin, OUTPUT);
  digitalWrite(startPin, HIGH);
  delayMicroseconds(20);
}

void ads1292r::ads1292HardStop(const int startPin)
{
  pinMode(startPin, OUTPUT);
  digitalWrite(startPin, LOW);
  delay(50);
}

void ads1292r::ads1292StartDataConvCommand(const int chipSelect)
{
  ads1292SPICommandData(CMD_START, chipSelect);
}

void ads1292r::ads1292SoftStop(const int chipSelect)
{
  ads1292SPICommandData(CMD_STOP, chipSelect);
}

void ads1292r::ads1292StartReadDataContinuous(const int chipSelect)
{
  ads1292SPICommandData(CMD_RDATAC, chipSelect);
}

void ads1292r::ads1292StopReadDataContinuous(const int chipSelect)
{
  ads1292SPICommandData(CMD_SDATAC, chipSelect);
}

void ads1292r::ads1292SPICommandData(unsigned char dataIn, const int chipSelect)
{
  _spi->beginTransaction(_spiSettings);
  digitalWrite(chipSelect, LOW);
  delayMicroseconds(2);

  _spi->transfer(dataIn);

  delayMicroseconds(2);
  digitalWrite(chipSelect, HIGH);
  _spi->endTransaction();
  delayMicroseconds(4); // Wait tSDECODE (min 4 tCLK)
}

uint8_t ads1292r::ads1292RegRead(unsigned char READ_ADDRESS, const int chipSelect)
{
  uint8_t dataToSend = (READ_ADDRESS & 0x1F) | RREG;
  uint8_t val = 0;

  _spi->beginTransaction(_spiSettings);
  digitalWrite(chipSelect, LOW);
  delayMicroseconds(2);

  _spi->transfer(dataToSend);
  delayMicroseconds(2);
  _spi->transfer(0x00);       // Read 1 register (n - 1 = 0)
  delayMicroseconds(4);       // tSDECODE delay (at least 4 tCLK cycles)
  val = _spi->transfer(CONFIG_SPI_MASTER_DUMMY);

  delayMicroseconds(2);
  digitalWrite(chipSelect, HIGH);
  _spi->endTransaction();

  return val;
}

void ads1292r::ads1292RegWrite(unsigned char READ_WRITE_ADDRESS, unsigned char DATA, const int chipSelect)
{
  // Mask reserved bits as specified in ADS1292 datasheet
  switch (READ_WRITE_ADDRESS)
  {
    case 1:  DATA = DATA & 0x87; break;
    case 2:  DATA = (DATA & 0xFB) | 0x80; break;
    case 3:  DATA = (DATA & 0xFD) | 0x10; break;
    case 7:  DATA = DATA & 0x3F; break;
    case 8:  DATA = DATA & 0x5F; break;
    case 9:  DATA |= 0x02; break;
    case 10: DATA = (DATA & 0x87) | 0x01; break;
    case 11: DATA = DATA & 0x0F; break;
    default: break;
  }

  uint8_t dataToSend = (READ_WRITE_ADDRESS & 0x1F) | WREG;

  _spi->beginTransaction(_spiSettings);
  digitalWrite(chipSelect, LOW);
  delayMicroseconds(2);

  _spi->transfer(dataToSend);
  delayMicroseconds(2);
  _spi->transfer(0x00);       // Write 1 register (n - 1 = 0)
  delayMicroseconds(4);       // tSDECODE delay (at least 4 tCLK cycles)
  _spi->transfer(DATA);

  delayMicroseconds(2);
  digitalWrite(chipSelect, HIGH);
  _spi->endTransaction();
}

uint8_t ads1292r::ads1292GetDeviceID(const int chipSelect)
{
  // Safely stop continuous mode to read the ID register
  ads1292StopReadDataContinuous(chipSelect);
  delayMicroseconds(50);
  uint8_t id = ads1292RegRead(ADS1292_REG_ID, chipSelect);
  return id;
}

void ads1292r::ads1292Init(const int chipSelect, const int pwdnPin, const int startPin)
{
  // 1. Ensure pin modes are properly initialized as OUTPUT
  pinMode(chipSelect, OUTPUT);
  digitalWrite(chipSelect, HIGH);

  pinMode(pwdnPin, OUTPUT);
  digitalWrite(pwdnPin, HIGH);

  pinMode(startPin, OUTPUT);
  digitalWrite(startPin, LOW);

  // 2. Hardware reset ADS1292
  ads1292Reset(pwdnPin);
  delay(100);

  // 3. Keep START LOW so that ADC conversions are paused (no DRDY collision)
  ads1292HardStop(startPin);
  delay(50);

  // 4. Send SDATAC command (0x11) FIRST as required by TI datasheet after reset
  ads1292StopReadDataContinuous(chipSelect); // SDATAC (0x11)
  delay(50);

  // 5. Configure ADS1292 registers
  ads1292RegWrite(ADS1292_REG_CONFIG1, 0x03, chipSelect);         // Sampling rate 1 kSPS (EMG)
  delay(10);
  ads1292RegWrite(ADS1292_REG_CONFIG2, 0b10100000, chipSelect);   // Lead-off comp off, test signal disabled
  delay(10);
  ads1292RegWrite(ADS1292_REG_LOFF, 0b00010000, chipSelect);      // Lead-off defaults
  delay(10);
  ads1292RegWrite(ADS1292_REG_CH1SET, 0b01000000, chipSelect);    // Ch 1 enabled, gain 4, normal electrode input (0x40)
  delay(10);
  ads1292RegWrite(ADS1292_REG_CH2SET, 0b01000000, chipSelect);    // Ch 2 enabled, gain 4, normal electrode input (0x40)
  delay(10);
  ads1292RegWrite(ADS1292_REG_RLDSENS, 0b00101100, chipSelect);   // RLD buffer ON, RLD from Ch2 (0x2C)
  delay(10);
  ads1292RegWrite(ADS1292_REG_LOFFSENS, 0x00, chipSelect);        // LOFF settings: all disabled
  delay(10);
  ads1292RegWrite(ADS1292_REG_RESP1, 0b00110010, chipSelect);     // Disable respiration modulation/demodulation for EMG
  delay(10);
  ads1292RegWrite(ADS1292_REG_RESP2, 0b00000011, chipSelect);     // Respiration calibration off, RLDREF internal
  delay(10);
}

boolean ads1292r::readRawSamples(const int chipSelect, uint8_t *buffer9Bytes)
{
  if (buffer9Bytes == nullptr) return false;

  _spi->beginTransaction(_spiSettings);
  digitalWrite(chipSelect, LOW);
  delayMicroseconds(2);

  for (int i = 0; i < 9; ++i)
  {
    buffer9Bytes[i] = _spi->transfer(CONFIG_SPI_MASTER_DUMMY);
  }

  delayMicroseconds(2);
  digitalWrite(chipSelect, HIGH);
  _spi->endTransaction();

  return true;
}

char* ads1292r::ads1292ReadData(const int chipSelect)
{
  static char SPI_Dummy_Buff[10];

  _spi->beginTransaction(_spiSettings);
  digitalWrite(chipSelect, LOW);
  delayMicroseconds(2);

  for (int i = 0; i < 9; ++i)
  {
    SPI_Dummy_Buff[i] = (char)_spi->transfer(CONFIG_SPI_MASTER_DUMMY);
  }

  delayMicroseconds(2);
  digitalWrite(chipSelect, HIGH);
  _spi->endTransaction();

  SPI_Dummy_Buff[9] = '\0';
  return SPI_Dummy_Buff;
}

boolean ads1292r::getAds1292EcgAndRespirationSamples(const int dataReady, const int chipSelect, ads1292OutputValues *ecgRespirationValues)
{
  if (ecgRespirationValues == nullptr) return false;

  if (digitalRead(dataReady) == LOW)
  {
    uint8_t rxBuf[9];

    _spi->beginTransaction(_spiSettings);
    digitalWrite(chipSelect, LOW);
    delayMicroseconds(2);

    for (int i = 0; i < 9; ++i)
    {
      rxBuf[i] = _spi->transfer(CONFIG_SPI_MASTER_DUMMY);
    }

    delayMicroseconds(2);
    digitalWrite(chipSelect, HIGH);
    _spi->endTransaction();

    // 1. Channel 1 (Respiration / Ch1): Bytes 3, 4, 5 (24-bit signed 2's complement)
    int32_t ch1 = ((uint32_t)rxBuf[3] << 16) | ((uint32_t)rxBuf[4] << 8) | rxBuf[5];
    if (ch1 & 0x00800000) {
      ch1 |= 0xFF000000; // Sign extend to 32 bits
    }

    // 2. Channel 2 (ECG / Ch2): Bytes 6, 7, 8 (24-bit signed 2's complement)
    int32_t ch2 = ((uint32_t)rxBuf[6] << 16) | ((uint32_t)rxBuf[7] << 8) | rxBuf[8];
    if (ch2 & 0x00800000) {
      ch2 |= 0xFF000000; // Sign extend to 32 bits
    }

    ecgRespirationValues->sDaqVals[0] = ch1; // Respiration data
    ecgRespirationValues->sDaqVals[1] = ch2; // ECG data

    // Raw shifted 32-bit Respiration value for ProtoCentral GUI
    ecgRespirationValues->sresultTempResp = ((int32_t)rxBuf[3] << 24) | ((int32_t)rxBuf[4] << 16) | ((int32_t)rxBuf[5] << 8);

    // 3. Status word: Bytes 0, 1, 2
    uint32_t statusByte = ((uint32_t)rxBuf[0] << 16) | ((uint32_t)rxBuf[1] << 8) | rxBuf[2];
    uint8_t leadStatus = (uint8_t)((statusByte & 0x0F8000) >> 15);

    if ((leadStatus & 0x1F) != 0)
    {
      ecgRespirationValues->leadoffDetected = true;
    }
    else
    {
      ecgRespirationValues->leadoffDetected = false;
    }

    return true;
  }

  return false;
}
