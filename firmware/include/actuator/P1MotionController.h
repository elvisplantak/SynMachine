#pragma once

#include <stdint.h>

#include "protocol/CommandStatusCache.h"

namespace labforge {

constexpr uint32_t kP1StepIntervalUs = 1500;
constexpr uint16_t kP1StepHighUs = 20;
constexpr uint16_t kP1DirectionSetupUs = 5;
constexpr uint32_t kP1HomeStableUs = 30000;
constexpr uint16_t kP1HomeReleaseMaximumSteps = 400;

static_assert(kP1StepHighUs < kP1StepIntervalUs,
              "P1 STEP high time must be shorter than its pulse interval");

class P1MotionIo {
 public:
  virtual ~P1MotionIo() = default;
  virtual bool homeActive() const = 0;
  virtual void writeDirection(bool high) = 0;
  virtual void writeStep(bool high) = 0;
  virtual void pulseStep(uint16_t highUs) = 0;
};

enum class P1PositionTrust : uint8_t { UNTRUSTED, TRUSTED };
enum class P1MotionState : uint8_t {
  IDLE,
  PREPARED_HOME,
  PREPARED_MOVE,
  CONFIRMING_TRUSTED_HOME,
  RELEASING_HOME,
  CONFIRMING_HOME_RELEASE,
  SEARCHING_HOME,
  WAITING_FINAL_HOME_SIGNAL,
  CONFIRMING_HOME_ACTIVE,
  MOVING,
  CONFIRMING_MOVE_RELEASE,
  CONFIRMING_UNEXPECTED_HOME,
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
  P1PrepareResult prepareFullAspiration();
  P1PrepareResult prepareMoveAbsolute(uint16_t targetSteps);
  bool start(uint32_t nowUs);
  P1MotionResult update(uint32_t nowUs);
  bool abort();

  P1MotionState state() const;
  P1PositionTrust positionTrust() const;
  uint16_t positionSteps() const;
  bool homeActive() const;
  bool busy() const;

 private:
  void beginStage(P1MotionState state, bool directionHigh, uint32_t nowUs);
  bool pulseDue(uint32_t nowUs) const;
  void emitPulse(uint32_t nowUs);
  void pauseForHomeStability(P1MotionState state, uint32_t nowUs);
  void resumePulses(uint32_t nowUs);
  P1MotionResult finish(P1MotionResult result);

  P1MotionIo& io_;
  P1MotionState state_ = P1MotionState::IDLE;
  P1PositionTrust trust_ = P1PositionTrust::UNTRUSTED;
  uint16_t positionSteps_ = 0;
  uint16_t targetSteps_ = 0;
  uint16_t stageSteps_ = 0;
  uint32_t nextPulseUs_ = 0;
  uint32_t homeStableSinceUs_ = 0;
  bool homeStableLevel_ = false;
  bool directionHigh_ = false;
  bool releasingHomeDuringMove_ = false;
  bool fullAspiration_ = false;
};

}  // namespace labforge
