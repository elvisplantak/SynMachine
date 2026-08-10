#include <unity.h>

#include "actuator/P1MotionController.h"

using namespace labforge;

namespace {

class FakeIo : public P1MotionIo {
 public:
  bool home = false;
  bool direction = false;
  bool step = false;
  unsigned directionWrites = 0;
  unsigned stepWrites = 0;
  unsigned risingEdges = 0;

  bool homeActive() const override { return home; }
  void writeDirection(bool high) override {
    direction = high;
    ++directionWrites;
  }
  void writeStep(bool high) override {
    if (high && !step) ++risingEdges;
    step = high;
    ++stepWrites;
  }
};

void reachFirstRise(uint32_t& nowUs) { nowUs += kP1DirectionSetupUs; }

P1MotionResult runOnePulse(P1MotionController& controller, FakeIo& io,
                           uint32_t& nowUs) {
  const unsigned before = io.risingEdges;
  P1MotionResult result = controller.update(nowUs);
  TEST_ASSERT_EQUAL_UINT32(before + 1, io.risingEdges);
  TEST_ASSERT_TRUE(io.step);
  nowUs += kP1StepHighUs;
  result = controller.update(nowUs);
  TEST_ASSERT_FALSE(io.step);
  nowUs += kP1StepIntervalUs - kP1StepHighUs;
  return result;
}

void establishHome(P1MotionController& controller, FakeIo& io,
                   uint32_t& nowUs) {
  io.home = true;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(nowUs));
  TEST_ASSERT_EQUAL(P1MotionState::CONFIRMING_HOME_ACTIVE,
                    controller.state());
  TEST_ASSERT_FALSE(io.direction);
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);
  nowUs += kP1HomeStableUs;
  TEST_ASSERT_EQUAL(P1MotionResult::COMPLETED, controller.update(nowUs));
  TEST_ASSERT_EQUAL(P1PositionTrust::TRUSTED, controller.positionTrust());
  TEST_ASSERT_EQUAL_UINT16(0, controller.positionSteps());
}

void test_boot_is_untrusted_and_prepare_has_no_physical_side_effect() {
  FakeIo io;
  P1MotionController controller(io);
  TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED, controller.positionTrust());
  TEST_ASSERT_EQUAL(P1MotionState::IDLE, controller.state());
  TEST_ASSERT_EQUAL(P1PrepareResult::POSITION_UNTRUSTED,
                    controller.prepareMoveAbsolute(100));
  TEST_ASSERT_EQUAL_UINT32(0, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(0, io.stepWrites);

  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_EQUAL(P1MotionState::PREPARED_HOME, controller.state());
  TEST_ASSERT_EQUAL_UINT32(0, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(0, io.stepWrites);
}

void test_direction_setup_precedes_first_step_rise() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = 100;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(nowUs));
  TEST_ASSERT_EQUAL_UINT32(1, io.directionWrites);
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);
  nowUs += kP1DirectionSetupUs - 1;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);
  ++nowUs;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_EQUAL_UINT32(1, io.risingEdges);
}

void test_home_requires_stable_active_signal_and_rejects_one_sample_glitch() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = 0;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(nowUs));
  reachFirstRise(nowUs);
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, runOnePulse(controller, io, nowUs));

  io.home = true;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_EQUAL(P1MotionState::CONFIRMING_HOME_ACTIVE,
                    controller.state());
  TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED, controller.positionTrust());
  io.home = false;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_EQUAL(P1MotionState::SEARCHING_HOME, controller.state());

  nowUs += kP1StepIntervalUs;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, runOnePulse(controller, io, nowUs));
  io.home = true;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  nowUs += kP1HomeStableUs - 1;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED, controller.positionTrust());
  ++nowUs;
  TEST_ASSERT_EQUAL(P1MotionResult::COMPLETED, controller.update(nowUs));
  TEST_ASSERT_EQUAL(P1PositionTrust::TRUSTED, controller.positionTrust());
}

void test_initial_active_home_is_confirmed_without_away_motion() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = 0;
  establishHome(controller, io, nowUs);
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);
  TEST_ASSERT_FALSE(io.step);
}

void test_trusted_home_releases_then_rehomes_with_stable_transitions() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = 0;
  establishHome(controller, io, nowUs);

  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(nowUs));
  TEST_ASSERT_EQUAL(P1MotionState::RELEASING_HOME, controller.state());
  TEST_ASSERT_TRUE(io.direction);
  reachFirstRise(nowUs);
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, runOnePulse(controller, io, nowUs));
  io.home = false;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_EQUAL(P1MotionState::CONFIRMING_HOME_RELEASE,
                    controller.state());
  nowUs += kP1HomeStableUs;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_EQUAL(P1MotionState::SEARCHING_HOME, controller.state());
  TEST_ASSERT_FALSE(io.direction);

  io.home = true;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  nowUs += kP1HomeStableUs;
  TEST_ASSERT_EQUAL(P1MotionResult::COMPLETED, controller.update(nowUs));
  TEST_ASSERT_EQUAL(P1PositionTrust::TRUSTED, controller.positionTrust());
}

void test_stuck_home_release_fails_closed() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = 0;
  establishHome(controller, io, nowUs);
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(nowUs));
  reachFirstRise(nowUs);
  P1MotionResult result = P1MotionResult::NONE;
  for (uint16_t i = 0; i < kP1HomeReleaseMaximumSteps; ++i)
    result = runOnePulse(controller, io, nowUs);
  TEST_ASSERT_EQUAL(P1MotionResult::HOME_SWITCH_STUCK, result);
  TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED, controller.positionTrust());
  TEST_ASSERT_FALSE(io.step);
}

void test_demo_home_search_is_bounded_to_accepted_full_span() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = 0;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(nowUs));
  reachFirstRise(nowUs);
  P1MotionResult result = P1MotionResult::NONE;
  for (uint32_t i = 0; i < kP1MaximumAbsoluteSteps; ++i)
    result = runOnePulse(controller, io, nowUs);
  TEST_ASSERT_EQUAL(P1MotionResult::MOTION_TIMEOUT, result);
  TEST_ASSERT_EQUAL_UINT32(kP1MaximumAbsoluteSteps, io.risingEdges);
  TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED, controller.positionTrust());
  TEST_ASSERT_FALSE(io.step);
}

void test_absolute_move_rejects_zero_and_tracks_position() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = 0;
  establishHome(controller, io, nowUs);

  TEST_ASSERT_EQUAL(P1PrepareResult::TARGET_REQUIRES_HOME,
                    controller.prepareMoveAbsolute(0));
  TEST_ASSERT_EQUAL(P1PrepareResult::INVALID_TARGET,
                    controller.prepareMoveAbsolute(20501));
  io.home = false;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareMoveAbsolute(3));
  TEST_ASSERT_TRUE(controller.start(nowUs));
  reachFirstRise(nowUs);
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, runOnePulse(controller, io, nowUs));
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, runOnePulse(controller, io, nowUs));
  TEST_ASSERT_EQUAL(P1MotionResult::COMPLETED,
                    runOnePulse(controller, io, nowUs));
  TEST_ASSERT_EQUAL_UINT16(3, controller.positionSteps());
  TEST_ASSERT_EQUAL(P1PositionTrust::TRUSTED, controller.positionTrust());
}

void test_move_cannot_complete_inside_active_home_release_zone() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = 0;
  establishHome(controller, io, nowUs);
  TEST_ASSERT_EQUAL(P1PrepareResult::READY,
                    controller.prepareMoveAbsolute(100));
  TEST_ASSERT_TRUE(controller.start(nowUs));
  reachFirstRise(nowUs);
  P1MotionResult result = P1MotionResult::NONE;
  for (uint16_t i = 0; i < 100; ++i)
    result = runOnePulse(controller, io, nowUs);
  TEST_ASSERT_EQUAL(P1MotionResult::HOME_SWITCH_STUCK, result);
  TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED, controller.positionTrust());
  TEST_ASSERT_FALSE(io.step);
}

void test_move_requires_stable_home_release_and_ignores_one_sample_bounce() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = 0;
  establishHome(controller, io, nowUs);
  TEST_ASSERT_EQUAL(P1PrepareResult::READY,
                    controller.prepareMoveAbsolute(3));
  TEST_ASSERT_TRUE(controller.start(nowUs));
  reachFirstRise(nowUs);
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, runOnePulse(controller, io, nowUs));

  io.home = false;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_EQUAL(P1MotionState::CONFIRMING_MOVE_RELEASE,
                    controller.state());
  io.home = true;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_EQUAL(P1MotionState::MOVING, controller.state());

  io.home = false;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  nowUs += kP1HomeStableUs;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  nowUs += kP1StepIntervalUs;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, runOnePulse(controller, io, nowUs));
  TEST_ASSERT_EQUAL(P1MotionResult::COMPLETED,
                    runOnePulse(controller, io, nowUs));
  TEST_ASSERT_EQUAL_UINT16(3, controller.positionSteps());
}

void test_unexpected_home_during_absolute_move_invalidates_position() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = 0;
  establishHome(controller, io, nowUs);
  io.home = false;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY,
                    controller.prepareMoveAbsolute(10));
  TEST_ASSERT_TRUE(controller.start(nowUs));
  reachFirstRise(nowUs);
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, runOnePulse(controller, io, nowUs));
  io.home = true;
  TEST_ASSERT_EQUAL(P1MotionResult::HOME_SWITCH_UNEXPECTED,
                    controller.update(nowUs));
  TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED, controller.positionTrust());
  TEST_ASSERT_FALSE(io.step);
}

void test_abort_during_home_release_search_and_absolute_motion() {
  {
    FakeIo io;
    P1MotionController controller(io);
    uint32_t nowUs = 0;
    establishHome(controller, io, nowUs);
    TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
    TEST_ASSERT_TRUE(controller.start(nowUs));
    TEST_ASSERT_TRUE(controller.abort());
    TEST_ASSERT_EQUAL(P1MotionState::IDLE, controller.state());
    TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED,
                      controller.positionTrust());
    TEST_ASSERT_FALSE(io.step);
  }
  {
    FakeIo io;
    P1MotionController controller(io);
    uint32_t nowUs = 0;
    TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
    TEST_ASSERT_TRUE(controller.start(nowUs));
    TEST_ASSERT_TRUE(controller.abort());
    TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED,
                      controller.positionTrust());
    TEST_ASSERT_FALSE(io.step);
  }
  {
    FakeIo io;
    P1MotionController controller(io);
    uint32_t nowUs = 0;
    establishHome(controller, io, nowUs);
    io.home = false;
    TEST_ASSERT_EQUAL(P1PrepareResult::READY,
                      controller.prepareMoveAbsolute(10));
    TEST_ASSERT_TRUE(controller.start(nowUs));
    TEST_ASSERT_TRUE(controller.abort());
    TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);
    TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED,
                      controller.positionTrust());
  }
}

void test_abort_while_step_high_forces_step_low() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = 0;
  establishHome(controller, io, nowUs);
  io.home = false;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY,
                    controller.prepareMoveAbsolute(10));
  TEST_ASSERT_TRUE(controller.start(nowUs));
  reachFirstRise(nowUs);
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_TRUE(io.step);
  TEST_ASSERT_TRUE(controller.abort());
  TEST_ASSERT_FALSE(io.step);
  TEST_ASSERT_EQUAL(P1MotionState::IDLE, controller.state());
  TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED, controller.positionTrust());
}

void test_abort_after_completion_does_not_corrupt_trusted_position() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = 0;
  establishHome(controller, io, nowUs);
  io.home = false;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareMoveAbsolute(1));
  TEST_ASSERT_TRUE(controller.start(nowUs));
  reachFirstRise(nowUs);
  TEST_ASSERT_EQUAL(P1MotionResult::COMPLETED,
                    runOnePulse(controller, io, nowUs));
  TEST_ASSERT_FALSE(controller.abort());
  TEST_ASSERT_EQUAL(P1PositionTrust::TRUSTED, controller.positionTrust());
  TEST_ASSERT_EQUAL_UINT16(1, controller.positionSteps());
}

void test_full_pulse_sequence_crosses_micros_wraparound() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = UINT32_MAX - 2;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(nowUs));
  reachFirstRise(nowUs);
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_TRUE(io.step);
  nowUs += kP1StepHighUs;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_FALSE(io.step);
  nowUs += kP1StepIntervalUs - kP1StepHighUs;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_TRUE(io.step);
  TEST_ASSERT_EQUAL_UINT32(2, io.risingEdges);
}

void test_delayed_updates_do_not_emit_catch_up_pulses() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = 0;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(nowUs));
  nowUs = 100000;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_EQUAL_UINT32(1, io.risingEdges);
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_EQUAL_UINT32(1, io.risingEdges);
  nowUs += 100000;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_FALSE(io.step);
  TEST_ASSERT_EQUAL_UINT32(1, io.risingEdges);
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_EQUAL_UINT32(1, io.risingEdges);
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_boot_is_untrusted_and_prepare_has_no_physical_side_effect);
  RUN_TEST(test_direction_setup_precedes_first_step_rise);
  RUN_TEST(test_home_requires_stable_active_signal_and_rejects_one_sample_glitch);
  RUN_TEST(test_initial_active_home_is_confirmed_without_away_motion);
  RUN_TEST(test_trusted_home_releases_then_rehomes_with_stable_transitions);
  RUN_TEST(test_stuck_home_release_fails_closed);
  RUN_TEST(test_demo_home_search_is_bounded_to_accepted_full_span);
  RUN_TEST(test_absolute_move_rejects_zero_and_tracks_position);
  RUN_TEST(test_move_cannot_complete_inside_active_home_release_zone);
  RUN_TEST(test_move_requires_stable_home_release_and_ignores_one_sample_bounce);
  RUN_TEST(test_unexpected_home_during_absolute_move_invalidates_position);
  RUN_TEST(test_abort_during_home_release_search_and_absolute_motion);
  RUN_TEST(test_abort_while_step_high_forces_step_low);
  RUN_TEST(test_abort_after_completion_does_not_corrupt_trusted_position);
  RUN_TEST(test_full_pulse_sequence_crosses_micros_wraparound);
  RUN_TEST(test_delayed_updates_do_not_emit_catch_up_pulses);
  return UNITY_END();
}
