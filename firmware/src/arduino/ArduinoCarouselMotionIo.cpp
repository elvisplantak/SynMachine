#include "arduino/ArduinoCarouselMotionIo.h"

#include <Arduino.h>

namespace labforge {
namespace {
constexpr uint8_t kCarouselStepPin = 8;
constexpr uint8_t kCarouselDirectionPin = 9;
}  // namespace

void ArduinoCarouselMotionIo::begin() {
  digitalWrite(kCarouselStepPin, LOW);
  digitalWrite(kCarouselDirectionPin, LOW);
  pinMode(kCarouselStepPin, OUTPUT);
  pinMode(kCarouselDirectionPin, OUTPUT);
}

void ArduinoCarouselMotionIo::writeDirection(bool high) {
  digitalWrite(kCarouselDirectionPin, high ? HIGH : LOW);
}

void ArduinoCarouselMotionIo::writeStep(bool high) {
  digitalWrite(kCarouselStepPin, high ? HIGH : LOW);
}

void ArduinoCarouselMotionIo::pulseStep(uint16_t highUs) {
  digitalWrite(kCarouselStepPin, HIGH);
  delayMicroseconds(highUs);
  digitalWrite(kCarouselStepPin, LOW);
}

}  // namespace labforge
