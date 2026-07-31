#include <unity.h>

#include <stdio.h>
#include <string.h>

#include "protocol/MessageParser.h"

using namespace labforge;

static const char* NONCE = "123e4567-e89b-12d3-a456-426614174000";
static const char* OPERATION = "323e4567-e89b-12d3-a456-426614174002";
static const char* REQUEST = "423e4567-e89b-12d3-a456-426614174003";

ParseResult parse(const char* json) {
  return MessageParser().parse(reinterpret_cast<const uint8_t*>(json), strlen(json));
}

void assertValid(const char* json, MessageType type) {
  const ParseResult result = parse(json);
  TEST_ASSERT_EQUAL(ParseStatus::VALID_MESSAGE, result.status);
  TEST_ASSERT_EQUAL(type, result.message.type);
}

void assertError(const char* json, ProtocolErrorCode error) {
  const ParseResult result = parse(json);
  TEST_ASSERT_EQUAL(ParseStatus::INVALID_MESSAGE, result.status);
  TEST_ASSERT_EQUAL(error, result.error);
}

void test_all_four_minimal_messages() {
  char json[512];
  snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO\",\"backend_session_nonce\":\"%s\"}", NONCE);
  assertValid(json, MessageType::HELLO);
  snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"QUERY_STATUS\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":4294967295,\"request_id\":\"%s\"}", NONCE, REQUEST);
  assertValid(json, MessageType::QUERY_STATUS);
  snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"QUERY_COMMAND\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":0,\"request_id\":\"%s\",\"operation_command_id\":\"%s\"}", NONCE, REQUEST, OPERATION);
  assertValid(json, MessageType::QUERY_COMMAND);
  snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":1,\"phase_execution_id\":\"phase-1\",\"operation_command_id\":\"%s\",\"command\":\"FUTURE_COMMAND\",\"arguments\":{\"text\":\"ž\",\"count\":2,\"enabled\":true}}", NONCE, OPERATION);
  assertValid(json, MessageType::COMMAND);
}

void test_envelope_error_classification() {
  assertError("{\"type\":\"HELLO\"}", ProtocolErrorCode::MISSING_FIELD);
  assertError("{\"protocol\":\"LABFORGE/1\"}", ProtocolErrorCode::MISSING_FIELD);
  assertError("{\"protocol\":1,\"type\":\"HELLO\"}", ProtocolErrorCode::INVALID_FIELD);
  assertError("{\"protocol\":\"LABFORGE/2\",\"type\":\"HELLO\"}", ProtocolErrorCode::UNSUPPORTED_PROTOCOL_VERSION);
  assertError("{\"protocol\":\"LABFORGE/1\",\"type\":1}", ProtocolErrorCode::INVALID_FIELD);
  assertError("{\"protocol\":\"LABFORGE/1\",\"type\":\"BOUNDED_UNKNOWN\"}", ProtocolErrorCode::UNSUPPORTED_MESSAGE_TYPE);
  assertError("{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO\",\"backend_session_nonce\":\"123e4567-e89b-12d3-a456-426614174000\",\"extra\":1}", ProtocolErrorCode::INVALID_FIELD);
}

void test_identifier_and_boot_id_bounds() {
  assertError("{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO\",\"backend_session_nonce\":\"123E4567-E89B-12D3-A456-426614174000\"}", ProtocolErrorCode::INVALID_FIELD);
  char json[512];
  snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"QUERY_STATUS\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":-1,\"request_id\":\"%s\"}", NONCE, REQUEST);
  assertError(json, ProtocolErrorCode::INVALID_FIELD);
  snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"QUERY_STATUS\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":4294967296,\"request_id\":\"%s\"}", NONCE, REQUEST);
  assertError(json, ProtocolErrorCode::INVALID_FIELD);
}

void test_command_schema_rejections() {
  char json[700];
  const char* formats[] = {
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":1,\"phase_execution_id\":\"bad space\",\"operation_command_id\":\"%s\",\"command\":\"GO\",\"arguments\":{}}",
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":1,\"phase_execution_id\":\"phase\",\"operation_command_id\":\"%s\",\"command\":\"lower\",\"arguments\":{}}",
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":1,\"phase_execution_id\":\"phase\",\"operation_command_id\":\"%s\",\"command\":\"GO\",\"arguments\":{\"x\":null}}"};
  for (const char* format : formats) {
    snprintf(json, sizeof(json), format, NONCE, OPERATION);
    assertError(json, ProtocolErrorCode::INVALID_FIELD);
  }
  snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":1,\"phase_execution_id\":\"phase\",\"operation_command_id\":\"%s\",\"command\":\"GO\",\"arguments\":{\"a\":1,\"b\":2,\"c\":3,\"d\":4,\"e\":5,\"f\":6,\"g\":7,\"h\":8,\"i\":9}}", NONCE, OPERATION);
  assertError(json, ProtocolErrorCode::INVALID_FIELD);
  char longValue[66];
  memset(longValue, 'x', 65);
  longValue[65] = '\0';
  snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":1,\"phase_execution_id\":\"phase\",\"operation_command_id\":\"%s\",\"command\":\"GO\",\"arguments\":{\"x\":\"%s\"}}", NONCE, OPERATION, longValue);
  assertError(json, ProtocolErrorCode::INVALID_FIELD);
}

void test_argument_key_type_and_boolean_semantics() {
  char json[512];
  snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":1,\"phase_execution_id\":\"phase\",\"operation_command_id\":\"%s\",\"command\":\"GO\",\"arguments\":{\"ž\":1}}", NONCE, OPERATION);
  assertError(json, ProtocolErrorCode::INVALID_FIELD);
  snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":1,\"phase_execution_id\":\"phase\",\"operation_command_id\":\"%s\",\"command\":\"GO\",\"arguments\":{\"enabled\":true}}", NONCE, OPERATION);
  const ParseResult result = parse(json);
  TEST_ASSERT_EQUAL(ParseStatus::VALID_MESSAGE, result.status);
  TEST_ASSERT_EQUAL_UINT8(1, result.message.argumentCount);
  TEST_ASSERT_EQUAL(ArgumentType::BOOLEAN, result.message.arguments[0].type);
  TEST_ASSERT_TRUE(result.message.arguments[0].value.booleanValue);
}

void test_signed_integer_and_boot_id_boundaries() {
  char json[512];
  snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":1,\"phase_execution_id\":\"phase\",\"operation_command_id\":\"%s\",\"command\":\"GO\",\"arguments\":{\"minimum\":-9223372036854775808,\"maximum\":9223372036854775807}}", NONCE, OPERATION);
  ParseResult result = parse(json);
  TEST_ASSERT_EQUAL(ParseStatus::VALID_MESSAGE, result.status);
  TEST_ASSERT_EQUAL_INT64(INT64_MIN, result.message.arguments[0].value.integerValue);
  TEST_ASSERT_EQUAL_INT64(INT64_MAX, result.message.arguments[1].value.integerValue);

  snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":1,\"phase_execution_id\":\"phase\",\"operation_command_id\":\"%s\",\"command\":\"GO\",\"arguments\":{\"value\":-9223372036854775809}}", NONCE, OPERATION);
  assertError(json, ProtocolErrorCode::INVALID_FIELD);
  snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":1,\"phase_execution_id\":\"phase\",\"operation_command_id\":\"%s\",\"command\":\"GO\",\"arguments\":{\"value\":9223372036854775808}}", NONCE, OPERATION);
  assertError(json, ProtocolErrorCode::INVALID_FIELD);
  snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":1,\"phase_execution_id\":\"phase\",\"operation_command_id\":\"%s\",\"command\":\"GO\",\"arguments\":{\"value\":1.0}}", NONCE, OPERATION);
  assertError(json, ProtocolErrorCode::INVALID_FIELD);

  snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"QUERY_STATUS\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":4294967295,\"request_id\":\"%s\"}", NONCE, REQUEST);
  result = parse(json);
  TEST_ASSERT_EQUAL(ParseStatus::VALID_MESSAGE, result.status);
  TEST_ASSERT_EQUAL_UINT32(UINT32_MAX, result.message.controllerBootId);
  snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"QUERY_STATUS\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":4294967296,\"request_id\":\"%s\"}", NONCE, REQUEST);
  assertError(json, ProtocolErrorCode::INVALID_FIELD);
}

void test_string_content_unicode_bounds_and_owned_lifetime() {
  char frame[512];
  snprintf(frame, sizeof(frame), "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":1,\"phase_execution_id\":\"phase\",\"operation_command_id\":\"%s\",\"command\":\"GO\",\"arguments\":{\"value\":\"NaN // not a comment apostrophe '\"}}", NONCE, OPERATION);
  ParseResult result = MessageParser().parse(reinterpret_cast<const uint8_t*>(frame), strlen(frame));
  TEST_ASSERT_EQUAL(ParseStatus::VALID_MESSAGE, result.status);
  memset(frame, 'x', sizeof(frame));
  TEST_ASSERT_EQUAL_STRING("NaN // not a comment apostrophe '", result.message.arguments[0].value.stringValue);
  TEST_ASSERT_EQUAL_STRING("value", result.message.arguments[0].key);

  snprintf(frame, sizeof(frame), "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":1,\"phase_execution_id\":\"phase\",\"operation_command_id\":\"%s\",\"command\":\"GO\",\"arguments\":{\"value\":\"\\ud83d\\ude00\\ud83d\\ude00\\ud83d\\ude00\\ud83d\\ude00\\ud83d\\ude00\\ud83d\\ude00\\ud83d\\ude00\\ud83d\\ude00\\ud83d\\ude00\\ud83d\\ude00\\ud83d\\ude00\\ud83d\\ude00\\ud83d\\ude00\\ud83d\\ude00\\ud83d\\ude00\\ud83d\\ude00\"}}", NONCE, OPERATION);
  TEST_ASSERT_EQUAL(ParseStatus::VALID_MESSAGE, parse(frame).status);
  const size_t used = strlen(frame);
  strcpy(frame + used - 3, "\\ud83d\\ude00\"}}");
  assertError(frame, ProtocolErrorCode::INVALID_FIELD);
}

void test_malformed_then_valid_parser_recovery() {
  assertError("{\"protocol\":", ProtocolErrorCode::MALFORMED_MESSAGE);
  char json[160];
  snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO\",\"backend_session_nonce\":\"%s\"}", NONCE);
  assertValid(json, MessageType::HELLO);
}

void test_unsupported_nesting_is_consistently_malformed() {
  char json[512];
  const char* arguments[] = {"{\"value\":{}}", "{\"value\":{\"x\":1}}",
                             "{\"value\":[]}", "{\"value\":[1]}"};
  for (const char* nestedArguments : arguments) {
    snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\",\"backend_session_nonce\":\"%s\",\"controller_boot_id\":1,\"phase_execution_id\":\"phase\",\"operation_command_id\":\"%s\",\"command\":\"GO\",\"arguments\":%s}", NONCE, OPERATION, nestedArguments);
    assertError(json, ProtocolErrorCode::MALFORMED_MESSAGE);
  }
  snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO\",\"backend_session_nonce\":\"%s\"}", NONCE);
  assertValid(json, MessageType::HELLO);
}

void test_escaped_nul_duplicate_rejects_then_parser_recovers() {
  assertError("{\"protocol\":\"LABFORGE/1\",\"type\\u0000x\":1,\"type\\u0000x\":2}",
              ProtocolErrorCode::MALFORMED_MESSAGE);
  char json[160];
  snprintf(json, sizeof(json), "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO\",\"backend_session_nonce\":\"%s\"}", NONCE);
  assertValid(json, MessageType::HELLO);
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_all_four_minimal_messages);
  RUN_TEST(test_envelope_error_classification);
  RUN_TEST(test_identifier_and_boot_id_bounds);
  RUN_TEST(test_command_schema_rejections);
  RUN_TEST(test_argument_key_type_and_boolean_semantics);
  RUN_TEST(test_signed_integer_and_boot_id_boundaries);
  RUN_TEST(test_string_content_unicode_bounds_and_owned_lifetime);
  RUN_TEST(test_malformed_then_valid_parser_recovery);
  RUN_TEST(test_unsupported_nesting_is_consistently_malformed);
  RUN_TEST(test_escaped_nul_duplicate_rejects_then_parser_recovers);
  return UNITY_END();
}
