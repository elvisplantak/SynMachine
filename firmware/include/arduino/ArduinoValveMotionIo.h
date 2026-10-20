#pragma once

#include <stdint.h>

#include "actuator/ValveMotionController.h"

namespace labforge {

class ArduinoValveMotionIo final : public ValveMotionIo {
 public:
  ArduinoValveMotionIo(uint8_t stepPin, uint8_t directionPin,
                       uint8_t homePin);
  void begin();
  bool homeActive() const override;
  void writeDirection(bool high) override;
  void writeStep(bool high) override;
  void pulseStep(uint16_t highUs) override;

 private:
  const uint8_t stepPin_;
  const uint8_t directionPin_;
  const uint8_t homePin_;
};

}  // namespace labforge
