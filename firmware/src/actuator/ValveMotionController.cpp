#include "actuator/ValveMotionController.h"

namespace labforge {
namespace {

bool timeReached(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}

bool validTarget(uint16_t degrees) {
  return degrees == 0 || degrees == 90 || degrees == 180;
}

}  // namespace

ValveMotionController::ValveMotionController(ValveMotionIo& io,
                                             bool directionTowardHomeHigh)
    : io_(io), directionTowardHomeHigh_(directionTowardHomeHigh) {}

ValvePrepareResult ValveMotionController::prepareHome() {
  if (busy()) return ValvePrepareResult::BUSY;
  state_ = ValveMotionState::PREPARED_HOME;
  return ValvePrepareResult::READY;
}

ValvePrepareResult ValveMotionController::prepareSetPosition(
    uint16_t targetDegrees) {
  if (busy()) return ValvePrepareResult::BUSY;
  if (!validTarget(targetDegrees)) return ValvePrepareResult::INVALID_TARGET;
  if (targetDegrees == 0) return prepareHome();
  if (trust_ != ValvePositionTrust::TRUSTED)
    return ValvePrepareResult::POSITION_UNTRUSTED;
  const uint16_t targetSteps =
      static_cast<uint16_t>((targetDegrees / 90) * kValveStepsPer90Degrees);
  if (targetSteps == positionSteps_)
    return ValvePrepareResult::TARGET_ALREADY_REACHED;
  targetSteps_ = targetSteps;
  state_ = ValveMotionState::PREPARED_MOVE;
  return ValvePrepareResult::READY;
}

bool ValveMotionController::start(uint32_t nowUs) {
  if (state_ == ValveMotionState::PREPARED_HOME) {
    if (trust_ == ValvePositionTrust::TRUSTED && positionSteps_ == 0) {
      pauseForHome(nowUs, io_.homeActive()
                              ? ValveMotionState::CONFIRMING_HOME
                              : ValveMotionState::CONFIRMING_TRUSTED_HOME);
      return true;
    }
    trust_ = ValvePositionTrust::UNTRUSTED;
    if (io_.homeActive()) {
      pauseForHome(nowUs, ValveMotionState::CONFIRMING_HOME);
    } else {
      beginMotion(ValveMotionState::SEARCHING_HOME,
                  directionTowardHomeHigh_, nowUs);
    }
    return true;
  }
  if (state_ != ValveMotionState::PREPARED_MOVE) return false;
  const bool movingAway = targetSteps_ > positionSteps_;
  releasingHome_ = movingAway && positionSteps_ == 0 && io_.homeActive();
  beginMotion(ValveMotionState::MOVING,
              movingAway ? !directionTowardHomeHigh_
                         : directionTowardHomeHigh_,
              nowUs);
  return true;
}

ValveMotionResult ValveMotionController::update(uint32_t nowUs) {
  if (state_ == ValveMotionState::IDLE ||
      state_ == ValveMotionState::PREPARED_HOME ||
      state_ == ValveMotionState::PREPARED_MOVE)
    return ValveMotionResult::NONE;

  if (state_ == ValveMotionState::CONFIRMING_HOME) {
    if (!io_.homeActive()) {
      if (trust_ == ValvePositionTrust::TRUSTED && positionSteps_ == 0) {
        pauseForHome(nowUs, ValveMotionState::CONFIRMING_TRUSTED_HOME);
      } else {
        beginMotion(ValveMotionState::SEARCHING_HOME,
                    directionTowardHomeHigh_, nowUs);
      }
    } else if (timeReached(nowUs, homeStableSinceUs_ + kValveHomeStableUs)) {
      positionSteps_ = 0;
      trust_ = ValvePositionTrust::TRUSTED;
      return finish(ValveMotionResult::COMPLETED);
    }
    return ValveMotionResult::NONE;
  }

  if (state_ == ValveMotionState::CONFIRMING_TRUSTED_HOME) {
    if (io_.homeActive()) {
      pauseForHome(nowUs, ValveMotionState::CONFIRMING_HOME);
    } else if (timeReached(nowUs, homeStableSinceUs_ + kValveHomeStableUs)) {
      trust_ = ValvePositionTrust::UNTRUSTED;
      return finish(ValveMotionResult::HOME_SWITCH_UNEXPECTED);
    }
    return ValveMotionResult::NONE;
  }

  if (state_ == ValveMotionState::CONFIRMING_HOME_RELEASE) {
    if (io_.homeActive()) {
      releasingHome_ = true;
      nextPulseUs_ = nowUs + kValveStepIntervalUs;
      state_ = ValveMotionState::MOVING;
    } else if (timeReached(nowUs, homeStableSinceUs_ + kValveHomeStableUs)) {
      releasingHome_ = false;
      nextPulseUs_ = nowUs + kValveStepIntervalUs;
      state_ = ValveMotionState::MOVING;
    }
    return ValveMotionResult::NONE;
  }

  if (state_ == ValveMotionState::CONFIRMING_UNEXPECTED_HOME) {
    if (!io_.homeActive()) {
      nextPulseUs_ = nowUs + kValveStepIntervalUs;
      state_ = ValveMotionState::MOVING;
    } else if (timeReached(nowUs, homeStableSinceUs_ + kValveHomeStableUs)) {
      trust_ = ValvePositionTrust::UNTRUSTED;
      return finish(ValveMotionResult::HOME_SWITCH_UNEXPECTED);
    }
    return ValveMotionResult::NONE;
  }

  if (state_ == ValveMotionState::SEARCHING_HOME && io_.homeActive()) {
    pauseForHome(nowUs, ValveMotionState::CONFIRMING_HOME);
    return ValveMotionResult::NONE;
  }

  if (state_ == ValveMotionState::MOVING) {
    if (releasingHome_) {
      if (!io_.homeActive()) {
        pauseForHome(nowUs, ValveMotionState::CONFIRMING_HOME_RELEASE);
        return ValveMotionResult::NONE;
      } else if (stageSteps_ >= kValveStepsPer90Degrees) {
        trust_ = ValvePositionTrust::UNTRUSTED;
        return finish(ValveMotionResult::HOME_SWITCH_STUCK);
      }
    } else if (io_.homeActive()) {
      pauseForHome(nowUs, ValveMotionState::CONFIRMING_UNEXPECTED_HOME);
      return ValveMotionResult::NONE;
    }
  }

  if (!pulseDue(nowUs)) return ValveMotionResult::NONE;
  emitPulse(nowUs);
  if (state_ == ValveMotionState::SEARCHING_HOME) {
    if (stageSteps_ >= kValveMaximumSearchSteps)
      return finish(ValveMotionResult::MOTION_TIMEOUT);
    return ValveMotionResult::NONE;
  }

  if (directionHigh_ == directionTowardHomeHigh_)
    --positionSteps_;
  else
    ++positionSteps_;
  if (positionSteps_ == targetSteps_)
    return finish(ValveMotionResult::COMPLETED);
  return ValveMotionResult::NONE;
}

bool ValveMotionController::abort() {
  if (state_ == ValveMotionState::IDLE) return false;
  const bool started = state_ != ValveMotionState::PREPARED_HOME &&
                       state_ != ValveMotionState::PREPARED_MOVE;
  io_.writeStep(false);
  state_ = ValveMotionState::IDLE;
  releasingHome_ = false;
  if (started) trust_ = ValvePositionTrust::UNTRUSTED;
  return true;
}

ValveMotionState ValveMotionController::state() const { return state_; }
ValvePositionTrust ValveMotionController::positionTrust() const { return trust_; }
uint16_t ValveMotionController::positionDegrees() const {
  return static_cast<uint16_t>((positionSteps_ * 90U) /
                               kValveStepsPer90Degrees);
}
bool ValveMotionController::busy() const {
  return state_ != ValveMotionState::IDLE;
}

void ValveMotionController::beginMotion(ValveMotionState state,
                                        bool directionHigh,
                                        uint32_t nowUs) {
  state_ = state;
  directionHigh_ = directionHigh;
  stageSteps_ = 0;
  nextPulseUs_ = nowUs + kValveDirectionSetupUs;
  io_.writeDirection(directionHigh);
}

void ValveMotionController::pauseForHome(uint32_t nowUs,
                                         ValveMotionState state) {
  io_.writeStep(false);
  state_ = state;
  homeStableSinceUs_ = nowUs;
}

bool ValveMotionController::pulseDue(uint32_t nowUs) const {
  return timeReached(nowUs, nextPulseUs_);
}

void ValveMotionController::emitPulse(uint32_t nowUs) {
  io_.pulseStep(kValveStepHighUs);
  ++stageSteps_;
  nextPulseUs_ = nowUs + kValveStepIntervalUs;
}

ValveMotionResult ValveMotionController::finish(ValveMotionResult result) {
  io_.writeStep(false);
  state_ = ValveMotionState::IDLE;
  releasingHome_ = false;
  return result;
}

}  // namespace labforge
