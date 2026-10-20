#include "arduino/ArduinoValveMotionIo.h"

#include <Arduino.h>

namespace labforge {

ArduinoValveMotionIo::ArduinoValveMotionIo(uint8_t stepPin,
                                           uint8_t directionPin,
                                           uint8_t homePin)
    : stepPin_(stepPin), directionPin_(directionPin), homePin_(homePin) {}

void ArduinoValveMotionIo::begin() {
  digitalWrite(stepPin_, LOW);
  digitalWrite(directionPin_, LOW);
  pinMode(stepPin_, OUTPUT);
  pinMode(directionPin_, OUTPUT);
  pinMode(homePin_, INPUT_PULLUP);
}

bool ArduinoValveMotionIo::homeActive() const {
  return digitalRead(homePin_) == HIGH;
}

void ArduinoValveMotionIo::writeDirection(bool high) {
  digitalWrite(directionPin_, high ? HIGH : LOW);
}

void ArduinoValveMotionIo::writeStep(bool high) {
  digitalWrite(stepPin_, high ? HIGH : LOW);
}

void ArduinoValveMotionIo::pulseStep(uint16_t highUs) {
  digitalWrite(stepPin_, HIGH);
  delayMicroseconds(highUs);
  digitalWrite(stepPin_, LOW);
}

}  // namespace labforge
