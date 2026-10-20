#pragma once

#include "actuator/SfMixerMotionController.h"

namespace labforge {

class ArduinoSfMixerMotionIo final : public SfMixerMotionIo {
 public:
  void begin();
  void writeDirection(bool high) override;
  void writeStep(bool high) override;
  void pulseStep(uint16_t highUs) override;
};

}  // namespace labforge
