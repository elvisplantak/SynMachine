#pragma once

#include <stdint.h>

namespace labforge {

constexpr uint16_t kValveStepsPer90Degrees = 400;
constexpr uint16_t kValveMaximumSearchSteps = 1600;
constexpr uint32_t kValveStepIntervalUs = 2000;
constexpr uint16_t kValveStepHighUs = 20;
constexpr uint16_t kValveDirectionSetupUs = 5;
constexpr uint32_t kValveHomeStableUs = 30000;

class ValveMotionIo {
 public:
  virtual ~ValveMotionIo() = default;
  virtual bool homeActive() const = 0;
  virtual void writeDirection(bool high) = 0;
  virtual void writeStep(bool high) = 0;
  virtual void pulseStep(uint16_t highUs) = 0;
};

enum class ValvePositionTrust : uint8_t { UNTRUSTED, TRUSTED };
enum class ValvePrepareResult : uint8_t {
  READY,
  BUSY,
  POSITION_UNTRUSTED,
  TARGET_ALREADY_REACHED,
  INVALID_TARGET,
};
enum class ValveMotionResult : uint8_t {
  NONE,
  COMPLETED,
  MOTION_TIMEOUT,
  HOME_SWITCH_UNEXPECTED,
  HOME_SWITCH_STUCK,
};
enum class ValveMotionState : uint8_t {
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

class ValveMotionController {
 public:
  ValveMotionController(ValveMotionIo& io, bool directionTowardHomeHigh);

  ValvePrepareResult prepareHome();
  ValvePrepareResult prepareSetPosition(uint16_t targetDegrees);
  bool start(uint32_t nowUs);
  ValveMotionResult update(uint32_t nowUs);
  bool abort();

  ValveMotionState state() const;
  ValvePositionTrust positionTrust() const;
  uint16_t positionDegrees() const;
  bool busy() const;

 private:
  void beginMotion(ValveMotionState state, bool directionHigh, uint32_t nowUs);
  void pauseForHome(uint32_t nowUs, ValveMotionState state);
  bool pulseDue(uint32_t nowUs) const;
  void emitPulse(uint32_t nowUs);
  ValveMotionResult finish(ValveMotionResult result);

  ValveMotionIo& io_;
  const bool directionTowardHomeHigh_;
  ValveMotionState state_ = ValveMotionState::IDLE;
  ValvePositionTrust trust_ = ValvePositionTrust::UNTRUSTED;
  uint16_t positionSteps_ = 0;
  uint16_t targetSteps_ = 0;
  uint16_t stageSteps_ = 0;
  uint32_t nextPulseUs_ = 0;
  uint32_t homeStableSinceUs_ = 0;
  bool directionHigh_ = false;
  bool releasingHome_ = false;
};

}  // namespace labforge
