#include <unity.h>

#include <stdio.h>
#include <string.h>

#include "protocol/MessageParser.h"
#include "protocol/PumpHomeContract.h"

using namespace labforge;

namespace {

InboundMessage parseCommand(const char* command, const char* arguments) {
  char frame[512];
  snprintf(frame, sizeof(frame),
           "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\","
           "\"backend_session_nonce\":\"123e4567-e89b-12d3-a456-426614174000\","
           "\"controller_boot_id\":7,\"phase_execution_id\":\"phase-1\","
           "\"operation_command_id\":\"323e4567-e89b-12d3-a456-426614174002\","
           "\"command\":\"%s\",\"arguments\":%s}",
           command, arguments);
  const ParseResult parsed = MessageParser().parse(
      reinterpret_cast<const uint8_t*>(frame), strlen(frame));
  TEST_ASSERT_EQUAL(ParseStatus::VALID_MESSAGE, parsed.status);
  return parsed.message;
}

void test_accepts_only_exact_p1_argument() {
  PumpHomeCommand command{};
  const InboundMessage message = parseCommand("PUMP_HOME", "{\"pump\":\"P1\"}");
  TEST_ASSERT_EQUAL(PumpHomeContractStatus::VALID,
                    parsePumpHome(message, command));
  TEST_ASSERT_EQUAL(PumpId::P1, command.pump);
  const CommandSemanticIdentity identity = semanticIdentity(command);
  TEST_ASSERT_EQUAL(CommandKind::PUMP_HOME, identity.command);
  TEST_ASSERT_EQUAL_UINT16(0, identity.targetSteps);
}

void test_rejects_wrong_pump_type_missing_and_extra_arguments() {
  const char* invalid[] = {
      "{}",
      "{\"pump\":\"P2\"}",
      "{\"pump\":1}",
      "{\"pump\":\"P1\",\"speed\":1}",
  };
  for (const char* arguments : invalid) {
    PumpHomeCommand command{};
    TEST_ASSERT_EQUAL(
        PumpHomeContractStatus::INVALID_ARGUMENTS,
        parsePumpHome(parseCommand("PUMP_HOME", arguments), command));
  }
}

void test_rejects_other_command_name() {
  PumpHomeCommand command{};
  TEST_ASSERT_EQUAL(
      PumpHomeContractStatus::UNSUPPORTED_COMMAND,
      parsePumpHome(parseCommand("FUTURE_COMMAND", "{\"pump\":\"P1\"}"),
                    command));
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_accepts_only_exact_p1_argument);
  RUN_TEST(test_rejects_wrong_pump_type_missing_and_extra_arguments);
  RUN_TEST(test_rejects_other_command_name);
  return UNITY_END();
}
