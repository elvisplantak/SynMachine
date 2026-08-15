#include "actuator/ColumnBottomValveMotionController.h"

namespace labforge {
namespace {

constexpr bool kDirectionTowardHomeHigh = false;

bool timeReached(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}

uint32_t targetStepsFor(uint16_t degrees) {
  if (degrees == 4) return kColumnValveClosedSteps;
  if (degrees == 94) return kColumnValveOpenSteps;
  return UINT32_MAX;
}

}  // namespace

ColumnBottomValveMotionController::ColumnBottomValveMotionController(
    ValveMotionIo& io)
    : io_(io) {}

ColumnValvePrepareResult ColumnBottomValveMotionController::prepareHome() {
  if (busy()) return ColumnValvePrepareResult::BUSY;
  state_ = ColumnValveMotionState::PREPARED_HOME;
  return ColumnValvePrepareResult::READY;
}

ColumnValvePrepareResult
ColumnBottomValveMotionController::prepareSetPosition(uint16_t targetDegrees) {
  if (busy()) return ColumnValvePrepareResult::BUSY;
  const uint32_t target = targetStepsFor(targetDegrees);
  if (target == UINT32_MAX) return ColumnValvePrepareResult::INVALID_TARGET;
  if (trust_ != ColumnValvePositionTrust::TRUSTED)
    return ColumnValvePrepareResult::POSITION_UNTRUSTED;
  if (target == positionSteps_)
    return ColumnValvePrepareResult::TARGET_ALREADY_REACHED;
  targetSteps_ = target;
  state_ = ColumnValveMotionState::PREPARED_MOVE;
  return ColumnValvePrepareResult::READY;
}

bool ColumnBottomValveMotionController::start(uint32_t nowUs) {
  if (state_ == ColumnValveMotionState::PREPARED_HOME) {
    if (trust_ == ColumnValvePositionTrust::TRUSTED && positionSteps_ == 0) {
      pauseForHome(nowUs, io_.homeActive()
                              ? ColumnValveMotionState::CONFIRMING_HOME
                              : ColumnValveMotionState::CONFIRMING_TRUSTED_HOME);
      return true;
    }
    trust_ = ColumnValvePositionTrust::UNTRUSTED;
    if (io_.homeActive()) {
      pauseForHome(nowUs, ColumnValveMotionState::CONFIRMING_HOME);
    } else {
      beginMotion(ColumnValveMotionState::SEARCHING_HOME,
                  kDirectionTowardHomeHigh, nowUs);
    }
    return true;
  }
  if (state_ != ColumnValveMotionState::PREPARED_MOVE) return false;
  const bool movingAway = targetSteps_ > positionSteps_;
  releasingHome_ = movingAway && positionSteps_ == 0 && io_.homeActive();
  beginMotion(ColumnValveMotionState::MOVING,
              movingAway ? !kDirectionTowardHomeHigh
                         : kDirectionTowardHomeHigh,
              nowUs);
  return true;
}

ColumnValveMotionResult ColumnBottomValveMotionController::update(
    uint32_t nowUs) {
  if (state_ == ColumnValveMotionState::IDLE ||
      state_ == ColumnValveMotionState::PREPARED_HOME ||
      state_ == ColumnValveMotionState::PREPARED_MOVE)
    return ColumnValveMotionResult::NONE;

  if (state_ == ColumnValveMotionState::CONFIRMING_HOME) {
    const bool homeActive = io_.homeActive();
    if (homeActive != homeCandidateActive_) {
      homeCandidateActive_ = homeActive;
      homeStableSinceUs_ = nowUs;
      return ColumnValveMotionResult::NONE;
    }
    if (!timeReached(nowUs, homeStableSinceUs_ + kColumnValveHomeStableUs))
      return ColumnValveMotionResult::NONE;
    if (homeActive) {
      positionSteps_ = 0;
      trust_ = ColumnValvePositionTrust::TRUSTED;
      return finish(ColumnValveMotionResult::COMPLETED);
    }
    if (trust_ == ColumnValvePositionTrust::TRUSTED && positionSteps_ == 0) {
      trust_ = ColumnValvePositionTrust::UNTRUSTED;
      return finish(ColumnValveMotionResult::HOME_SWITCH_UNEXPECTED);
    }
    beginMotion(ColumnValveMotionState::SEARCHING_HOME,
                kDirectionTowardHomeHigh, nowUs);
    return ColumnValveMotionResult::NONE;
  }

  if (state_ == ColumnValveMotionState::CONFIRMING_TRUSTED_HOME) {
    if (io_.homeActive()) {
      pauseForHome(nowUs, ColumnValveMotionState::CONFIRMING_HOME);
    } else if (timeReached(nowUs,
                           homeStableSinceUs_ + kColumnValveHomeStableUs)) {
      trust_ = ColumnValvePositionTrust::UNTRUSTED;
      return finish(ColumnValveMotionResult::HOME_SWITCH_UNEXPECTED);
    }
    return ColumnValveMotionResult::NONE;
  }

  if (state_ == ColumnValveMotionState::CONFIRMING_HOME_RELEASE) {
    const bool homeActive = io_.homeActive();
    if (homeActive != homeCandidateActive_) {
      homeCandidateActive_ = homeActive;
      homeStableSinceUs_ = nowUs;
      return ColumnValveMotionResult::NONE;
    }
    if (!timeReached(nowUs, homeStableSinceUs_ + kColumnValveHomeStableUs))
      return ColumnValveMotionResult::NONE;
    if (!homeActive) {
      releasingHome_ = false;
      releaseTravelExhausted_ = false;
      if (positionSteps_ == targetSteps_)
        return finish(ColumnValveMotionResult::COMPLETED);
      nextPulseUs_ = nowUs + kColumnValveStepIntervalUs;
      state_ = ColumnValveMotionState::MOVING;
    } else if (releaseTravelExhausted_) {
      trust_ = ColumnValvePositionTrust::UNTRUSTED;
      return finish(ColumnValveMotionResult::HOME_SWITCH_STUCK);
    } else {
      nextPulseUs_ = nowUs + kColumnValveStepIntervalUs;
      state_ = ColumnValveMotionState::MOVING;
    }
    return ColumnValveMotionResult::NONE;
  }

  if (state_ == ColumnValveMotionState::CONFIRMING_UNEXPECTED_HOME) {
    if (!io_.homeActive()) {
      nextPulseUs_ = nowUs + kColumnValveStepIntervalUs;
      state_ = ColumnValveMotionState::MOVING;
    } else if (timeReached(nowUs,
                           homeStableSinceUs_ + kColumnValveHomeStableUs)) {
      trust_ = ColumnValvePositionTrust::UNTRUSTED;
      return finish(ColumnValveMotionResult::HOME_SWITCH_UNEXPECTED);
    }
    return ColumnValveMotionResult::NONE;
  }

  if (state_ == ColumnValveMotionState::SEARCHING_HOME && io_.homeActive()) {
    pauseForHome(nowUs, ColumnValveMotionState::CONFIRMING_HOME);
    return ColumnValveMotionResult::NONE;
  }

  if (state_ == ColumnValveMotionState::MOVING) {
    if (releasingHome_) {
      if (!io_.homeActive()) {
        pauseForHome(nowUs, ColumnValveMotionState::CONFIRMING_HOME_RELEASE);
        return ColumnValveMotionResult::NONE;
      } else if (stageSteps_ >= kColumnValveClosedSteps) {
        trust_ = ColumnValvePositionTrust::UNTRUSTED;
        return finish(ColumnValveMotionResult::HOME_SWITCH_STUCK);
      }
    } else if (io_.homeActive()) {
      pauseForHome(nowUs,
                   ColumnValveMotionState::CONFIRMING_UNEXPECTED_HOME);
      return ColumnValveMotionResult::NONE;
    }
  }

  if (!pulseDue(nowUs)) return ColumnValveMotionResult::NONE;
  emitPulse(nowUs);
  if (state_ == ColumnValveMotionState::SEARCHING_HOME) {
    if (stageSteps_ >= kColumnValveMaximumSearchSteps)
      return finish(ColumnValveMotionResult::MOTION_TIMEOUT);
    return ColumnValveMotionResult::NONE;
  }

  if (directionHigh_ == kDirectionTowardHomeHigh)
    --positionSteps_;
  else
    ++positionSteps_;
  if (releasingHome_ && stageSteps_ >= kColumnValveClosedSteps) {
    releaseTravelExhausted_ = true;
    pauseForHome(nowUs, ColumnValveMotionState::CONFIRMING_HOME_RELEASE);
    return ColumnValveMotionResult::NONE;
  }
  if (positionSteps_ == targetSteps_)
    return finish(ColumnValveMotionResult::COMPLETED);
  return ColumnValveMotionResult::NONE;
}

bool ColumnBottomValveMotionController::abort() {
  if (state_ == ColumnValveMotionState::IDLE) return false;
  const bool started = state_ != ColumnValveMotionState::PREPARED_HOME &&
                       state_ != ColumnValveMotionState::PREPARED_MOVE;
  io_.writeStep(false);
  state_ = ColumnValveMotionState::IDLE;
  releasingHome_ = false;
  releaseTravelExhausted_ = false;
  if (started) trust_ = ColumnValvePositionTrust::UNTRUSTED;
  return true;
}

ColumnValveMotionState ColumnBottomValveMotionController::state() const {
  return state_;
}
ColumnValvePositionTrust
ColumnBottomValveMotionController::positionTrust() const {
  return trust_;
}
uint32_t ColumnBottomValveMotionController::positionSteps() const {
  return positionSteps_;
}
uint32_t ColumnBottomValveMotionController::stageSteps() const {
  return stageSteps_;
}
bool ColumnBottomValveMotionController::homeActive() const {
  return io_.homeActive();
}
bool ColumnBottomValveMotionController::busy() const {
  return state_ != ColumnValveMotionState::IDLE;
}

void ColumnBottomValveMotionController::beginMotion(
    ColumnValveMotionState state, bool directionHigh, uint32_t nowUs) {
  state_ = state;
  directionHigh_ = directionHigh;
  stageSteps_ = 0;
  releaseTravelExhausted_ = false;
  nextPulseUs_ = nowUs + kColumnValveDirectionSetupUs;
  io_.writeDirection(directionHigh);
}

void ColumnBottomValveMotionController::pauseForHome(
    uint32_t nowUs, ColumnValveMotionState state) {
  io_.writeStep(false);
  state_ = state;
  homeStableSinceUs_ = nowUs;
  homeCandidateActive_ = io_.homeActive();
}

bool ColumnBottomValveMotionController::pulseDue(uint32_t nowUs) const {
  return timeReached(nowUs, nextPulseUs_);
}

void ColumnBottomValveMotionController::emitPulse(uint32_t nowUs) {
  io_.pulseStep(kColumnValveStepHighUs);
  ++stageSteps_;
  nextPulseUs_ = nowUs + kColumnValveStepIntervalUs;
}

ColumnValveMotionResult ColumnBottomValveMotionController::finish(
    ColumnValveMotionResult result) {
  io_.writeStep(false);
  state_ = ColumnValveMotionState::IDLE;
  releasingHome_ = false;
  releaseTravelExhausted_ = false;
  return result;
}

}  // namespace labforge
