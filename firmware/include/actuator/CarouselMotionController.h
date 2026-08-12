#pragma once

#include <stdint.h>

namespace labforge {

constexpr uint8_t kCarouselPositionCount = 40;
constexpr uint16_t kCarouselPulsesPerPosition = 250;
constexpr uint16_t kCarouselStepHighUs = 20;
constexpr uint16_t kCarouselDirectionSetupUs = 5;
constexpr uint32_t kCarouselStartIntervalUs = 6000;
constexpr uint32_t kCarouselCruiseIntervalUs = 1200;
constexpr uint16_t kCarouselRampPulses = 125;

class CarouselMotionIo {
 public:
  virtual ~CarouselMotionIo() = default;
  virtual void writeDirection(bool high) = 0;
  virtual void writeStep(bool high) = 0;
  virtual void pulseStep(uint16_t highUs) = 0;
};

enum class CarouselPositionTrust : uint8_t { UNTRUSTED, TRUSTED };
enum class CarouselPrepareResult : uint8_t {
  READY,
  BUSY,
  POSITION_UNTRUSTED,
  TARGET_ALREADY_REACHED,
  INVALID_POSITION,
};
enum class CarouselMotionResult : uint8_t { NONE, COMPLETED };
enum class CarouselMotionState : uint8_t {
  IDLE,
  PREPARED_REFERENCE,
  PREPARED_MOVE,
  REFERENCE_PENDING,
  MOVING,
};

class CarouselMotionController {
 public:
  explicit CarouselMotionController(CarouselMotionIo& io);

  CarouselPrepareResult prepareSetReference(uint8_t position);
  CarouselPrepareResult prepareMoveToPosition(uint8_t position);
  bool start(uint32_t nowUs);
  CarouselMotionResult update(uint32_t nowUs);
  bool abort();
  void invalidatePositionTrust();

  CarouselMotionState state() const;
  CarouselPositionTrust positionTrust() const;
  uint8_t position() const;
  bool busy() const;

 private:
  uint32_t intervalForPulse(uint16_t pulseIndex) const;
  CarouselMotionResult finish();

  CarouselMotionIo& io_;
  CarouselMotionState state_ = CarouselMotionState::IDLE;
  CarouselPositionTrust trust_ = CarouselPositionTrust::UNTRUSTED;
  uint8_t position_ = 0;
  uint8_t targetPosition_ = 0;
  uint16_t totalPulses_ = 0;
  uint16_t emittedPulses_ = 0;
  uint32_t nextPulseUs_ = 0;
};

}  // namespace labforge
