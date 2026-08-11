#include "arduino/ArduinoP2MotionIo.h"

#include <Arduino.h>

namespace labforge {
namespace {
constexpr uint8_t kP2StepPin = 48;
constexpr uint8_t kP2DirectionPin = 49;
constexpr uint8_t kP2HomePin = 44;
}  // namespace

void ArduinoP2MotionIo::begin() {
  digitalWrite(kP2StepPin, LOW);
  digitalWrite(kP2DirectionPin, LOW);
  pinMode(kP2StepPin, OUTPUT);
  pinMode(kP2DirectionPin, OUTPUT);
  pinMode(kP2HomePin, INPUT_PULLUP);
}

bool ArduinoP2MotionIo::homeActive() const {
  return digitalRead(kP2HomePin) == HIGH;
}

void ArduinoP2MotionIo::writeDirection(bool high) {
  digitalWrite(kP2DirectionPin, high ? HIGH : LOW);
}

void ArduinoP2MotionIo::writeStep(bool high) {
  digitalWrite(kP2StepPin, high ? HIGH : LOW);
}

void ArduinoP2MotionIo::pulseStep(uint16_t highUs) {
  digitalWrite(kP2StepPin, HIGH);
  delayMicroseconds(highUs);
  digitalWrite(kP2StepPin, LOW);
}

}  // namespace labforge
