#include "actuator/P1MotionController.h"

namespace labforge {
namespace {

constexpr bool kDirectionTowardHomeHigh = false;
constexpr bool kDirectionAwayFromHomeHigh = true;

bool timeReached(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}

}  // namespace

P1MotionController::P1MotionController(P1MotionIo& io) : io_(io) {}

P1PrepareResult P1MotionController::prepareHome() {
  if (busy()) return P1PrepareResult::BUSY;
  state_ = P1MotionState::PREPARED_HOME;
  return P1PrepareResult::READY;
}

P1PrepareResult P1MotionController::prepareMoveAbsolute(uint16_t targetSteps) {
  if (busy()) return P1PrepareResult::BUSY;
  if (targetSteps > kP1MaximumAbsoluteSteps)
    return P1PrepareResult::INVALID_TARGET;
  if (trust_ != P1PositionTrust::TRUSTED)
    return P1PrepareResult::POSITION_UNTRUSTED;
  if (targetSteps == 0) return P1PrepareResult::TARGET_REQUIRES_HOME;
  if (targetSteps == positionSteps_)
    return P1PrepareResult::TARGET_ALREADY_REACHED;
  if (io_.homeActive() && positionSteps_ != 0)
    return P1PrepareResult::HOME_SWITCH_ACTIVE;
  targetSteps_ = targetSteps;
  state_ = P1MotionState::PREPARED_MOVE;
  return P1PrepareResult::READY;
}

bool P1MotionController::start(uint32_t nowUs) {
  if (state_ == P1MotionState::PREPARED_HOME) {
    const bool trustedAtHome =
        trust_ == P1PositionTrust::TRUSTED && positionSteps_ == 0;
    trust_ = P1PositionTrust::UNTRUSTED;
    if (trustedAtHome) {
      beginStage(P1MotionState::RELEASING_HOME,
                 kDirectionAwayFromHomeHigh, nowUs);
      homeStableLevel_ = io_.homeActive();
      pauseForHomeStability(P1MotionState::CONFIRMING_TRUSTED_HOME, nowUs);
    } else if (io_.homeActive()) {
      beginStage(P1MotionState::SEARCHING_HOME,
                 kDirectionTowardHomeHigh, nowUs);
      pauseForHomeStability(P1MotionState::CONFIRMING_HOME_ACTIVE, nowUs);
    } else {
      beginStage(P1MotionState::SEARCHING_HOME,
                 kDirectionTowardHomeHigh, nowUs);
    }
    return true;
  }
  if (state_ == P1MotionState::PREPARED_MOVE) {
    const bool movingAway = targetSteps_ > positionSteps_;
    releasingHomeDuringMove_ =
        movingAway && positionSteps_ == 0 && io_.homeActive();
    beginStage(P1MotionState::MOVING, movingAway, nowUs);
    return true;
  }
  return false;
}

P1MotionResult P1MotionController::update(uint32_t nowUs) {
  if (state_ == P1MotionState::IDLE ||
      state_ == P1MotionState::PREPARED_HOME ||
      state_ == P1MotionState::PREPARED_MOVE) {
    return P1MotionResult::NONE;
  }

  if (state_ == P1MotionState::CONFIRMING_TRUSTED_HOME) {
    const bool homeActive = io_.homeActive();
    if (homeActive != homeStableLevel_) {
      homeStableLevel_ = homeActive;
      homeStableSinceUs_ = nowUs;
    } else if (timeReached(nowUs, homeStableSinceUs_ + kP1HomeStableUs)) {
      if (!homeActive)
        return finish(P1MotionResult::HOME_SWITCH_UNEXPECTED);
      resumePulses(nowUs);
      state_ = P1MotionState::RELEASING_HOME;
    }
    return P1MotionResult::NONE;
  }

  if (state_ == P1MotionState::WAITING_FINAL_HOME_SIGNAL) {
    // The final electrical pulse can precede mechanical switch activation.
    // Hold STEP inactive; a late input never authorizes another search pulse.
    // Reuse the existing 30 ms interval as a bounded software arrival budget.
    if (timeReached(nowUs, homeStableSinceUs_ + kP1HomeStableUs))
      return finish(P1MotionResult::MOTION_TIMEOUT);
    if (io_.homeActive())
      pauseForHomeStability(P1MotionState::CONFIRMING_HOME_ACTIVE, nowUs);
    return P1MotionResult::NONE;
  }

  if (state_ == P1MotionState::CONFIRMING_HOME_ACTIVE) {
    if (!io_.homeActive()) {
      if (stageSteps_ >= kP1MaximumAbsoluteSteps)
        return finish(P1MotionResult::MOTION_TIMEOUT);
      resumePulses(nowUs);
      state_ = P1MotionState::SEARCHING_HOME;
    } else if (timeReached(nowUs, homeStableSinceUs_ + kP1HomeStableUs)) {
      positionSteps_ = 0;
      trust_ = P1PositionTrust::TRUSTED;
      return finish(P1MotionResult::COMPLETED);
    }
    return P1MotionResult::NONE;
  }

  if (state_ == P1MotionState::CONFIRMING_HOME_RELEASE) {
    if (io_.homeActive()) {
      resumePulses(nowUs);
      state_ = P1MotionState::RELEASING_HOME;
    } else if (timeReached(nowUs, homeStableSinceUs_ + kP1HomeStableUs)) {
      beginStage(P1MotionState::SEARCHING_HOME,
                 kDirectionTowardHomeHigh, nowUs);
    }
    return P1MotionResult::NONE;
  }

  if (state_ == P1MotionState::CONFIRMING_MOVE_RELEASE) {
    if (io_.homeActive()) {
      resumePulses(nowUs);
      state_ = P1MotionState::MOVING;
    } else if (timeReached(nowUs, homeStableSinceUs_ + kP1HomeStableUs)) {
      releasingHomeDuringMove_ = false;
      if (positionSteps_ == targetSteps_)
        return finish(P1MotionResult::COMPLETED);
      resumePulses(nowUs);
      state_ = P1MotionState::MOVING;
    }
    return P1MotionResult::NONE;
  }

  if (state_ == P1MotionState::CONFIRMING_UNEXPECTED_HOME) {
    if (!io_.homeActive()) {
      resumePulses(nowUs);
      state_ = P1MotionState::MOVING;
    } else if (timeReached(nowUs, homeStableSinceUs_ + kP1HomeStableUs)) {
      trust_ = P1PositionTrust::UNTRUSTED;
      return finish(P1MotionResult::HOME_SWITCH_UNEXPECTED);
    }
    return P1MotionResult::NONE;
  }

  if (state_ == P1MotionState::SEARCHING_HOME && io_.homeActive()) {
    pauseForHomeStability(P1MotionState::CONFIRMING_HOME_ACTIVE, nowUs);
    return P1MotionResult::NONE;
  }

  if (state_ == P1MotionState::RELEASING_HOME) {
    if (!io_.homeActive()) {
      pauseForHomeStability(P1MotionState::CONFIRMING_HOME_RELEASE, nowUs);
    } else if (stageSteps_ >= kP1HomeReleaseMaximumSteps) {
      return finish(P1MotionResult::HOME_SWITCH_STUCK);
    }
  } else if (state_ == P1MotionState::MOVING) {
    if (releasingHomeDuringMove_) {
      if (!io_.homeActive()) {
        pauseForHomeStability(P1MotionState::CONFIRMING_MOVE_RELEASE, nowUs);
        return P1MotionResult::NONE;
      }
      if (positionSteps_ == targetSteps_) {
        trust_ = P1PositionTrust::UNTRUSTED;
        return finish(P1MotionResult::HOME_SWITCH_STUCK);
      }
    } else if (io_.homeActive()) {
      pauseForHomeStability(P1MotionState::CONFIRMING_UNEXPECTED_HOME, nowUs);
      return P1MotionResult::NONE;
    }
  }

  if (!pulseDue(nowUs)) return P1MotionResult::NONE;

  emitPulse(nowUs);
  if (state_ == P1MotionState::MOVING) {
    if (directionHigh_) {
      ++positionSteps_;
    } else {
      --positionSteps_;
    }
  }

  if (state_ == P1MotionState::RELEASING_HOME &&
      stageSteps_ >= kP1HomeReleaseMaximumSteps)
    return finish(P1MotionResult::HOME_SWITCH_STUCK);
  if (state_ == P1MotionState::SEARCHING_HOME &&
      stageSteps_ >= kP1MaximumAbsoluteSteps) {
    if (io_.homeActive()) {
      pauseForHomeStability(P1MotionState::CONFIRMING_HOME_ACTIVE, nowUs);
      return P1MotionResult::NONE;
    }
    pauseForHomeStability(P1MotionState::WAITING_FINAL_HOME_SIGNAL, nowUs);
    return P1MotionResult::NONE;
  }
  if (state_ == P1MotionState::MOVING) {
    if (releasingHomeDuringMove_ && positionSteps_ == targetSteps_) {
      trust_ = P1PositionTrust::UNTRUSTED;
      return finish(P1MotionResult::HOME_SWITCH_STUCK);
    }
    if (!releasingHomeDuringMove_ && positionSteps_ == targetSteps_)
      return finish(P1MotionResult::COMPLETED);
  }
  return P1MotionResult::NONE;
}

bool P1MotionController::abort() {
  if (state_ == P1MotionState::IDLE) return false;

  const bool executionStarted =
      state_ != P1MotionState::PREPARED_HOME &&
      state_ != P1MotionState::PREPARED_MOVE;
  if (!executionStarted) {
    state_ = P1MotionState::IDLE;
    releasingHomeDuringMove_ = false;
    return true;
  }
  io_.writeStep(false);
  state_ = P1MotionState::IDLE;
  releasingHomeDuringMove_ = false;
  trust_ = P1PositionTrust::UNTRUSTED;
  return true;
}

P1MotionState P1MotionController::state() const { return state_; }

P1PositionTrust P1MotionController::positionTrust() const { return trust_; }

uint16_t P1MotionController::positionSteps() const { return positionSteps_; }

bool P1MotionController::busy() const {
  return state_ != P1MotionState::IDLE;
}

void P1MotionController::beginStage(P1MotionState state, bool directionHigh,
                                    uint32_t nowUs) {
  state_ = state;
  directionHigh_ = directionHigh;
  stageSteps_ = 0;
  nextPulseUs_ = nowUs + kP1DirectionSetupUs;
  io_.writeDirection(directionHigh);
}

bool P1MotionController::pulseDue(uint32_t nowUs) const {
  return timeReached(nowUs, nextPulseUs_);
}

void P1MotionController::emitPulse(uint32_t nowUs) {
  io_.pulseStep(kP1StepHighUs);
  ++stageSteps_;
  nextPulseUs_ = nowUs + kP1StepIntervalUs;
}

void P1MotionController::pauseForHomeStability(P1MotionState state,
                                               uint32_t nowUs) {
  io_.writeStep(false);
  state_ = state;
  homeStableSinceUs_ = nowUs;
}

void P1MotionController::resumePulses(uint32_t nowUs) {
  nextPulseUs_ = nowUs + kP1StepIntervalUs;
}

P1MotionResult P1MotionController::finish(P1MotionResult result) {
  io_.writeStep(false);
  state_ = P1MotionState::IDLE;
  releasingHomeDuringMove_ = false;
  return result;
}

}  // namespace labforge
