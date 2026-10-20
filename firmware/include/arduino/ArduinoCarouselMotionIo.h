#pragma once

#include "actuator/CarouselMotionController.h"

namespace labforge {

class ArduinoCarouselMotionIo final : public CarouselMotionIo {
 public:
  void begin();
  void writeDirection(bool high) override;
  void writeStep(bool high) override;
  void pulseStep(uint16_t highUs) override;
};

}  // namespace labforge
