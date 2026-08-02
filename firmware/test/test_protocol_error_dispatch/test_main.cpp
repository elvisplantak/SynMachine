#include <unity.h>

#include <stdio.h>
#include <string.h>

#include "protocol/NoMotionDispatcher.h"
#include "protocol/ProtocolErrorWriter.h"

using namespace labforge;

namespace {

constexpr char NONCE[] = "123e4567-e89b-12d3-a456-426614174000";
constexpr char OTHER_NONCE[] = "223e4567-e89b-12d3-a456-426614174000";
constexpr char REQUEST_ID[] = "423e4567-e89b-12d3-a456-426614174003";
constexpr char OPERATION_ID[] = "323e4567-e89b-12d3-a456-426614174002";
constexpr BootIdentityResult TRUSTED{true, 7, IdentityFailureReason::NONE};

DispatchResult dispatch(NoMotionDispatcher& dispatcher, SessionState& session,
                        const BootIdentityResult& identity, const char* frame,
                        uint8_t* output, size_t capacity) {
  memset(output, 0, capacity);
  return dispatcher.dispatch(reinterpret_cast<const uint8_t*>(frame),
                             strlen(frame), identity, session, output, capacity);
}

void assertSingleFrame(const uint8_t* output, size_t length) {
  TEST_ASSERT_GREATER_THAN_UINT32(0, length);
  TEST_ASSERT_EQUAL_UINT8('\n', output[length - 1]);
  size_t lineFeeds = 0;
  for (size_t i = 0; i < length; ++i) {
    if (output[i] == '\n') ++lineFeeds;
  }
  TEST_ASSERT_EQUAL_UINT32(1, lineFeeds);
}

void test_complete_hello_then_status_path() {
  NoMotionDispatcher dispatcher;
  SessionState session;
  uint8_t output[kProtocolErrorFrameCapacity];
  char frame[256];
  snprintf(frame, sizeof(frame),
           "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO\","
           "\"backend_session_nonce\":\"%s\"}", NONCE);
  DispatchResult result = dispatch(dispatcher, session, TRUSTED, frame, output,
                                   sizeof(output));
  TEST_ASSERT_EQUAL(ParseStatus::VALID_MESSAGE, result.parseStatus);
  assertSingleFrame(output, result.outputLength);
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), "\"type\":\"HELLO_OK\""));
  TEST_ASSERT_TRUE(session.active());

  snprintf(frame, sizeof(frame),
           "{\"protocol\":\"LABFORGE/1\",\"type\":\"QUERY_STATUS\","
           "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":7,"
           "\"request_id\":\"%s\"}", NONCE, REQUEST_ID);
  result = dispatch(dispatcher, session, TRUSTED, frame, output, sizeof(output));
  TEST_ASSERT_EQUAL(ParseStatus::VALID_MESSAGE, result.parseStatus);
  assertSingleFrame(output, result.outputLength);
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), "\"type\":\"STATUS\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), "\"controller_state\":\"PROTOCOL_ONLY\""));
}

void test_session_failures_are_correlated() {
  NoMotionDispatcher dispatcher;
  SessionState session;
  uint8_t output[kProtocolErrorFrameCapacity]{};
  char frame[256];
  snprintf(frame, sizeof(frame),
           "{\"protocol\":\"LABFORGE/1\",\"type\":\"QUERY_STATUS\","
           "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":7,"
           "\"request_id\":\"%s\"}", NONCE, REQUEST_ID);
  DispatchResult result = dispatch(dispatcher, session, TRUSTED, frame, output,
                                   sizeof(output));
  assertSingleFrame(output, result.outputLength);
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), "HANDSHAKE_REQUIRED"));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), REQUEST_ID));

  session.establish(OTHER_NONCE);
  result = dispatch(dispatcher, session, TRUSTED, frame, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), "STALE_SESSION"));

  session.establish(NONCE);
  char mismatch[256];
  snprintf(mismatch, sizeof(mismatch),
           "{\"protocol\":\"LABFORGE/1\",\"type\":\"QUERY_STATUS\","
           "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":8,"
           "\"request_id\":\"%s\"}", NONCE, REQUEST_ID);
  result = dispatch(dispatcher, session, TRUSTED, mismatch, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), "CONTROLLER_BOOT_MISMATCH"));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), "\"controller_boot_id\":7"));
}

void test_untrusted_query_boundary() {
  NoMotionDispatcher dispatcher;
  SessionState session;
  session.establish(NONCE);
  const BootIdentityResult untrusted{false, 0, IdentityFailureReason::VERIFY_FAILED};
  uint8_t output[kProtocolErrorFrameCapacity]{};
  char frame[256];
  snprintf(frame, sizeof(frame),
           "{\"protocol\":\"LABFORGE/1\",\"type\":\"QUERY_STATUS\","
           "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":null,"
           "\"request_id\":\"%s\"}", NONCE, REQUEST_ID);
  DispatchResult result = dispatch(dispatcher, session, untrusted, frame, output,
                                   sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), "\"type\":\"STATUS\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), "IDENTITY_UNTRUSTED"));

  snprintf(frame, sizeof(frame),
           "{\"protocol\":\"LABFORGE/1\",\"type\":\"QUERY_STATUS\","
           "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":1,"
           "\"request_id\":\"%s\"}", NONCE, REQUEST_ID);
  result = dispatch(dispatcher, session, untrusted, frame, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "CONTROLLER_IDENTITY_UNTRUSTED"));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"controller_boot_id\":null"));
}

void test_parser_errors_correlate_only_safe_identifiers() {
  NoMotionDispatcher dispatcher;
  SessionState session;
  session.establish(NONCE);
  uint8_t output[kProtocolErrorFrameCapacity]{};
  const char malformed[] = "{not-json";
  DispatchResult result = dispatch(dispatcher, session, TRUSTED, malformed,
                                   output, sizeof(output));
  TEST_ASSERT_EQUAL(ParseStatus::INVALID_MESSAGE, result.parseStatus);
  TEST_ASSERT_EQUAL_STRING(
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"PROTOCOL_ERROR\",\"error_code\":\"MALFORMED_MESSAGE\"}\n",
      reinterpret_cast<char*>(output));
  TEST_ASSERT_EQUAL_STRING(NONCE, session.nonce());

  const char invalidHello[] =
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO\","
      "\"backend_session_nonce\":\"123E4567-E89B-12D3-A456-426614174000\"}";
  result = dispatch(dispatcher, session, TRUSTED, invalidHello, output,
                    sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), "INVALID_FIELD"));
  TEST_ASSERT_EQUAL_STRING(NONCE, session.nonce());

  char invalidQuery[300];
  snprintf(invalidQuery, sizeof(invalidQuery),
           "{\"protocol\":\"LABFORGE/1\",\"type\":\"QUERY_STATUS\","
           "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":7,"
           "\"request_id\":\"%s\",\"extra\":1}", NONCE, REQUEST_ID);
  result = dispatch(dispatcher, session, TRUSTED, invalidQuery, output,
                    sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), "INVALID_FIELD"));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), REQUEST_ID));
  TEST_ASSERT_EQUAL_STRING(NONCE, session.nonce());

  char invalidCommand[400];
  snprintf(invalidCommand, sizeof(invalidCommand),
           "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\","
           "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":7,"
           "\"phase_execution_id\":\"phase-1\","
           "\"operation_command_id\":\"%s\",\"command\":\"bad\","
           "\"arguments\":{}}", NONCE, OPERATION_ID);
  result = dispatch(dispatcher, session, TRUSTED, invalidCommand, output,
                    sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), "INVALID_FIELD"));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), "phase-1"));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), OPERATION_ID));
  TEST_ASSERT_NULL(strstr(reinterpret_cast<char*>(output), "request_id"));
  TEST_ASSERT_EQUAL_STRING(NONCE, session.nonce());
}

void test_oversize_and_writer_failure_are_transactional() {
  NoMotionDispatcher dispatcher;
  SessionState session;
  uint8_t output[kProtocolErrorFrameCapacity]{};
  DispatchResult result = dispatcher.lineTooLong(TRUSTED, output, sizeof(output));
  TEST_ASSERT_EQUAL(ParseStatus::OVERSIZED_FRAME, result.parseStatus);
  TEST_ASSERT_EQUAL_STRING(
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"PROTOCOL_ERROR\",\"error_code\":\"LINE_TOO_LONG\"}\n",
      reinterpret_cast<char*>(output));

  ErrorCorrelation correlation{};
  correlation.kind = ErrorCorrelationKind::NONE;
  uint8_t guarded[100];
  memset(guarded, 0xA7, sizeof(guarded));
  size_t length = 123;
  TEST_ASSERT_FALSE(writeProtocolError(ProtocolErrorCode::MALFORMED_MESSAGE,
                                       correlation, TRUSTED, guarded + 1, 1,
                                       length));
  TEST_ASSERT_EQUAL_UINT32(0, length);
  for (size_t i = 0; i < sizeof(guarded); ++i) {
    TEST_ASSERT_EQUAL_UINT8(0xA7, guarded[i]);
  }

  char hello[160];
  snprintf(hello, sizeof(hello),
           "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO\","
           "\"backend_session_nonce\":\"%s\"}", NONCE);
  result = dispatch(dispatcher, session, TRUSTED, hello, guarded, 1);
  TEST_ASSERT_EQUAL_UINT32(0, result.outputLength);
  TEST_ASSERT_FALSE(session.active());
}

void test_exact_correlated_error_frames_and_all_codes() {
  ErrorCorrelation query{};
  query.kind = ErrorCorrelationKind::QUERY;
  strcpy(query.backendSessionNonce, NONCE);
  strcpy(query.requestId, REQUEST_ID);
  uint8_t output[kProtocolErrorFrameCapacity]{};
  size_t length = 0;
  TEST_ASSERT_TRUE(writeProtocolError(ProtocolErrorCode::STALE_SESSION, query,
                                      TRUSTED, output, sizeof(output), length));
  TEST_ASSERT_EQUAL_STRING(
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"PROTOCOL_ERROR\",\"backend_session_nonce\":\"123e4567-e89b-12d3-a456-426614174000\",\"controller_boot_id\":7,\"request_id\":\"423e4567-e89b-12d3-a456-426614174003\",\"error_code\":\"STALE_SESSION\"}\n",
      reinterpret_cast<char*>(output));

  ErrorCorrelation command{};
  command.kind = ErrorCorrelationKind::COMMAND;
  strcpy(command.backendSessionNonce, NONCE);
  strcpy(command.phaseExecutionId, "phase-1");
  strcpy(command.operationCommandId, OPERATION_ID);
  memset(output, 0, sizeof(output));
  const BootIdentityResult untrusted{false, 0, IdentityFailureReason::READ_FAILED};
  TEST_ASSERT_TRUE(writeProtocolError(ProtocolErrorCode::INVALID_FIELD, command,
                                      untrusted, output, sizeof(output), length));
  TEST_ASSERT_EQUAL_STRING(
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"PROTOCOL_ERROR\",\"backend_session_nonce\":\"123e4567-e89b-12d3-a456-426614174000\",\"controller_boot_id\":null,\"phase_execution_id\":\"phase-1\",\"operation_command_id\":\"323e4567-e89b-12d3-a456-426614174002\",\"error_code\":\"INVALID_FIELD\"}\n",
      reinterpret_cast<char*>(output));

  const ProtocolErrorCode codes[] = {
      ProtocolErrorCode::MALFORMED_MESSAGE,
      ProtocolErrorCode::LINE_TOO_LONG,
      ProtocolErrorCode::UNSUPPORTED_PROTOCOL_VERSION,
      ProtocolErrorCode::HANDSHAKE_REQUIRED,
      ProtocolErrorCode::STALE_SESSION,
      ProtocolErrorCode::CONTROLLER_BOOT_MISMATCH,
      ProtocolErrorCode::CONTROLLER_IDENTITY_UNTRUSTED,
      ProtocolErrorCode::MISSING_FIELD,
      ProtocolErrorCode::INVALID_FIELD,
      ProtocolErrorCode::UNSUPPORTED_MESSAGE_TYPE,
  };
  ErrorCorrelation none{};
  none.kind = ErrorCorrelationKind::NONE;
  for (ProtocolErrorCode code : codes) {
    memset(output, 0, sizeof(output));
    TEST_ASSERT_TRUE(writeProtocolError(code, none, TRUSTED, output,
                                        sizeof(output), length));
    assertSingleFrame(output, length);
  }
}

void test_valid_deferred_messages_intentionally_emit_nothing() {
  NoMotionDispatcher dispatcher;
  SessionState session;
  session.establish(NONCE);
  uint8_t output[kProtocolErrorFrameCapacity];
  char frame[400];
  snprintf(frame, sizeof(frame),
           "{\"protocol\":\"LABFORGE/1\",\"type\":\"QUERY_COMMAND\","
           "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":7,"
           "\"request_id\":\"%s\",\"operation_command_id\":\"%s\"}",
           NONCE, REQUEST_ID, OPERATION_ID);
  DispatchResult result = dispatch(dispatcher, session, TRUSTED, frame, output,
                                   sizeof(output));
  TEST_ASSERT_EQUAL(ParseStatus::VALID_MESSAGE, result.parseStatus);
  TEST_ASSERT_EQUAL_UINT32(0, result.outputLength);
  TEST_ASSERT_EQUAL_STRING(NONCE, session.nonce());
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_complete_hello_then_status_path);
  RUN_TEST(test_session_failures_are_correlated);
  RUN_TEST(test_untrusted_query_boundary);
  RUN_TEST(test_parser_errors_correlate_only_safe_identifiers);
  RUN_TEST(test_oversize_and_writer_failure_are_transactional);
  RUN_TEST(test_exact_correlated_error_frames_and_all_codes);
  RUN_TEST(test_valid_deferred_messages_intentionally_emit_nothing);
  return UNITY_END();
}
