#include "arduino/ArduinoP1MotionIo.h"

#include <Arduino.h>

namespace labforge {
namespace {
constexpr uint8_t kP1StepPin = 46;
constexpr uint8_t kP1DirectionPin = 47;
constexpr uint8_t kP1HomePin = 45;
}  // namespace

void ArduinoP1MotionIo::begin() {
  digitalWrite(kP1StepPin, LOW);
  digitalWrite(kP1DirectionPin, LOW);
  pinMode(kP1StepPin, OUTPUT);
  pinMode(kP1DirectionPin, OUTPUT);
  pinMode(kP1HomePin, INPUT_PULLUP);
}

bool ArduinoP1MotionIo::homeActive() const {
  return digitalRead(kP1HomePin) == HIGH;
}

void ArduinoP1MotionIo::writeDirection(bool high) {
  digitalWrite(kP1DirectionPin, high ? HIGH : LOW);
}

void ArduinoP1MotionIo::writeStep(bool high) {
  digitalWrite(kP1StepPin, high ? HIGH : LOW);
}

void ArduinoP1MotionIo::pulseStep(uint16_t highUs) {
  digitalWrite(kP1StepPin, HIGH);
  delayMicroseconds(highUs);
  digitalWrite(kP1StepPin, LOW);
}

}  // namespace labforge
