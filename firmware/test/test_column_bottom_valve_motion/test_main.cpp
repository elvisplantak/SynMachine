#include <unity.h>

#include "actuator/ColumnBottomValveMotionController.h"

using namespace labforge;

namespace {

class FakeIo final : public ValveMotionIo {
 public:
  bool home = false;
  bool direction = false;
  bool step = false;
  uint32_t pulses = 0;
  uint16_t lastHighUs = 0;
  uint32_t releaseHomeAfterPulse = 0;

  bool homeActive() const override { return home; }
  void writeDirection(bool high) override { direction = high; }
  void writeStep(bool high) override { step = high; }
  void pulseStep(uint16_t highUs) override {
    ++pulses;
    lastHighUs = highUs;
    if (releaseHomeAfterPulse != 0 && pulses == releaseHomeAfterPulse)
      home = false;
  }
};

ColumnValveMotionResult runFor(ColumnBottomValveMotionController& controller,
                               uint32_t& now, uint32_t durationUs,
                               uint32_t intervalUs = 1000) {
  ColumnValveMotionResult result = ColumnValveMotionResult::NONE;
  const uint32_t iterations = durationUs / intervalUs;
  for (uint32_t i = 0; i < iterations; ++i) {
    now += intervalUs;
    result = controller.update(now);
    if (result != ColumnValveMotionResult::NONE) return result;
  }
  return result;
}

void establishHome(ColumnBottomValveMotionController& controller, FakeIo& io,
                   uint32_t& now) {
  io.home = true;
  TEST_ASSERT_EQUAL(ColumnValvePrepareResult::READY,
                    controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(now));
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::COMPLETED,
                    runFor(controller, now, kColumnValveHomeStableUs));
}

void runPulses(ColumnBottomValveMotionController& controller, uint32_t& now,
               uint32_t count) {
  for (uint32_t i = 0; i < count; ++i) {
    now += kColumnValveStepIntervalUs;
    controller.update(now);
  }
}

void test_home_uses_low_direction_and_stable_high() {
  FakeIo io;
  ColumnBottomValveMotionController controller(io);
  uint32_t now = 100;
  TEST_ASSERT_EQUAL(ColumnValvePrepareResult::READY,
                    controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(now));
  TEST_ASSERT_FALSE(io.direction);
  now += kColumnValveDirectionSetupUs;
  controller.update(now);
  TEST_ASSERT_EQUAL_UINT32(1, io.pulses);
  io.home = true;
  controller.update(++now);
  const uint32_t heldPulses = io.pulses;
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::NONE,
                    runFor(controller, now, 10000));
  io.home = false;
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::NONE,
                    runFor(controller, now, 2000));
  TEST_ASSERT_EQUAL_UINT32(heldPulses, io.pulses);
  io.home = true;
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::COMPLETED,
                    runFor(controller, now, 30000));
  TEST_ASSERT_EQUAL_UINT32(heldPulses, io.pulses);
  TEST_ASSERT_EQUAL_UINT16(kColumnValveStepHighUs, io.lastHighUs);
}

void test_home_confirmation_fails_closed_when_signal_remains_ambiguous() {
  FakeIo io;
  ColumnBottomValveMotionController controller(io);
  uint32_t now = 100;
  TEST_ASSERT_EQUAL(ColumnValvePrepareResult::READY,
                    controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(now));
  now += kColumnValveDirectionSetupUs;
  controller.update(now);
  io.home = true;
  controller.update(++now);
  const uint32_t heldPulses = io.pulses;

  ColumnValveMotionResult result = ColumnValveMotionResult::NONE;
  for (uint32_t elapsedUs = 0;
       elapsedUs < kColumnValveHomeConfirmationTimeoutUs; elapsedUs += 1000) {
    io.home = (elapsedUs % 4000) < 3000;
    now += 1000;
    result = controller.update(now);
    if (result != ColumnValveMotionResult::NONE) break;
  }

  TEST_ASSERT_EQUAL(ColumnValveMotionResult::HOME_SWITCH_UNEXPECTED, result);
  TEST_ASSERT_EQUAL_UINT32(heldPulses, io.pulses);
  TEST_ASSERT_EQUAL(ColumnValvePositionTrust::UNTRUSTED,
                    controller.positionTrust());
  TEST_ASSERT_FALSE(io.step);
}

void test_home_confirmation_requires_continuous_low_before_search_resumes() {
  FakeIo io;
  ColumnBottomValveMotionController controller(io);
  uint32_t now = 100;
  TEST_ASSERT_EQUAL(ColumnValvePrepareResult::READY,
                    controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(now));
  now += kColumnValveDirectionSetupUs;
  controller.update(now);
  io.home = true;
  controller.update(++now);
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::NONE,
                    runFor(controller, now, 5000));
  const uint32_t heldPulses = io.pulses;

  io.home = false;
  controller.update(++now);
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::NONE,
                    runFor(controller, now,
                           kColumnValveHomeStableUs - 1000));
  TEST_ASSERT_EQUAL(ColumnValveMotionState::CONFIRMING_HOME,
                    controller.state());
  TEST_ASSERT_EQUAL_UINT32(heldPulses, io.pulses);
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::NONE,
                    runFor(controller, now, 1000));
  TEST_ASSERT_EQUAL(ColumnValveMotionState::SEARCHING_HOME,
                    controller.state());
  TEST_ASSERT_EQUAL_UINT32(heldPulses, io.pulses);
}

void test_delayed_sample_cannot_supply_whole_home_confirmation() {
  FakeIo io;
  io.home = true;
  ColumnBottomValveMotionController controller(io);
  uint32_t now = 100;
  TEST_ASSERT_EQUAL(ColumnValvePrepareResult::READY,
                    controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(now));

  now += kColumnValveHomeStableUs;
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::NONE, controller.update(now));
  TEST_ASSERT_EQUAL(ColumnValveMotionState::CONFIRMING_HOME,
                    controller.state());
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::COMPLETED,
                    runFor(controller, now,
                           kColumnValveHomeStableUs -
                               kColumnValveHomeEvidenceSampleCapUs));
}

void test_move_away_ignores_home_noise_only_within_release_bound() {
  FakeIo io;
  ColumnBottomValveMotionController controller(io);
  uint32_t now = 100;
  establishHome(controller, io, now);
  TEST_ASSERT_EQUAL(ColumnValvePrepareResult::READY,
                    controller.prepareSetPosition(4));
  TEST_ASSERT_TRUE(controller.start(now));
  for (uint32_t i = 0; i < 100; ++i) {
    io.home = (i % 4) != 3;
    now += kColumnValveStepIntervalUs;
    TEST_ASSERT_EQUAL(ColumnValveMotionResult::NONE, controller.update(now));
  }
  TEST_ASSERT_EQUAL_UINT32(100, io.pulses);
  TEST_ASSERT_EQUAL(ColumnValveMotionState::MOVING, controller.state());

  io.home = false;
  runPulses(controller, now, kColumnValveClosedSteps - 100);
  TEST_ASSERT_EQUAL_UINT32(kColumnValveClosedSteps, io.pulses);
  TEST_ASSERT_EQUAL(ColumnValveMotionState::CONFIRMING_HOME_RELEASE,
                    controller.state());
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::COMPLETED,
                    runFor(controller, now, kColumnValveHomeStableUs));
}

void test_ambiguous_home_release_fails_closed_without_more_pulses() {
  FakeIo io;
  ColumnBottomValveMotionController controller(io);
  uint32_t now = 100;
  establishHome(controller, io, now);
  TEST_ASSERT_EQUAL(ColumnValvePrepareResult::READY,
                    controller.prepareSetPosition(4));
  TEST_ASSERT_TRUE(controller.start(now));
  runPulses(controller, now, kColumnValveClosedSteps);
  const uint32_t heldPulses = io.pulses;

  ColumnValveMotionResult result = ColumnValveMotionResult::NONE;
  for (uint32_t elapsedUs = 0;
       elapsedUs < kColumnValveHomeConfirmationTimeoutUs; elapsedUs += 1000) {
    io.home = (elapsedUs % 4000) < 3000;
    now += 1000;
    result = controller.update(now);
    if (result != ColumnValveMotionResult::NONE) break;
  }

  TEST_ASSERT_EQUAL(ColumnValveMotionResult::HOME_SWITCH_STUCK, result);
  TEST_ASSERT_EQUAL_UINT32(heldPulses, io.pulses);
  TEST_ASSERT_EQUAL(ColumnValvePositionTrust::UNTRUSTED,
                    controller.positionTrust());
  TEST_ASSERT_FALSE(io.step);
}

void test_closed_and_open_use_confirmed_absolute_steps() {
  TEST_ASSERT_EQUAL_UINT32(889, kColumnValveClosedSteps);
  TEST_ASSERT_EQUAL_UINT32(24739, kColumnValveOpenSteps);
  TEST_ASSERT_EQUAL_UINT32(
      23850, kColumnValveOpenSteps - kColumnValveClosedSteps);
  FakeIo io;
  ColumnBottomValveMotionController controller(io);
  uint32_t now = 100;
  establishHome(controller, io, now);
  io.home = false;
  TEST_ASSERT_EQUAL(ColumnValvePrepareResult::READY,
                    controller.prepareSetPosition(4));
  TEST_ASSERT_TRUE(controller.start(now));
  TEST_ASSERT_TRUE(io.direction);
  runPulses(controller, now, kColumnValveClosedSteps);
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::COMPLETED,
                    runFor(controller, now, kColumnValveHomeStableUs));
  TEST_ASSERT_EQUAL_UINT32(kColumnValveClosedSteps, io.pulses);
  TEST_ASSERT_EQUAL_UINT32(kColumnValveClosedSteps,
                           controller.positionSteps());

  TEST_ASSERT_EQUAL(ColumnValvePrepareResult::READY,
                    controller.prepareSetPosition(94));
  TEST_ASSERT_TRUE(controller.start(now));
  runPulses(controller, now,
            kColumnValveOpenSteps - kColumnValveClosedSteps);
  TEST_ASSERT_EQUAL_UINT32(kColumnValveOpenSteps, io.pulses);
  TEST_ASSERT_EQUAL_UINT32(kColumnValveOpenSteps, controller.positionSteps());
}

void test_untrusted_position_rejects_move_and_abort_invalidates_trust() {
  FakeIo io;
  ColumnBottomValveMotionController controller(io);
  TEST_ASSERT_EQUAL(ColumnValvePrepareResult::POSITION_UNTRUSTED,
                    controller.prepareSetPosition(4));
  uint32_t now = 100;
  establishHome(controller, io, now);
  io.home = false;
  TEST_ASSERT_EQUAL(ColumnValvePrepareResult::READY,
                    controller.prepareSetPosition(94));
  TEST_ASSERT_TRUE(controller.start(now));
  TEST_ASSERT_TRUE(controller.abort());
  TEST_ASSERT_EQUAL(ColumnValvePositionTrust::UNTRUSTED,
                    controller.positionTrust());
  TEST_ASSERT_FALSE(io.step);
}

void test_final_closed_pulse_may_release_home_without_extra_travel() {
  FakeIo io;
  ColumnBottomValveMotionController controller(io);
  uint32_t now = 100;
  establishHome(controller, io, now);
  io.releaseHomeAfterPulse = kColumnValveClosedSteps;
  TEST_ASSERT_EQUAL(ColumnValvePrepareResult::READY,
                    controller.prepareSetPosition(4));
  TEST_ASSERT_TRUE(controller.start(now));
  runPulses(controller, now, kColumnValveClosedSteps);
  TEST_ASSERT_EQUAL_UINT32(kColumnValveClosedSteps, io.pulses);
  TEST_ASSERT_FALSE(io.home);
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::NONE,
                    controller.update(now + kColumnValveHomeStableUs - 1));
  TEST_ASSERT_EQUAL_UINT32(kColumnValveClosedSteps, io.pulses);
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::COMPLETED,
                    controller.update(now + kColumnValveHomeStableUs));
  TEST_ASSERT_EQUAL_UINT32(kColumnValveClosedSteps, io.pulses);
  TEST_ASSERT_EQUAL_UINT32(kColumnValveClosedSteps,
                           controller.positionSteps());
  TEST_ASSERT_EQUAL(ColumnValvePositionTrust::TRUSTED,
                    controller.positionTrust());
  TEST_ASSERT_FALSE(io.step);
}

void test_stuck_and_unexpected_home_fail_closed() {
  FakeIo io;
  ColumnBottomValveMotionController controller(io);
  uint32_t now = 100;
  establishHome(controller, io, now);
  TEST_ASSERT_EQUAL(ColumnValvePrepareResult::READY,
                    controller.prepareSetPosition(4));
  TEST_ASSERT_TRUE(controller.start(now));
  runPulses(controller, now, kColumnValveClosedSteps);
  TEST_ASSERT_EQUAL_UINT32(kColumnValveClosedSteps, io.pulses);
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::HOME_SWITCH_STUCK,
                    runFor(controller, now, kColumnValveHomeStableUs));
  TEST_ASSERT_EQUAL_UINT32(kColumnValveClosedSteps, io.pulses);
  TEST_ASSERT_EQUAL(ColumnValvePositionTrust::UNTRUSTED,
                    controller.positionTrust());
  TEST_ASSERT_FALSE(io.step);

  FakeIo io2;
  ColumnBottomValveMotionController controller2(io2);
  now = 100;
  establishHome(controller2, io2, now);
  io2.releaseHomeAfterPulse = kColumnValveClosedSteps;
  controller2.prepareSetPosition(4);
  controller2.start(now);
  runPulses(controller2, now, kColumnValveClosedSteps);
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::COMPLETED,
                    runFor(controller2, now, kColumnValveHomeStableUs));
  io2.releaseHomeAfterPulse = 0;
  controller2.prepareSetPosition(94);
  controller2.start(now);
  runPulses(controller2, now, 10);
  io2.home = true;
  controller2.update(++now);
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::HOME_SWITCH_UNEXPECTED,
                    controller2.update(now + kColumnValveHomeStableUs));
  TEST_ASSERT_EQUAL(ColumnValvePositionTrust::UNTRUSTED,
                    controller2.positionTrust());
  TEST_ASSERT_FALSE(io2.step);
}

void test_missing_home_times_out_and_invalidates_trust() {
  FakeIo io;
  ColumnBottomValveMotionController controller(io);
  uint32_t now = 100;
  TEST_ASSERT_EQUAL(ColumnValvePrepareResult::READY,
                    controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(now));
  runPulses(controller, now, kColumnValveMaximumSearchSteps - 1);
  now += kColumnValveStepIntervalUs;
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::MOTION_TIMEOUT,
                    controller.update(now));
  TEST_ASSERT_EQUAL_UINT32(kColumnValveMaximumSearchSteps, io.pulses);
  TEST_ASSERT_EQUAL(ColumnValvePositionTrust::UNTRUSTED,
                    controller.positionTrust());
  TEST_ASSERT_FALSE(io.step);
}

void test_false_home_candidates_do_not_reset_total_search_bound() {
  FakeIo io;
  ColumnBottomValveMotionController controller(io);
  uint32_t now = 100;
  TEST_ASSERT_EQUAL(ColumnValvePrepareResult::READY,
                    controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(now));

  runPulses(controller, now, 10);
  io.home = true;
  controller.update(++now);
  io.home = false;
  controller.update(++now);
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::NONE,
                    runFor(controller, now, kColumnValveHomeStableUs));
  TEST_ASSERT_EQUAL(ColumnValveMotionState::SEARCHING_HOME,
                    controller.state());
  TEST_ASSERT_EQUAL_UINT32(10, controller.stageSteps());

  runPulses(controller, now, 20);
  io.home = true;
  controller.update(++now);
  io.home = false;
  controller.update(++now);
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::NONE,
                    runFor(controller, now, kColumnValveHomeStableUs));
  TEST_ASSERT_EQUAL(ColumnValveMotionState::SEARCHING_HOME,
                    controller.state());
  TEST_ASSERT_EQUAL_UINT32(30, controller.stageSteps());

  runPulses(controller, now, kColumnValveMaximumSearchSteps - 31);
  TEST_ASSERT_EQUAL_UINT32(kColumnValveMaximumSearchSteps - 1, io.pulses);
  now += kColumnValveStepIntervalUs;
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::MOTION_TIMEOUT,
                    controller.update(now));
  TEST_ASSERT_EQUAL_UINT32(kColumnValveMaximumSearchSteps, io.pulses);
  TEST_ASSERT_EQUAL(ColumnValvePositionTrust::UNTRUSTED,
                    controller.positionTrust());
  TEST_ASSERT_FALSE(io.step);
}

}  // namespace

void setUp() {}
void tearDown() {}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_home_uses_low_direction_and_stable_high);
  RUN_TEST(test_home_confirmation_fails_closed_when_signal_remains_ambiguous);
  RUN_TEST(test_home_confirmation_requires_continuous_low_before_search_resumes);
  RUN_TEST(test_delayed_sample_cannot_supply_whole_home_confirmation);
  RUN_TEST(test_move_away_ignores_home_noise_only_within_release_bound);
  RUN_TEST(test_ambiguous_home_release_fails_closed_without_more_pulses);
  RUN_TEST(test_closed_and_open_use_confirmed_absolute_steps);
  RUN_TEST(test_untrusted_position_rejects_move_and_abort_invalidates_trust);
  RUN_TEST(test_final_closed_pulse_may_release_home_without_extra_travel);
  RUN_TEST(test_stuck_and_unexpected_home_fail_closed);
  RUN_TEST(test_missing_home_times_out_and_invalidates_trust);
  RUN_TEST(test_false_home_candidates_do_not_reset_total_search_bound);
  return UNITY_END();
}
