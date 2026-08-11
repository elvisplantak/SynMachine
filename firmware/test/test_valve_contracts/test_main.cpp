#include <unity.h>

#include <cstdio>
#include <cstring>
#include <initializer_list>

#include "protocol/MessageParser.h"
#include "protocol/ValveHomeContract.h"
#include "protocol/ValveSetPositionContract.h"

using namespace labforge;

namespace {

InboundMessage parseCommand(const char* command, const char* arguments) {
  char frame[512];
  std::snprintf(
      frame, sizeof(frame),
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\","
      "\"backend_session_nonce\":\"123e4567-e89b-12d3-a456-426614174000\","
      "\"controller_boot_id\":7,\"phase_execution_id\":\"phase-1\","
      "\"operation_command_id\":\"323e4567-e89b-12d3-a456-426614174002\","
      "\"command\":\"%s\",\"arguments\":%s}", command, arguments);
  const ParseResult parsed = MessageParser().parse(
      reinterpret_cast<const uint8_t*>(frame), std::strlen(frame));
  TEST_ASSERT_EQUAL(ParseStatus::VALID_MESSAGE, parsed.status);
  return parsed.message;
}

void test_valve_home_accepts_only_v1_through_v8() {
  for (char index = '1'; index <= '8'; ++index) {
    char arguments[] = "{\"valve\":\"V1\"}";
    arguments[11] = index;
    ValveHomeCommand command{};
    TEST_ASSERT_EQUAL(
        ValveHomeContractStatus::VALID,
        parseValveHome(parseCommand("VALVE_HOME", arguments), command));
    TEST_ASSERT_EQUAL(static_cast<uint8_t>(index - '0'),
                      static_cast<uint8_t>(command.valve));
  }
  ValveHomeCommand command{};
  TEST_ASSERT_EQUAL(
      ValveHomeContractStatus::INVALID_ARGUMENTS,
      parseValveHome(parseCommand("VALVE_HOME", "{\"valve\":\"V9\"}"),
                     command));
}

void test_valve_position_accepts_only_canonical_angles() {
  for (int degrees : {0, 90, 180}) {
    char arguments[96];
    std::snprintf(arguments, sizeof(arguments),
                  "{\"position_degrees\":%d,\"valve\":\"V8\"}", degrees);
    ValveSetPositionCommand command{};
    TEST_ASSERT_EQUAL(
        ValveSetPositionContractStatus::VALID,
        parseValveSetPosition(
            parseCommand("VALVE_SET_POSITION", arguments), command));
    TEST_ASSERT_EQUAL(degrees, command.targetDegrees);
  }
  ValveSetPositionCommand command{};
  TEST_ASSERT_EQUAL(
      ValveSetPositionContractStatus::INVALID_ARGUMENTS,
      parseValveSetPosition(
          parseCommand("VALVE_SET_POSITION",
                       "{\"valve\":\"V1\",\"position_degrees\":45}"),
          command));
}

void test_valve_semantic_identity_distinguishes_valve_and_position() {
  const CommandSemanticIdentity home =
      semanticIdentity(ValveHomeCommand{ValveId::V2});
  const CommandSemanticIdentity positioned =
      semanticIdentity(ValveSetPositionCommand{ValveId::V2, 90});
  TEST_ASSERT_FALSE(commandSemanticIdentityEqual(home, positioned));
  TEST_ASSERT_EQUAL(ValveId::V2, positioned.valve);
  TEST_ASSERT_EQUAL_UINT16(90, positioned.targetDegrees);
}

}  // namespace

void setUp() {}
void tearDown() {}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_valve_home_accepts_only_v1_through_v8);
  RUN_TEST(test_valve_position_accepts_only_canonical_angles);
  RUN_TEST(test_valve_semantic_identity_distinguishes_valve_and_position);
  return UNITY_END();
}
