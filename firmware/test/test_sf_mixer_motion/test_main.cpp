#include <unity.h>

#include <vector>

#include "actuator/SfMixerMotionController.h"

using namespace labforge;

namespace {

class FakeIo : public SfMixerMotionIo {
 public:
  void writeDirection(bool high) override {
    direction = high;
    ++directionWrites;
  }
  void writeStep(bool high) override {
    step = high;
    ++stepWrites;
  }
  void pulseStep(uint16_t highUs) override {
    step = false;
    pulseWidths.push_back(highUs);
  }

  bool direction = true;
  bool step = false;
  uint16_t directionWrites = 0;
  uint16_t stepWrites = 0;
  std::vector<uint16_t> pulseWidths;
};

void startMixer(SfMixerMotionController& controller, uint32_t nowUs = 100) {
  TEST_ASSERT_EQUAL(SfMixerPrepareResult::READY,
                    controller.prepareSetRunning(true));
  TEST_ASSERT_TRUE(controller.start(nowUs));
  TEST_ASSERT_EQUAL(SfMixerCommandResult::NONE,
                    controller.update(nowUs + kSfMixerDirectionSetupUs - 1));
  TEST_ASSERT_EQUAL(SfMixerCommandResult::COMPLETED,
                    controller.update(nowUs + kSfMixerDirectionSetupUs));
}

void test_start_waits_for_direction_setup_and_uses_confirmed_profile() {
  FakeIo io;
  SfMixerMotionController controller(io);
  TEST_ASSERT_FALSE(controller.running());
  TEST_ASSERT_EQUAL(SfMixerPrepareResult::READY,
                    controller.prepareSetRunning(true));
  TEST_ASSERT_EQUAL_UINT16(0, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT16(0, io.pulseWidths.size());
  TEST_ASSERT_TRUE(controller.start(100));
  TEST_ASSERT_TRUE(controller.running());
  TEST_ASSERT_EQUAL_UINT16(1, io.directionWrites);
  TEST_ASSERT_FALSE(io.direction);
  TEST_ASSERT_EQUAL_UINT16(0, io.pulseWidths.size());
  TEST_ASSERT_EQUAL(SfMixerCommandResult::NONE, controller.update(104));
  TEST_ASSERT_EQUAL(SfMixerCommandResult::COMPLETED, controller.update(105));
  TEST_ASSERT_EQUAL_UINT16(1, io.pulseWidths.size());
  TEST_ASSERT_EQUAL_UINT16(kSfMixerStepHighUs, io.pulseWidths[0]);
}

void test_trial_rate_uses_1667_us_without_early_or_catch_up_pulses() {
  FakeIo io;
  SfMixerMotionController controller(io);
  startMixer(controller);
  TEST_ASSERT_EQUAL_UINT32(1667, kSfMixerStepIntervalUs);
  controller.update(105 + 1666);
  TEST_ASSERT_EQUAL_UINT16(1, io.pulseWidths.size());
  controller.update(105 + 1667);
  TEST_ASSERT_EQUAL_UINT16(2, io.pulseWidths.size());
  controller.update(105 + 1667);
  TEST_ASSERT_EQUAL_UINT16(2, io.pulseWidths.size());
}

void test_continuous_update_emits_one_pulse_without_catch_up() {
  FakeIo io;
  SfMixerMotionController controller(io);
  startMixer(controller);
  controller.update(1000000);
  TEST_ASSERT_EQUAL_UINT16(2, io.pulseWidths.size());
  controller.update(1000000);
  TEST_ASSERT_EQUAL_UINT16(2, io.pulseWidths.size());
  controller.update(1000000 + kSfMixerStepIntervalUs);
  TEST_ASSERT_EQUAL_UINT16(3, io.pulseWidths.size());
}

void test_set_state_is_idempotent_and_stop_prevents_more_pulses() {
  FakeIo io;
  SfMixerMotionController controller(io);
  startMixer(controller);
  const size_t pulses = io.pulseWidths.size();
  TEST_ASSERT_EQUAL(SfMixerPrepareResult::READY,
                    controller.prepareSetRunning(true));
  TEST_ASSERT_TRUE(controller.start(200));
  TEST_ASSERT_EQUAL(SfMixerCommandResult::COMPLETED, controller.update(200));
  TEST_ASSERT_EQUAL_UINT16(pulses, io.pulseWidths.size());

  TEST_ASSERT_EQUAL(SfMixerPrepareResult::READY,
                    controller.prepareSetRunning(false));
  TEST_ASSERT_TRUE(controller.start(300));
  TEST_ASSERT_FALSE(controller.running());
  TEST_ASSERT_EQUAL(SfMixerCommandResult::COMPLETED, controller.update(300));
  controller.update(1000000);
  TEST_ASSERT_EQUAL_UINT16(pulses, io.pulseWidths.size());

  TEST_ASSERT_EQUAL(SfMixerPrepareResult::READY,
                    controller.prepareSetRunning(false));
  TEST_ASSERT_TRUE(controller.start(400));
  TEST_ASSERT_EQUAL(SfMixerCommandResult::COMPLETED, controller.update(400));
}

void test_abort_and_force_stop_leave_step_inactive() {
  FakeIo io;
  SfMixerMotionController controller(io);
  TEST_ASSERT_EQUAL(SfMixerPrepareResult::READY,
                    controller.prepareSetRunning(true));
  TEST_ASSERT_TRUE(controller.start(100));
  TEST_ASSERT_TRUE(controller.abort());
  TEST_ASSERT_FALSE(controller.running());
  TEST_ASSERT_FALSE(controller.commandPending());
  TEST_ASSERT_FALSE(io.step);
  TEST_ASSERT_EQUAL_UINT16(0, io.pulseWidths.size());

  startMixer(controller, 200);
  controller.forceStop();
  TEST_ASSERT_FALSE(controller.running());
  TEST_ASSERT_FALSE(io.step);
  TEST_ASSERT_EQUAL(SfMixerCommandResult::NONE, controller.update(1000000));
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_start_waits_for_direction_setup_and_uses_confirmed_profile);
  RUN_TEST(test_trial_rate_uses_1667_us_without_early_or_catch_up_pulses);
  RUN_TEST(test_continuous_update_emits_one_pulse_without_catch_up);
  RUN_TEST(test_set_state_is_idempotent_and_stop_prevents_more_pulses);
  RUN_TEST(test_abort_and_force_stop_leave_step_inactive);
  return UNITY_END();
}
