#include "actuator/CarouselMotionController.h"

namespace labforge {
namespace {

bool timeReached(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}

bool validPosition(uint8_t position) {
  return position >= 1 && position <= kCarouselPositionCount;
}

}  // namespace

CarouselMotionController::CarouselMotionController(CarouselMotionIo& io)
    : io_(io) {}

CarouselPrepareResult CarouselMotionController::prepareSetReference(
    uint8_t position) {
  if (busy()) return CarouselPrepareResult::BUSY;
  if (!validPosition(position)) return CarouselPrepareResult::INVALID_POSITION;
  targetPosition_ = position;
  state_ = CarouselMotionState::PREPARED_REFERENCE;
  return CarouselPrepareResult::READY;
}

CarouselPrepareResult CarouselMotionController::prepareMoveToPosition(
    uint8_t position) {
  if (busy()) return CarouselPrepareResult::BUSY;
  if (!validPosition(position)) return CarouselPrepareResult::INVALID_POSITION;
  if (trust_ != CarouselPositionTrust::TRUSTED)
    return CarouselPrepareResult::POSITION_UNTRUSTED;
  if (position == position_)
    return CarouselPrepareResult::TARGET_ALREADY_REACHED;
  targetPosition_ = position;
  const uint8_t positions = targetPosition_ > position_
                                ? targetPosition_ - position_
                                : kCarouselPositionCount - position_ +
                                      targetPosition_;
  totalPulses_ = static_cast<uint16_t>(positions) *
                 kCarouselPulsesPerPosition;
  state_ = CarouselMotionState::PREPARED_MOVE;
  return CarouselPrepareResult::READY;
}

bool CarouselMotionController::start(uint32_t nowUs) {
  if (state_ == CarouselMotionState::PREPARED_REFERENCE) {
    state_ = CarouselMotionState::REFERENCE_PENDING;
    return true;
  }
  if (state_ != CarouselMotionState::PREPARED_MOVE) return false;
  emittedPulses_ = 0;
  io_.writeDirection(true);
  nextPulseUs_ = nowUs + kCarouselDirectionSetupUs;
  state_ = CarouselMotionState::MOVING;
  return true;
}

CarouselMotionResult CarouselMotionController::update(uint32_t nowUs) {
  if (state_ == CarouselMotionState::REFERENCE_PENDING) {
    position_ = targetPosition_;
    trust_ = CarouselPositionTrust::TRUSTED;
    state_ = CarouselMotionState::IDLE;
    return CarouselMotionResult::COMPLETED;
  }
  if (state_ != CarouselMotionState::MOVING ||
      !timeReached(nowUs, nextPulseUs_))
    return CarouselMotionResult::NONE;
  io_.pulseStep(kCarouselStepHighUs);
  ++emittedPulses_;
  if (emittedPulses_ >= totalPulses_) return finish();
  nextPulseUs_ = nowUs + intervalForPulse(emittedPulses_);
  return CarouselMotionResult::NONE;
}

bool CarouselMotionController::abort() {
  if (state_ == CarouselMotionState::IDLE) return false;
  const bool started = state_ == CarouselMotionState::MOVING;
  io_.writeStep(false);
  state_ = CarouselMotionState::IDLE;
  if (started) trust_ = CarouselPositionTrust::UNTRUSTED;
  return true;
}

CarouselMotionState CarouselMotionController::state() const { return state_; }
CarouselPositionTrust CarouselMotionController::positionTrust() const {
  return trust_;
}
uint8_t CarouselMotionController::position() const { return position_; }
bool CarouselMotionController::busy() const {
  return state_ != CarouselMotionState::IDLE;
}

uint32_t CarouselMotionController::intervalForPulse(uint16_t pulseIndex) const {
  const uint16_t remaining = totalPulses_ - pulseIndex;
  uint16_t rampIndex = kCarouselRampPulses;
  if (pulseIndex < rampIndex) {
    rampIndex = pulseIndex;
  } else if (remaining < rampIndex) {
    rampIndex = remaining;
  }
  if (rampIndex >= kCarouselRampPulses) return kCarouselCruiseIntervalUs;
  const uint32_t x =
      (static_cast<uint32_t>(rampIndex) * 1024U) / kCarouselRampPulses;
  const uint32_t smooth = (3UL * x * x * 1024UL - 2UL * x * x * x) /
                          (1024UL * 1024UL);
  return kCarouselStartIntervalUs -
         ((kCarouselStartIntervalUs - kCarouselCruiseIntervalUs) * smooth) /
             1024U;
}

CarouselMotionResult CarouselMotionController::finish() {
  io_.writeStep(false);
  position_ = targetPosition_;
  state_ = CarouselMotionState::IDLE;
  return CarouselMotionResult::COMPLETED;
}

}  // namespace labforge
