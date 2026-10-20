#include "SampleAcquisition.h"
#include "protocentralAds1292r.h"
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

namespace {
constexpr size_t QUEUE_SAMPLES = 512; // 256 ms at 2000 SPS
QueueHandle_t sampleQueue = nullptr;
SemaphoreHandle_t spiMutex = nullptr;
TaskHandle_t readerTask = nullptr;
portMUX_TYPE stateMux = portMUX_INITIALIZER_UNLOCKED;
uint32_t edgeSequence = 0;
uint32_t edgeTimestampUs = 0;
AcquisitionStats stats = {};
int drdy = -1;
int cs = -1;

void IRAM_ATTR onDataReady() {
  const uint32_t now = static_cast<uint32_t>(esp_timer_get_time());
  portENTER_CRITICAL_ISR(&stateMux);
  ++edgeSequence;
  edgeTimestampUs = now;
  portEXIT_CRITICAL_ISR(&stateMux);
  BaseType_t higherPriorityWoken = pdFALSE;
  vTaskNotifyGiveFromISR(readerTask, &higherPriorityWoken);
  if (higherPriorityWoken) portYIELD_FROM_ISR();
}

void acquire(void *) {
  // Install GPIO interrupt on the same core as this task.
  readerTask = xTaskGetCurrentTaskHandle();
  attachInterrupt(digitalPinToInterrupt(drdy), onDataReady, FALLING);
  ads1292r adc;
  ads1292OutputValues values;
  uint32_t lastHandled = 0;
  for (;;) {
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    xSemaphoreTake(spiMutex, portMAX_DELAY);
    AcquiredSample sample = {};
    portENTER_CRITICAL(&stateMux);
    sample.sequence = edgeSequence;
    sample.timestampUs = edgeTimestampUs;
    portEXIT_CRITICAL(&stateMux);
    if (sample.sequence == lastHandled) {
      xSemaphoreGive(spiMutex);
      continue;
    }
    const uint32_t skipped = sample.sequence - lastHandled - 1;
    lastHandled = sample.sequence;
    const bool read = adc.getAds1292EcgAndRespirationSamples(drdy, cs, &values);
    portENTER_CRITICAL(&stateMux);
    // A conversion arriving during the transfer makes the frame ambiguous.
    const bool valid = read && edgeSequence == sample.sequence;
    stats.missed += skipped + (valid ? 0 : 1);
    if (valid) ++stats.captured;
    portEXIT_CRITICAL(&stateMux);
    xSemaphoreGive(spiMutex);
    if (!valid) continue;
    sample.ch1 = values.sDaqVals[0];
    sample.ch2 = values.sDaqVals[1];
    sample.leadOff = values.leadoffDetected;
    // Never block ADC capture on the consumer or on UART transmission.
    if (xQueueSend(sampleQueue, &sample, 0) != pdTRUE) {
      portENTER_CRITICAL(&stateMux);
      ++stats.queueDrops;
      portEXIT_CRITICAL(&stateMux);
    }
  }
}
} // namespace

bool beginAcquisition(int drdyPin, int csPin) {
  drdy = drdyPin;
  cs = csPin;
  sampleQueue = xQueueCreate(QUEUE_SAMPLES, sizeof(AcquiredSample));
  spiMutex = xSemaphoreCreateMutex();
  if (!sampleQueue || !spiMutex) return false;
  return xTaskCreatePinnedToCore(acquire, "ads_capture", 4096, nullptr, 3,
                               nullptr, 0) == pdPASS;
}

bool receiveSample(AcquiredSample &sample) {
  return xQueueReceive(sampleQueue, &sample, pdMS_TO_TICKS(2)) == pdTRUE;
}

AcquisitionStats acquisitionStats() {
  portENTER_CRITICAL(&stateMux);
  AcquisitionStats result = stats;
  result.edges = edgeSequence;
  portEXIT_CRITICAL(&stateMux);
  return result;
}

void lockAcquisitionSpi() { xSemaphoreTake(spiMutex, portMAX_DELAY); }
void unlockAcquisitionSpi() { xSemaphoreGive(spiMutex); }
