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
#ifndef ads1292r_h
#define ads1292r_h

#include <Arduino.h>
#include <SPI.h>

#define CONFIG_SPI_MASTER_DUMMY   0x00

// ADS1292 SPI Configuration
// Maximum SCLK for internal clock (2.048 MHz) is fCLK/2 = 1.024 MHz.
// ADS1292 requires SPI_MODE1 (CPOL = 0, CPHA = 1) and MSBFIRST.
#define ADS1292_SPI_CLOCK         1000000
#define ADS1292_SPI_BITORDER      MSBFIRST
#define ADS1292_SPI_MODE          SPI_MODE1

// System Commands
#define CMD_WAKEUP                0x02
#define CMD_STANDBY               0x04
#define CMD_RESET                 0x06
#define CMD_START                 0x08
#define CMD_STOP                  0x0A
#define CMD_OFFSETCAL             0x1A

// Data Read Commands
#define CMD_RDATAC                0x10
#define CMD_SDATAC                0x11
#define CMD_RDATA                 0x12

// Legacy Command Aliases (Maintained for full compatibility)
#define START                     0x08
#define STOP                      0x0A
#define RDATAC                    0x10
#define SDATAC                    0x11
#define RDATA                     0x12

// Register Read/Write Commands (Opcodes)
#define RREG                      0x20
#define WREG                      0x40

// ADS1292 Register Addresses
#define ADS1292_REG_ID            0x00
#define ADS1292_REG_CONFIG1       0x01
#define ADS1292_REG_CONFIG2       0x02
#define ADS1292_REG_LOFF          0x03
#define ADS1292_REG_CH1SET        0x04
#define ADS1292_REG_CH2SET        0x05
#define ADS1292_REG_RLDSENS       0x06
#define ADS1292_REG_LOFFSENS      0x07
#define ADS1292_REG_LOFFSTAT      0x08
#define ADS1292_REG_RESP1         0x09
#define ADS1292_REG_RESP2         0x0A
#define ADS1292_REG_GPIO          0x0B

// Packet format for streaming/ProtoCentral GUI
#define CES_CMDIF_PKT_START_1     0x0A
#define CES_CMDIF_PKT_START_2     0xFA
#define CES_CMDIF_TYPE_DATA       0x02
#define CES_CMDIF_PKT_STOP_1      0x00
#define CES_CMDIF_PKT_STOP_2      0x0B

typedef struct Record {
  volatile signed long sDaqVals[8];
  boolean leadoffDetected = true;
  signed long sresultTempResp;
} ads1292OutputValues;

class ads1292r
{
  public:
    // SPI bus instance and transaction settings
    static SPIClass *_spi;
    static SPISettings _spiSettings;

    // SPI Configuration for ESP32 / ESP32-S3
    static void setSPI(SPIClass *spiBus);
    static void setSPISettings(SPISettings settings);
    static void setSPISettings(uint32_t clock, uint8_t bitOrder, uint8_t dataMode);

    // Initialization & Hardware Control
    static void ads1292Init(const int chipSelect, const int pwdnPin, const int startPin);
    static void ads1292Init(SPIClass &spiBus, const int chipSelect, const int pwdnPin, const int startPin);
    static void ads1292Reset(const int pwdnPin);
    static void ads1292SoftReset(const int chipSelect);

    // Register Read & Write
    static uint8_t ads1292RegRead(unsigned char READ_ADDRESS, const int chipSelect);
    static void ads1292RegWrite(unsigned char READ_WRITE_ADDRESS, unsigned char DATA, const int chipSelect);
    static uint8_t ads1292GetDeviceID(const int chipSelect);

    // SPI Commands
    static void ads1292SPICommandData(unsigned char dataIn, const int chipSelect);
    static void ads1292DisableStart(const int startPin);
    static void ads1292EnableStart(const int startPin);
    static void ads1292HardStop(const int startPin);
    static void ads1292StartDataConvCommand(const int chipSelect);
    static void ads1292SoftStop(const int chipSelect);
    static void ads1292StartReadDataContinuous(const int chipSelect);
    static void ads1292StopReadDataContinuous(const int chipSelect);

    // Data Reading
    static char* ads1292ReadData(const int chipSelect);
    static boolean readRawSamples(const int chipSelect, uint8_t *buffer9Bytes);
    boolean getAds1292EcgAndRespirationSamples(const int dataReady, const int chipSelect, ads1292OutputValues *ecgRespirationValues);
};

#endif
