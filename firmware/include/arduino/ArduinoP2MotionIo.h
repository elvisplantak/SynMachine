#pragma once

#include "actuator/P1MotionController.h"

namespace labforge {

class ArduinoP2MotionIo final : public P1MotionIo {
 public:
  void begin();
  bool homeActive() const override;
  void writeDirection(bool high) override;
  void writeStep(bool high) override;
  void pulseStep(uint16_t highUs) override;
};

}  // namespace labforge
