#include <unity.h>

#include <cstdio>
#include <cstring>
#include <initializer_list>

#include "protocol/ColumnBottomValveContract.h"
#include "protocol/MessageParser.h"

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
      "\"command\":\"%s\",\"arguments\":%s}",
      command, arguments);
  const ParseResult parsed = MessageParser().parse(
      reinterpret_cast<const uint8_t*>(frame), std::strlen(frame));
  TEST_ASSERT_EQUAL(ParseStatus::VALID_MESSAGE, parsed.status);
  return parsed.message;
}

void test_home_requires_empty_arguments() {
  ColumnBottomValveCommand command{};
  TEST_ASSERT_EQUAL(ColumnValveContractStatus::VALID,
                    parseColumnBottomValve(
                        parseCommand("COLUMN_BOTTOM_VALVE_HOME", "{}"),
                        command));
  TEST_ASSERT_EQUAL(CommandKind::COLUMN_BOTTOM_VALVE_HOME, command.kind);
  TEST_ASSERT_EQUAL(ColumnValveContractStatus::INVALID_ARGUMENTS,
                    parseColumnBottomValve(
                        parseCommand("COLUMN_BOTTOM_VALVE_HOME",
                                     "{\"extra\":1}"),
                        command));
}

void test_position_accepts_only_confirmed_4_and_94_degrees() {
  for (int degrees : {4, 94}) {
    char arguments[64];
    std::snprintf(arguments, sizeof(arguments),
                  "{\"position_degrees\":%d}", degrees);
    ColumnBottomValveCommand command{};
    TEST_ASSERT_EQUAL(
        ColumnValveContractStatus::VALID,
        parseColumnBottomValve(
            parseCommand("COLUMN_BOTTOM_VALVE_SET_POSITION", arguments),
            command));
    TEST_ASSERT_EQUAL_UINT16(degrees, command.targetDegrees);
  }
  for (const char* arguments : {
           "{}", "{\"position_degrees\":0}",
           "{\"position_degrees\":90}", "{\"position_degrees\":180}",
           "{\"position_degrees\":\"94\"}",
           "{\"position_degrees\":94,\"extra\":1}",
       }) {
    ColumnBottomValveCommand command{};
    TEST_ASSERT_EQUAL(
        ColumnValveContractStatus::INVALID_ARGUMENTS,
        parseColumnBottomValve(
            parseCommand("COLUMN_BOTTOM_VALVE_SET_POSITION", arguments),
            command));
  }
}

void test_semantic_identity_distinguishes_home_closed_and_open() {
  const CommandSemanticIdentity home = semanticIdentity(
      ColumnBottomValveCommand{CommandKind::COLUMN_BOTTOM_VALVE_HOME, 0});
  const CommandSemanticIdentity closed = semanticIdentity(
      ColumnBottomValveCommand{
          CommandKind::COLUMN_BOTTOM_VALVE_SET_POSITION, 4});
  const CommandSemanticIdentity open = semanticIdentity(
      ColumnBottomValveCommand{
          CommandKind::COLUMN_BOTTOM_VALVE_SET_POSITION, 94});
  TEST_ASSERT_FALSE(commandSemanticIdentityEqual(home, closed));
  TEST_ASSERT_FALSE(commandSemanticIdentityEqual(closed, open));
}

}  // namespace

void setUp() {}
void tearDown() {}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_home_requires_empty_arguments);
  RUN_TEST(test_position_accepts_only_confirmed_4_and_94_degrees);
  RUN_TEST(test_semantic_identity_distinguishes_home_closed_and_open);
  return UNITY_END();
}
