#include "arduino/ArduinoSfMixerMotionIo.h"

#include <Arduino.h>

namespace labforge {
namespace {
constexpr uint8_t kSfMixerStepPin = 6;
constexpr uint8_t kSfMixerDirectionPin = 7;
}  // namespace

void ArduinoSfMixerMotionIo::begin() {
  digitalWrite(kSfMixerStepPin, LOW);
  digitalWrite(kSfMixerDirectionPin, LOW);
  pinMode(kSfMixerStepPin, OUTPUT);
  pinMode(kSfMixerDirectionPin, OUTPUT);
}

void ArduinoSfMixerMotionIo::writeDirection(bool high) {
  digitalWrite(kSfMixerDirectionPin, high ? HIGH : LOW);
}

void ArduinoSfMixerMotionIo::writeStep(bool high) {
  digitalWrite(kSfMixerStepPin, high ? HIGH : LOW);
}

void ArduinoSfMixerMotionIo::pulseStep(uint16_t highUs) {
  digitalWrite(kSfMixerStepPin, HIGH);
  delayMicroseconds(highUs);
  digitalWrite(kSfMixerStepPin, LOW);
}

}  // namespace labforge
