#pragma once

#include <stdint.h>

#include "actuator/ValveMotionController.h"

namespace labforge {

constexpr uint32_t kColumnValveClosedSteps = 889;
constexpr uint32_t kColumnValveOpenSteps = 24739;
constexpr uint32_t kColumnValveMaximumSearchSteps = 80000;
constexpr uint32_t kColumnValveStepIntervalUs = 1000;
constexpr uint16_t kColumnValveStepHighUs = 20;
constexpr uint16_t kColumnValveDirectionSetupUs = 5;
constexpr uint32_t kColumnValveHomeStableUs = 30000;

enum class ColumnValvePositionTrust : uint8_t { UNTRUSTED, TRUSTED };
enum class ColumnValvePrepareResult : uint8_t {
  READY,
  BUSY,
  POSITION_UNTRUSTED,
  TARGET_ALREADY_REACHED,
  INVALID_TARGET,
};
enum class ColumnValveMotionResult : uint8_t {
  NONE,
  COMPLETED,
  MOTION_TIMEOUT,
  HOME_SWITCH_UNEXPECTED,
  HOME_SWITCH_STUCK,
};
enum class ColumnValveMotionState : uint8_t {
  IDLE,
  PREPARED_HOME,
  PREPARED_MOVE,
  CONFIRMING_HOME,
  CONFIRMING_TRUSTED_HOME,
  CONFIRMING_HOME_RELEASE,
  SEARCHING_HOME,
  MOVING,
  CONFIRMING_UNEXPECTED_HOME,
};

class ColumnBottomValveMotionController {
 public:
  explicit ColumnBottomValveMotionController(ValveMotionIo& io);

  ColumnValvePrepareResult prepareHome();
  ColumnValvePrepareResult prepareSetPosition(uint16_t targetDegrees);
  bool start(uint32_t nowUs);
  ColumnValveMotionResult update(uint32_t nowUs);
  bool abort();

  ColumnValveMotionState state() const;
  ColumnValvePositionTrust positionTrust() const;
  uint32_t positionSteps() const;
  uint32_t stageSteps() const;
  bool homeActive() const;
  bool busy() const;

 private:
  void beginMotion(ColumnValveMotionState state, bool directionHigh,
                   uint32_t nowUs);
  void pauseForHome(uint32_t nowUs, ColumnValveMotionState state);
  bool pulseDue(uint32_t nowUs) const;
  void emitPulse(uint32_t nowUs);
  ColumnValveMotionResult finish(ColumnValveMotionResult result);

  ValveMotionIo& io_;
  ColumnValveMotionState state_ = ColumnValveMotionState::IDLE;
  ColumnValvePositionTrust trust_ = ColumnValvePositionTrust::UNTRUSTED;
  uint32_t positionSteps_ = 0;
  uint32_t targetSteps_ = 0;
  uint32_t stageSteps_ = 0;
  uint32_t nextPulseUs_ = 0;
  uint32_t homeStableSinceUs_ = 0;
  bool homeCandidateActive_ = false;
  bool directionHigh_ = false;
  bool releasingHome_ = false;
  bool releaseTravelExhausted_ = false;
};

}  // namespace labforge
