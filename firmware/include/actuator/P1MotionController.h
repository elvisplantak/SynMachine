#pragma once

#include <stdint.h>

#include "protocol/CommandStatusCache.h"

namespace labforge {

constexpr uint32_t kP1StepIntervalUs = 1500;
constexpr uint16_t kP1StepHighUs = 20;
constexpr uint16_t kP1HomeReleaseMaximumSteps = 200;

class P1MotionIo {
 public:
  virtual ~P1MotionIo() = default;
  virtual bool homeActive() const = 0;
  virtual void writeDirection(bool high) = 0;
  virtual void writeStep(bool high) = 0;
};

enum class P1PositionTrust : uint8_t { UNTRUSTED, TRUSTED };
enum class P1MotionState : uint8_t {
  IDLE,
  PREPARED_HOME,
  PREPARED_MOVE,
  RELEASING_HOME,
  SEARCHING_HOME,
  MOVING,
};
enum class P1PrepareResult : uint8_t {
  READY,
  BUSY,
  POSITION_UNTRUSTED,
  TARGET_REQUIRES_HOME,
  TARGET_ALREADY_REACHED,
  INVALID_TARGET,
  HOME_SWITCH_ACTIVE,
};
enum class P1MotionResult : uint8_t {
  NONE,
  COMPLETED,
  MOTION_TIMEOUT,
  HOME_SWITCH_UNEXPECTED,
  HOME_SWITCH_STUCK,
};

class P1MotionController {
 public:
  explicit P1MotionController(P1MotionIo& io);

  P1PrepareResult prepareHome();
  P1PrepareResult prepareMoveAbsolute(uint16_t targetSteps);
  bool start(uint32_t nowUs);
  P1MotionResult update(uint32_t nowUs);

  P1MotionState state() const;
  P1PositionTrust positionTrust() const;
  uint16_t positionSteps() const;
  bool busy() const;

 private:
  enum class PulsePhase : uint8_t { WAITING_TO_RISE, HIGH };

  void beginStage(P1MotionState state, bool directionHigh, uint32_t nowUs);
  bool pulseDue(uint32_t nowUs) const;
  bool finishPulse(uint32_t nowUs);
  P1MotionResult finish(P1MotionResult result);

  P1MotionIo& io_;
  P1MotionState state_ = P1MotionState::IDLE;
  P1PositionTrust trust_ = P1PositionTrust::UNTRUSTED;
  PulsePhase pulsePhase_ = PulsePhase::WAITING_TO_RISE;
  uint16_t positionSteps_ = 0;
  uint16_t targetSteps_ = 0;
  uint16_t stageSteps_ = 0;
  uint32_t nextPulseUs_ = 0;
  bool directionHigh_ = false;
  bool releasingHomeDuringMove_ = false;
};

}  // namespace labforge
