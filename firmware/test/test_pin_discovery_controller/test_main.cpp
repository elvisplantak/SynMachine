#include <unity.h>

#include "commissioning/PinDiscoveryController.h"

using namespace labforge;

namespace {

void test_no_command_can_emit_pulses_before_complete_arming_sequence() {
  PinDiscoveryController controller;
  TEST_ASSERT_EQUAL(PinDiscoveryStatus::NOT_ARMED,
                    controller.process("PULSE 1").status);
  TEST_ASSERT_EQUAL(PinDiscoveryStatus::SELECTION_REQUIRED,
                    controller.process("ARM").status);
  TEST_ASSERT_EQUAL(PinDiscoveryStatus::OK,
                    controller.process("SELECT A").status);
  TEST_ASSERT_EQUAL(PinDiscoveryStatus::DIRECTION_REQUIRED,
                    controller.process("ARM").status);
  TEST_ASSERT_EQUAL(PinDiscoveryStatus::OK,
                    controller.process("DIR LOW").status);
  TEST_ASSERT_EQUAL(PinDiscoveryStatus::NOT_ARMED,
                    controller.process("PULSE 1").status);
}

void test_candidate_pairs_are_narrow_and_explicit() {
  PinDiscoveryPins pins =
      PinDiscoveryController::pinsFor(PinDiscoveryPair::PAIR_A);
  TEST_ASSERT_EQUAL_UINT8(34, pins.step);
  TEST_ASSERT_EQUAL_UINT8(35, pins.direction);
  pins = PinDiscoveryController::pinsFor(PinDiscoveryPair::PAIR_B);
  TEST_ASSERT_EQUAL_UINT8(36, pins.step);
  TEST_ASSERT_EQUAL_UINT8(37, pins.direction);
}

void test_one_to_five_pulses_require_arming_and_consume_it() {
  PinDiscoveryController controller;
  controller.process("SELECT B");
  controller.process("DIR HIGH");
  controller.process("ARM");
  const PinDiscoveryResult result = controller.process("PULSE 5");
  TEST_ASSERT_EQUAL(PinDiscoveryStatus::OK, result.status);
  TEST_ASSERT_EQUAL(PinDiscoveryAction::EMIT_PULSES, result.action);
  TEST_ASSERT_EQUAL_UINT8(36, result.pins.step);
  TEST_ASSERT_EQUAL_UINT8(37, result.pins.direction);
  TEST_ASSERT_EQUAL(PinDiscoveryDirection::LOGIC_HIGH, result.direction);
  TEST_ASSERT_EQUAL_UINT8(5, result.pulseCount);
  TEST_ASSERT_FALSE(controller.armed());
  TEST_ASSERT_EQUAL(PinDiscoveryStatus::NOT_ARMED,
                    controller.process("PULSE 1").status);
}

void test_invalid_or_state_changing_commands_disarm() {
  PinDiscoveryController controller;
  controller.process("SELECT A");
  controller.process("DIR LOW");
  controller.process("ARM");
  TEST_ASSERT_TRUE(controller.armed());
  TEST_ASSERT_EQUAL(PinDiscoveryStatus::INVALID_COMMAND,
                    controller.process("UNKNOWN").status);
  TEST_ASSERT_FALSE(controller.armed());

  controller.process("ARM");
  controller.process("DIR HIGH");
  TEST_ASSERT_FALSE(controller.armed());
  controller.process("ARM");
  controller.process("SELECT B");
  TEST_ASSERT_FALSE(controller.armed());
  TEST_ASSERT_EQUAL(PinDiscoveryDirection::UNSET, controller.direction());
}

void test_invalid_pulse_counts_never_emit_and_disarm() {
  const char* invalid[] = {"PULSE 0", "PULSE 6", "PULSE -1", "PULSE 1x",
                           "PULSE"};
  for (const char* command : invalid) {
    PinDiscoveryController controller;
    controller.process("SELECT A");
    controller.process("DIR LOW");
    controller.process("ARM");
    const PinDiscoveryResult result = controller.process(command);
    TEST_ASSERT_EQUAL(PinDiscoveryStatus::INVALID_PULSE_COUNT, result.status);
    TEST_ASSERT_EQUAL(PinDiscoveryAction::NONE, result.action);
    TEST_ASSERT_FALSE(controller.armed());
  }
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_no_command_can_emit_pulses_before_complete_arming_sequence);
  RUN_TEST(test_candidate_pairs_are_narrow_and_explicit);
  RUN_TEST(test_one_to_five_pulses_require_arming_and_consume_it);
  RUN_TEST(test_invalid_or_state_changing_commands_disarm);
  RUN_TEST(test_invalid_pulse_counts_never_emit_and_disarm);
  return UNITY_END();
}
