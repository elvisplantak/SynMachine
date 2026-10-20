#pragma once

#include <stdint.h>

namespace labforge {

constexpr uint32_t kSfMixerStepIntervalUs = 2000;
constexpr uint16_t kSfMixerStepHighUs = 20;
constexpr uint16_t kSfMixerDirectionSetupUs = 5;
constexpr bool kSfMixerTestedDirectionHigh = false;

class SfMixerMotionIo {
 public:
  virtual ~SfMixerMotionIo() = default;
  virtual void writeDirection(bool high) = 0;
  virtual void writeStep(bool high) = 0;
  virtual void pulseStep(uint16_t highUs) = 0;
};

enum class SfMixerPrepareResult : uint8_t { READY, BUSY };
enum class SfMixerCommandResult : uint8_t { NONE, COMPLETED };

class SfMixerMotionController {
 public:
  explicit SfMixerMotionController(SfMixerMotionIo& io);

  SfMixerPrepareResult prepareSetRunning(bool running);
  bool start(uint32_t nowUs);
  SfMixerCommandResult update(uint32_t nowUs);
  bool abort();
  void forceStop();

  bool running() const;
  bool commandPending() const;

 private:
  static bool due(uint32_t nowUs, uint32_t targetUs);

  SfMixerMotionIo& io_;
  uint32_t nextPulseUs_ = 0;
  bool running_ = false;
  bool commandPrepared_ = false;
  bool preparedRunning_ = false;
  bool commandCompletionPending_ = false;
  bool completionRequiresPulse_ = false;
  bool commandChangedRunningState_ = false;
};

static_assert(kSfMixerStepHighUs < kSfMixerStepIntervalUs,
              "SF mixer STEP high time must be shorter than its interval");

}  // namespace labforge
