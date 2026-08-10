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
  unsigned risingEdges = 0;

  bool homeActive() const override { return home; }
  void writeDirection(bool high) override {
    direction = high;
    ++directionWrites;
  }
  void writeStep(bool high) override {
    if (high && !step) ++risingEdges;
    step = high;
  }
};

P1MotionResult runOnePulse(P1MotionController& controller, uint32_t& nowUs) {
  P1MotionResult result = controller.update(nowUs);
  nowUs += kP1StepHighUs;
  result = controller.update(nowUs);
  nowUs += kP1StepIntervalUs - kP1StepHighUs;
  return result;
}

void establishHome(P1MotionController& controller, FakeIo& io,
                   uint32_t& nowUs) {
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(nowUs));
  TEST_ASSERT_FALSE(io.direction);
  runOnePulse(controller, nowUs);
  io.home = true;
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
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);

  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_EQUAL(P1MotionState::PREPARED_HOME, controller.state());
  TEST_ASSERT_EQUAL_UINT32(0, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);
}

void test_start_crosses_boundary_and_home_establishes_zero() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = 100;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(nowUs));
  TEST_ASSERT_EQUAL_UINT32(1, io.directionWrites);
  TEST_ASSERT_FALSE(io.direction);
  TEST_ASSERT_EQUAL(P1MotionState::SEARCHING_HOME, controller.state());

  TEST_ASSERT_EQUAL(P1MotionResult::NONE, runOnePulse(controller, nowUs));
  io.home = true;
  TEST_ASSERT_EQUAL(P1MotionResult::COMPLETED, controller.update(nowUs));
  TEST_ASSERT_EQUAL(P1MotionState::IDLE, controller.state());
  TEST_ASSERT_EQUAL(P1PositionTrust::TRUSTED, controller.positionTrust());
  TEST_ASSERT_EQUAL_UINT16(0, controller.positionSteps());
}

void test_home_releases_active_switch_then_searches_toward_home() {
  FakeIo io;
  io.home = true;
  P1MotionController controller(io);
  uint32_t nowUs = 0;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(nowUs));
  TEST_ASSERT_TRUE(io.direction);
  TEST_ASSERT_EQUAL(P1MotionState::RELEASING_HOME, controller.state());

  TEST_ASSERT_EQUAL(P1MotionResult::NONE, runOnePulse(controller, nowUs));
  io.home = false;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, runOnePulse(controller, nowUs));
  TEST_ASSERT_FALSE(io.direction);
  TEST_ASSERT_EQUAL(P1MotionState::SEARCHING_HOME, controller.state());

  io.home = true;
  TEST_ASSERT_EQUAL(P1MotionResult::COMPLETED, controller.update(nowUs));
  TEST_ASSERT_EQUAL(P1PositionTrust::TRUSTED, controller.positionTrust());
}

void test_stuck_home_switch_fails_closed_without_trusting_position() {
  FakeIo io;
  io.home = true;
  P1MotionController controller(io);
  uint32_t nowUs = 0;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(nowUs));
  P1MotionResult result = P1MotionResult::NONE;
  for (uint16_t i = 0; i < kP1HomeReleaseMaximumSteps; ++i)
    result = runOnePulse(controller, nowUs);
  TEST_ASSERT_EQUAL(P1MotionResult::HOME_SWITCH_STUCK, result);
  TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED, controller.positionTrust());
  TEST_ASSERT_EQUAL(P1MotionState::IDLE, controller.state());
  TEST_ASSERT_FALSE(io.step);
}

void test_home_search_is_bounded_by_confirmed_mechanical_range() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = 0;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(nowUs));
  P1MotionResult result = P1MotionResult::NONE;
  for (uint32_t i = 0; i < kP1MaximumAbsoluteSteps; ++i)
    result = runOnePulse(controller, nowUs);
  TEST_ASSERT_EQUAL(P1MotionResult::MOTION_TIMEOUT, result);
  TEST_ASSERT_EQUAL_UINT32(kP1MaximumAbsoluteSteps, io.risingEdges);
  TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED, controller.positionTrust());
}

void test_absolute_move_requires_home_and_tracks_position() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = 0;
  establishHome(controller, io, nowUs);

  TEST_ASSERT_EQUAL(P1PrepareResult::TARGET_REQUIRES_HOME,
                    controller.prepareMoveAbsolute(0));
  TEST_ASSERT_EQUAL(P1PrepareResult::INVALID_TARGET,
                    controller.prepareMoveAbsolute(20501));
  TEST_ASSERT_EQUAL(P1PrepareResult::READY,
                    controller.prepareMoveAbsolute(3));
  TEST_ASSERT_TRUE(controller.start(nowUs));
  TEST_ASSERT_TRUE(io.direction);
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, runOnePulse(controller, nowUs));
  io.home = false;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, runOnePulse(controller, nowUs));
  TEST_ASSERT_EQUAL(P1MotionResult::COMPLETED,
                    runOnePulse(controller, nowUs));
  TEST_ASSERT_EQUAL_UINT16(3, controller.positionSteps());
  TEST_ASSERT_EQUAL(P1PositionTrust::TRUSTED, controller.positionTrust());

  TEST_ASSERT_EQUAL(P1PrepareResult::READY,
                    controller.prepareMoveAbsolute(1));
  TEST_ASSERT_TRUE(controller.start(nowUs));
  TEST_ASSERT_FALSE(io.direction);
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, runOnePulse(controller, nowUs));
  TEST_ASSERT_EQUAL(P1MotionResult::COMPLETED,
                    runOnePulse(controller, nowUs));
  TEST_ASSERT_EQUAL_UINT16(1, controller.positionSteps());
}

void test_unexpected_home_during_absolute_move_invalidates_position() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = 0;
  establishHome(controller, io, nowUs);
  TEST_ASSERT_EQUAL(P1PrepareResult::READY,
                    controller.prepareMoveAbsolute(10));
  TEST_ASSERT_TRUE(controller.start(nowUs));
  runOnePulse(controller, nowUs);
  io.home = false;
  runOnePulse(controller, nowUs);
  io.home = true;
  TEST_ASSERT_EQUAL(P1MotionResult::HOME_SWITCH_UNEXPECTED,
                    controller.update(nowUs));
  TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED, controller.positionTrust());
  TEST_ASSERT_FALSE(io.step);
}

void test_move_from_zero_allows_only_bounded_initial_home_release() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = 0;
  establishHome(controller, io, nowUs);
  TEST_ASSERT_TRUE(io.home);
  TEST_ASSERT_EQUAL(P1PrepareResult::READY,
                    controller.prepareMoveAbsolute(300));
  TEST_ASSERT_TRUE(controller.start(nowUs));
  P1MotionResult result = P1MotionResult::NONE;
  for (uint16_t i = 0; i < kP1HomeReleaseMaximumSteps; ++i)
    result = runOnePulse(controller, nowUs);
  TEST_ASSERT_EQUAL(P1MotionResult::HOME_SWITCH_STUCK, result);
  TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED, controller.positionTrust());
}

void test_micros_wraparound_preserves_pulse_schedule() {
  FakeIo io;
  P1MotionController controller(io);
  uint32_t nowUs = UINT32_MAX - 10;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(nowUs));
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_TRUE(io.step);
  nowUs += kP1StepHighUs;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(nowUs));
  TEST_ASSERT_FALSE(io.step);
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_boot_is_untrusted_and_prepare_has_no_physical_side_effect);
  RUN_TEST(test_start_crosses_boundary_and_home_establishes_zero);
  RUN_TEST(test_home_releases_active_switch_then_searches_toward_home);
  RUN_TEST(test_stuck_home_switch_fails_closed_without_trusting_position);
  RUN_TEST(test_home_search_is_bounded_by_confirmed_mechanical_range);
  RUN_TEST(test_absolute_move_requires_home_and_tracks_position);
  RUN_TEST(test_unexpected_home_during_absolute_move_invalidates_position);
  RUN_TEST(test_move_from_zero_allows_only_bounded_initial_home_release);
  RUN_TEST(test_micros_wraparound_preserves_pulse_schedule);
  return UNITY_END();
}
