#include "actuator/SfMixerMotionController.h"

namespace labforge {

SfMixerMotionController::SfMixerMotionController(SfMixerMotionIo& io)
    : io_(io) {}

SfMixerPrepareResult SfMixerMotionController::prepareSetRunning(bool running) {
  if (commandPrepared_ || commandCompletionPending_)
    return SfMixerPrepareResult::BUSY;
  preparedRunning_ = running;
  commandPrepared_ = true;
  return SfMixerPrepareResult::READY;
}

bool SfMixerMotionController::start(uint32_t nowUs) {
  if (!commandPrepared_) return false;
  commandPrepared_ = false;
  commandChangedRunningState_ = preparedRunning_ != running_;
  if (preparedRunning_) {
    if (!running_) {
      io_.writeDirection(kSfMixerTestedDirectionHigh);
      io_.writeStep(false);
      running_ = true;
      nextPulseUs_ = nowUs + kSfMixerDirectionSetupUs;
      completionRequiresPulse_ = true;
    }
  } else {
    io_.writeStep(false);
    running_ = false;
  }
  commandCompletionPending_ = true;
  return true;
}

SfMixerCommandResult SfMixerMotionController::update(uint32_t nowUs) {
  bool emittedPulse = false;
  if (running_ && due(nowUs, nextPulseUs_)) {
    io_.pulseStep(kSfMixerStepHighUs);
    nextPulseUs_ = nowUs + kSfMixerStepIntervalUs;
    emittedPulse = true;
  }
  if (!commandCompletionPending_) return SfMixerCommandResult::NONE;
  if (completionRequiresPulse_ && !emittedPulse)
    return SfMixerCommandResult::NONE;
  commandCompletionPending_ = false;
  completionRequiresPulse_ = false;
  commandChangedRunningState_ = false;
  return SfMixerCommandResult::COMPLETED;
}

bool SfMixerMotionController::abort() {
  if (!commandPrepared_ && !commandCompletionPending_) return false;
  if (commandCompletionPending_ && commandChangedRunningState_ && running_) {
    io_.writeStep(false);
    running_ = false;
  }
  commandPrepared_ = false;
  commandCompletionPending_ = false;
  completionRequiresPulse_ = false;
  commandChangedRunningState_ = false;
  return true;
}

void SfMixerMotionController::forceStop() {
  io_.writeStep(false);
  running_ = false;
  commandPrepared_ = false;
  commandCompletionPending_ = false;
  completionRequiresPulse_ = false;
  commandChangedRunningState_ = false;
}

bool SfMixerMotionController::running() const { return running_; }

bool SfMixerMotionController::commandPending() const {
  return commandPrepared_ || commandCompletionPending_;
}

bool SfMixerMotionController::due(uint32_t nowUs, uint32_t targetUs) {
  return static_cast<int32_t>(nowUs - targetUs) >= 0;
}

}  // namespace labforge
