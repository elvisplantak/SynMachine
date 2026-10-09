#include <unity.h>

#include "actuator/ValveMotionController.h"

using namespace labforge;

namespace {

class FakeIo final : public ValveMotionIo {
 public:
  bool home = false;
  bool direction = false;
  uint16_t pulses = 0;
  uint16_t lastHighUs = 0;
  bool step = false;

  bool homeActive() const override { return home; }
  void writeDirection(bool high) override { direction = high; }
  void writeStep(bool high) override { step = high; }
  void pulseStep(uint16_t highUs) override {
    ++pulses;
    lastHighUs = highUs;
  }
};

uint32_t nextPulse(uint32_t now) { return now + kValveStepIntervalUs; }

void establishHome(ValveMotionController& controller, FakeIo& io,
                   uint32_t& now) {
  io.home = true;
  TEST_ASSERT_EQUAL(ValvePrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(now));
  now += kValveHomeStableUs;
  TEST_ASSERT_EQUAL(ValveMotionResult::COMPLETED, controller.update(now));
  TEST_ASSERT_EQUAL(ValvePositionTrust::TRUSTED, controller.positionTrust());
}

void test_home_uses_configured_direction_and_stable_high() {
  FakeIo io;
  ValveMotionController controller(io, true);
  uint32_t now = 100;
  TEST_ASSERT_EQUAL(ValvePrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(now));
  TEST_ASSERT_TRUE(io.direction);
  now += kValveDirectionSetupUs;
  TEST_ASSERT_EQUAL(ValveMotionResult::NONE, controller.update(now));
  TEST_ASSERT_EQUAL_UINT16(1, io.pulses);
  io.home = true;
  TEST_ASSERT_EQUAL(ValveMotionResult::NONE, controller.update(++now));
  TEST_ASSERT_EQUAL(ValveMotionResult::NONE,
                    controller.update(now + kValveHomeStableUs - 1));
  TEST_ASSERT_EQUAL(ValveMotionResult::COMPLETED,
                    controller.update(now + kValveHomeStableUs));
  TEST_ASSERT_EQUAL_UINT16(kValveStepHighUs, io.lastHighUs);
}

void test_low_direction_home_stops_at_switch_and_move_away_uses_high() {
  FakeIo io;
  io.direction = true;
  ValveMotionController controller(io, false);
  uint32_t now = 100;
  TEST_ASSERT_EQUAL(ValvePrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(now));
  TEST_ASSERT_FALSE(io.direction);
  now += kValveDirectionSetupUs;
  controller.update(now);
  TEST_ASSERT_EQUAL_UINT16(1, io.pulses);
  io.home = true;
  controller.update(++now);
  now += kValveHomeStableUs;
  TEST_ASSERT_EQUAL(ValveMotionResult::COMPLETED, controller.update(now));
  TEST_ASSERT_EQUAL_UINT16(1, io.pulses);
  TEST_ASSERT_FALSE(io.step);
  TEST_ASSERT_EQUAL(ValvePositionTrust::TRUSTED, controller.positionTrust());
  TEST_ASSERT_EQUAL(ValvePrepareResult::READY, controller.prepareSetPosition(90));
  TEST_ASSERT_TRUE(controller.start(++now));
  TEST_ASSERT_TRUE(io.direction);
  controller.abort();
  TEST_ASSERT_FALSE(io.step);
}

void test_home_candidate_bounce_holds_step_until_stable_resolution() {
  FakeIo io;
  ValveMotionController controller(io, true);
  uint32_t now = 100;
  TEST_ASSERT_EQUAL(ValvePrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(now));
  now += kValveDirectionSetupUs;
  TEST_ASSERT_EQUAL(ValveMotionResult::NONE, controller.update(now));
  TEST_ASSERT_EQUAL_UINT16(1, io.pulses);

  io.home = true;
  TEST_ASSERT_EQUAL(ValveMotionResult::NONE, controller.update(++now));
  const uint16_t pulsesAtCandidate = io.pulses;
  TEST_ASSERT_FALSE(io.step);

  io.home = false;
  now += 1000;
  TEST_ASSERT_EQUAL(ValveMotionResult::NONE, controller.update(now));
  TEST_ASSERT_EQUAL_UINT16(pulsesAtCandidate, io.pulses);
  TEST_ASSERT_EQUAL(ValveMotionResult::NONE,
                    controller.update(now + kValveHomeStableUs - 1));
  TEST_ASSERT_EQUAL_UINT16(pulsesAtCandidate, io.pulses);

  io.home = true;
  now += kValveHomeStableUs;
  TEST_ASSERT_EQUAL(ValveMotionResult::NONE, controller.update(now));
  TEST_ASSERT_EQUAL(ValveMotionResult::COMPLETED,
                    controller.update(now + kValveHomeStableUs));
  TEST_ASSERT_EQUAL_UINT16(pulsesAtCandidate, io.pulses);
  TEST_ASSERT_FALSE(io.step);
}

void test_stable_low_after_home_candidate_may_resume_search() {
  FakeIo io;
  ValveMotionController controller(io, false);
  uint32_t now = 100;
  TEST_ASSERT_EQUAL(ValvePrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(now));
  now += kValveDirectionSetupUs;
  controller.update(now);
  io.home = true;
  controller.update(++now);
  const uint16_t pulsesAtCandidate = io.pulses;

  io.home = false;
  controller.update(++now);
  TEST_ASSERT_EQUAL(ValveMotionResult::NONE,
                    controller.update(now + kValveHomeStableUs - 1));
  TEST_ASSERT_EQUAL_UINT16(pulsesAtCandidate, io.pulses);
  now += kValveHomeStableUs;
  TEST_ASSERT_EQUAL(ValveMotionResult::NONE, controller.update(now));
  TEST_ASSERT_EQUAL(ValveMotionState::SEARCHING_HOME, controller.state());
  TEST_ASSERT_EQUAL_UINT16(pulsesAtCandidate, io.pulses);
  TEST_ASSERT_FALSE(io.step);

  now += kValveDirectionSetupUs;
  TEST_ASSERT_EQUAL(ValveMotionResult::NONE, controller.update(now));
  TEST_ASSERT_EQUAL_UINT16(pulsesAtCandidate + 1, io.pulses);
}

void test_move_home_to_90_releases_switch_and_emits_400_pulses() {
  FakeIo io;
  ValveMotionController controller(io, true);
  uint32_t now = 100;
  establishHome(controller, io, now);
  TEST_ASSERT_EQUAL(ValvePrepareResult::READY,
                    controller.prepareSetPosition(90));
  TEST_ASSERT_TRUE(controller.start(now));
  TEST_ASSERT_FALSE(io.direction);
  io.home = false;
  TEST_ASSERT_EQUAL(ValveMotionResult::NONE, controller.update(now));
  now += kValveHomeStableUs;
  TEST_ASSERT_EQUAL(ValveMotionResult::NONE, controller.update(now));
  for (uint16_t i = 0; i < kValveStepsPer90Degrees; ++i) {
    now = nextPulse(now);
    const ValveMotionResult result = controller.update(now);
    if (i + 1 == kValveStepsPer90Degrees)
      TEST_ASSERT_EQUAL(ValveMotionResult::COMPLETED, result);
    else
      TEST_ASSERT_EQUAL(ValveMotionResult::NONE, result);
  }
  TEST_ASSERT_EQUAL_UINT16(kValveStepsPer90Degrees, io.pulses);
  TEST_ASSERT_EQUAL_UINT16(90, controller.positionDegrees());
}

void test_repeated_home_at_trusted_zero_ignores_short_low_glitch() {
  FakeIo io;
  ValveMotionController controller(io, true);
  uint32_t now = 100;
  establishHome(controller, io, now);
  const uint16_t pulsesBefore = io.pulses;

  io.home = false;
  TEST_ASSERT_EQUAL(ValvePrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(now));
  TEST_ASSERT_EQUAL(ValveMotionResult::NONE,
                    controller.update(now + kValveHomeStableUs - 1));
  io.home = true;
  TEST_ASSERT_EQUAL(ValveMotionResult::NONE,
                    controller.update(now + kValveHomeStableUs));
  now += 2 * kValveHomeStableUs;
  TEST_ASSERT_EQUAL(ValveMotionResult::COMPLETED, controller.update(now));
  TEST_ASSERT_EQUAL_UINT16(pulsesBefore, io.pulses);
  TEST_ASSERT_EQUAL(ValvePositionTrust::TRUSTED, controller.positionTrust());
}

void test_repeated_home_at_trusted_zero_fails_closed_on_stable_low() {
  FakeIo io;
  ValveMotionController controller(io, false);
  uint32_t now = 100;
  establishHome(controller, io, now);
  const uint16_t pulsesBefore = io.pulses;

  io.home = false;
  TEST_ASSERT_EQUAL(ValvePrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(now));
  TEST_ASSERT_EQUAL(ValveMotionResult::HOME_SWITCH_UNEXPECTED,
                    controller.update(now + kValveHomeStableUs));
  TEST_ASSERT_EQUAL_UINT16(pulsesBefore, io.pulses);
  TEST_ASSERT_EQUAL(ValvePositionTrust::UNTRUSTED,
                    controller.positionTrust());
}

void test_no_catch_up_burst_after_late_update() {
  FakeIo io;
  ValveMotionController controller(io, false);
  uint32_t now = 100;
  establishHome(controller, io, now);
  io.home = false;
  TEST_ASSERT_EQUAL(ValvePrepareResult::READY,
                    controller.prepareSetPosition(180));
  TEST_ASSERT_TRUE(controller.start(now));
  controller.update(now + 1000000);
  TEST_ASSERT_EQUAL_UINT16(1, io.pulses);
  controller.update(now + 1000001);
  TEST_ASSERT_EQUAL_UINT16(1, io.pulses);
  controller.update(now + 1000000 + kValveStepIntervalUs - 1);
  TEST_ASSERT_EQUAL_UINT16(1, io.pulses);
  controller.update(now + 1000000 + kValveStepIntervalUs);
  TEST_ASSERT_EQUAL_UINT16(2, io.pulses);
  controller.update(now + 1000000 + kValveStepIntervalUs);
  TEST_ASSERT_EQUAL_UINT16(2, io.pulses);
}

void test_home_pulse_spacing_survives_clock_wrap() {
  FakeIo io;
  ValveMotionController controller(io, true);
  const uint32_t start = UINT32_MAX - kValveStepIntervalUs / 2;
  const uint32_t firstPulse = start + kValveDirectionSetupUs;
  TEST_ASSERT_EQUAL(ValvePrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(start));
  controller.update(firstPulse - 1);
  TEST_ASSERT_EQUAL_UINT16(0, io.pulses);
  controller.update(firstPulse);
  TEST_ASSERT_EQUAL_UINT16(1, io.pulses);
  controller.update(firstPulse + kValveStepIntervalUs - 1);
  TEST_ASSERT_EQUAL_UINT16(1, io.pulses);
  controller.update(firstPulse + kValveStepIntervalUs);
  TEST_ASSERT_EQUAL_UINT16(2, io.pulses);
  TEST_ASSERT_EQUAL(ValveMotionState::SEARCHING_HOME, controller.state());
}

void test_abort_invalidates_started_motion() {
  FakeIo io;
  ValveMotionController controller(io, true);
  uint32_t now = 100;
  establishHome(controller, io, now);
  io.home = false;
  TEST_ASSERT_EQUAL(ValvePrepareResult::READY,
                    controller.prepareSetPosition(90));
  TEST_ASSERT_TRUE(controller.start(now));
  TEST_ASSERT_TRUE(controller.abort());
  TEST_ASSERT_EQUAL(ValvePositionTrust::UNTRUSTED,
                    controller.positionTrust());
}

void test_missing_home_times_out_untrusted_with_step_inactive() {
  FakeIo io;
  ValveMotionController controller(io, true);
  uint32_t now = 100;
  TEST_ASSERT_EQUAL(ValvePrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(now));
  ValveMotionResult result = ValveMotionResult::NONE;
  for (uint16_t i = 0; i < kValveMaximumSearchSteps; ++i) {
    now = nextPulse(now);
    result = controller.update(now);
  }
  TEST_ASSERT_EQUAL(ValveMotionResult::MOTION_TIMEOUT, result);
  TEST_ASSERT_EQUAL_UINT16(kValveMaximumSearchSteps, io.pulses);
  TEST_ASSERT_EQUAL(ValvePositionTrust::UNTRUSTED,
                    controller.positionTrust());
  TEST_ASSERT_FALSE(io.step);
  TEST_ASSERT_FALSE(controller.busy());
}

void test_home_stuck_during_release_fails_untrusted_with_step_inactive() {
  FakeIo io;
  ValveMotionController controller(io, true);
  uint32_t now = 100;
  establishHome(controller, io, now);
  TEST_ASSERT_EQUAL(ValvePrepareResult::READY,
                    controller.prepareSetPosition(90));
  TEST_ASSERT_TRUE(controller.start(now));
  ValveMotionResult result = ValveMotionResult::NONE;
  for (uint16_t i = 0; i < kValveStepsPer90Degrees; ++i) {
    now = nextPulse(now);
    result = controller.update(now);
  }
  TEST_ASSERT_EQUAL(ValveMotionResult::HOME_SWITCH_STUCK, result);
  TEST_ASSERT_EQUAL(ValvePositionTrust::UNTRUSTED,
                    controller.positionTrust());
  TEST_ASSERT_FALSE(io.step);
  TEST_ASSERT_FALSE(controller.busy());
}

void test_stable_unexpected_home_fails_untrusted_with_step_inactive() {
  FakeIo io;
  ValveMotionController controller(io, true);
  uint32_t now = 100;
  establishHome(controller, io, now);
  TEST_ASSERT_EQUAL(ValvePrepareResult::READY,
                    controller.prepareSetPosition(90));
  TEST_ASSERT_TRUE(controller.start(now));
  io.home = false;
  controller.update(now);
  now += kValveHomeStableUs;
  controller.update(now);
  now = nextPulse(now);
  controller.update(now);

  io.home = true;
  controller.update(++now);
  TEST_ASSERT_EQUAL(ValveMotionResult::NONE,
                    controller.update(now + kValveHomeStableUs - 1));
  TEST_ASSERT_EQUAL(ValveMotionResult::HOME_SWITCH_UNEXPECTED,
                    controller.update(now + kValveHomeStableUs));
  TEST_ASSERT_EQUAL(ValvePositionTrust::UNTRUSTED,
                    controller.positionTrust());
  TEST_ASSERT_FALSE(io.step);
  TEST_ASSERT_FALSE(controller.busy());
}

}  // namespace

void setUp() {}
void tearDown() {}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_home_uses_configured_direction_and_stable_high);
  RUN_TEST(test_low_direction_home_stops_at_switch_and_move_away_uses_high);
  RUN_TEST(test_home_candidate_bounce_holds_step_until_stable_resolution);
  RUN_TEST(test_stable_low_after_home_candidate_may_resume_search);
  RUN_TEST(test_move_home_to_90_releases_switch_and_emits_400_pulses);
  RUN_TEST(test_repeated_home_at_trusted_zero_ignores_short_low_glitch);
  RUN_TEST(test_repeated_home_at_trusted_zero_fails_closed_on_stable_low);
  RUN_TEST(test_no_catch_up_burst_after_late_update);
  RUN_TEST(test_home_pulse_spacing_survives_clock_wrap);
  RUN_TEST(test_abort_invalidates_started_motion);
  RUN_TEST(test_missing_home_times_out_untrusted_with_step_inactive);
  RUN_TEST(test_home_stuck_during_release_fails_untrusted_with_step_inactive);
  RUN_TEST(test_stable_unexpected_home_fails_untrusted_with_step_inactive);
  return UNITY_END();
}
