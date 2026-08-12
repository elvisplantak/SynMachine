#include <unity.h>

#include <vector>

#include "actuator/CarouselMotionController.h"

using namespace labforge;

namespace {
class FakeIo : public CarouselMotionIo {
 public:
  void writeDirection(bool high) override { direction = high; ++directionWrites; }
  void writeStep(bool high) override { step = high; }
  void pulseStep(uint16_t highUs) override {
    ++pulses;
    pulseWidths.push_back(highUs);
    step = false;
  }
  bool direction = false;
  bool step = false;
  uint16_t directionWrites = 0;
  uint16_t pulses = 0;
  std::vector<uint16_t> pulseWidths;
};

class TimedIo : public FakeIo {
 public:
  void pulseStep(uint16_t highUs) override {
    FakeIo::pulseStep(highUs);
    pulseTimes.push_back(now);
  }
  uint32_t now = 0;
  std::vector<uint32_t> pulseTimes;
};

void runUntilDone(CarouselMotionController& controller, uint32_t& now) {
  for (uint16_t i = 0; i < 11000; ++i) {
    now += 7000;
    if (controller.update(now) == CarouselMotionResult::COMPLETED) return;
  }
  TEST_FAIL_MESSAGE("carousel did not complete");
}

void reference(CarouselMotionController& controller, uint8_t position,
               uint32_t now = 0) {
  TEST_ASSERT_EQUAL_INT(static_cast<int>(CarouselPrepareResult::READY),
                        static_cast<int>(controller.prepareSetReference(position)));
  TEST_ASSERT_TRUE(controller.start(now));
  TEST_ASSERT_EQUAL_INT(static_cast<int>(CarouselMotionResult::COMPLETED),
                        static_cast<int>(controller.update(now)));
}

void test_reference_is_motionless_and_trusts_position() {
  FakeIo io;
  CarouselMotionController controller(io);
  reference(controller, 17);
  TEST_ASSERT_EQUAL_UINT16(0, io.pulses);
  TEST_ASSERT_EQUAL_UINT16(0, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT8(17, controller.position());
  TEST_ASSERT_EQUAL_INT(static_cast<int>(CarouselPositionTrust::TRUSTED),
                        static_cast<int>(controller.positionTrust()));
}

void test_one_position_uses_confirmed_profile_and_pulse_count() {
  FakeIo io;
  CarouselMotionController controller(io);
  reference(controller, 1);
  TEST_ASSERT_EQUAL_INT(static_cast<int>(CarouselPrepareResult::READY),
                        static_cast<int>(controller.prepareMoveToPosition(2)));
  TEST_ASSERT_TRUE(controller.start(100));
  TEST_ASSERT_TRUE(io.direction);
  TEST_ASSERT_EQUAL_UINT16(0, io.pulses);
  TEST_ASSERT_EQUAL_INT(static_cast<int>(CarouselMotionResult::NONE),
                        static_cast<int>(controller.update(104)));
  TEST_ASSERT_EQUAL_UINT16(0, io.pulses);
  uint32_t now = 104;
  runUntilDone(controller, now);
  TEST_ASSERT_EQUAL_UINT16(250, io.pulses);
  TEST_ASSERT_EQUAL_UINT8(2, controller.position());
  for (uint16_t width : io.pulseWidths)
    TEST_ASSERT_EQUAL_UINT16(kCarouselStepHighUs, width);
}

void test_wrap_and_no_catch_up_burst() {
  FakeIo io;
  CarouselMotionController controller(io);
  reference(controller, 40);
  TEST_ASSERT_EQUAL_INT(static_cast<int>(CarouselPrepareResult::READY),
                        static_cast<int>(controller.prepareMoveToPosition(1)));
  TEST_ASSERT_TRUE(controller.start(0));
  controller.update(1000000);
  TEST_ASSERT_EQUAL_UINT16(1, io.pulses);
  uint32_t now = 1000000;
  runUntilDone(controller, now);
  TEST_ASSERT_EQUAL_UINT16(250, io.pulses);
}

void test_untrusted_move_is_rejected_and_abort_invalidates_started_move() {
  FakeIo io;
  CarouselMotionController controller(io);
  TEST_ASSERT_EQUAL_INT(static_cast<int>(CarouselPrepareResult::POSITION_UNTRUSTED),
                        static_cast<int>(controller.prepareMoveToPosition(2)));
  reference(controller, 1);
  TEST_ASSERT_EQUAL_INT(static_cast<int>(CarouselPrepareResult::READY),
                        static_cast<int>(controller.prepareMoveToPosition(3)));
  TEST_ASSERT_TRUE(controller.start(0));
  controller.update(5);
  TEST_ASSERT_TRUE(controller.abort());
  TEST_ASSERT_FALSE(io.step);
  TEST_ASSERT_EQUAL_INT(static_cast<int>(CarouselPositionTrust::UNTRUSTED),
                        static_cast<int>(controller.positionTrust()));
}

void test_profile_reaches_cruise_and_decelerates_symmetrically() {
  TimedIo io;
  CarouselMotionController controller(io);
  reference(controller, 1);
  TEST_ASSERT_EQUAL(CarouselPrepareResult::READY,
                    controller.prepareMoveToPosition(2));
  TEST_ASSERT_TRUE(controller.start(0));
  while (controller.busy() && io.now < 2000000UL) {
    ++io.now;
    controller.update(io.now);
  }
  TEST_ASSERT_EQUAL_UINT16(kCarouselPulsesPerPosition, io.pulseTimes.size());
  const uint32_t early = io.pulseTimes[2] - io.pulseTimes[1];
  const uint32_t middle = io.pulseTimes[126] - io.pulseTimes[125];
  const uint32_t late = io.pulseTimes[249] - io.pulseTimes[248];
  TEST_ASSERT_GREATER_THAN_UINT32(kCarouselCruiseIntervalUs, early);
  TEST_ASSERT_UINT32_WITHIN(10, kCarouselCruiseIntervalUs, middle);
  TEST_ASSERT_GREATER_THAN_UINT32(kCarouselCruiseIntervalUs, late);
}
}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_reference_is_motionless_and_trusts_position);
  RUN_TEST(test_one_position_uses_confirmed_profile_and_pulse_count);
  RUN_TEST(test_wrap_and_no_catch_up_burst);
  RUN_TEST(test_untrusted_move_is_rejected_and_abort_invalidates_started_move);
  RUN_TEST(test_profile_reaches_cruise_and_decelerates_symmetrically);
  return UNITY_END();
}
