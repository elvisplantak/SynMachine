#include <unity.h>

#include <limits.h>
#include <string.h>

#include "protocol/HelloOkWriter.h"
#include "protocol/MessageParser.h"
#include "protocol/SessionState.h"

using namespace labforge;

namespace {

constexpr char NONCE[] = "123e4567-e89b-12d3-a456-426614174000";
constexpr char OTHER_NONCE[] = "223e4567-e89b-12d3-a456-426614174000";

void assertFrame(const BootIdentityResult& identity, const char* expected) {
  uint8_t guarded[kHelloOkFrameCapacity + 2];
  memset(guarded, 0xCC, sizeof(guarded));
  size_t length = 99;
  TEST_ASSERT_TRUE(writeHelloOk(NONCE, identity, guarded + 1, kHelloOkFrameCapacity, length));
  TEST_ASSERT_EQUAL_UINT8(0xCC, guarded[0]);
  TEST_ASSERT_EQUAL_UINT8(0xCC, guarded[sizeof(guarded) - 1]);
  TEST_ASSERT_EQUAL(strlen(expected), length);
  TEST_ASSERT_EQUAL_MEMORY(expected, guarded + 1, length);
  TEST_ASSERT_EQUAL_UINT8('\n', guarded[length]);
  TEST_ASSERT_TRUE(length - 1 <= 512);
}

void test_exact_trusted_and_untrusted_frames() {
  assertFrame({true, 1, IdentityFailureReason::NONE},
              "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO_OK\",\"backend_session_nonce\":\"123e4567-e89b-12d3-a456-426614174000\",\"controller_boot_id\":1,\"controller_state\":\"PROTOCOL_ONLY\",\"software_state_trust\":\"TRUSTED\",\"capabilities\":[]}\n");
  assertFrame({false, 0, IdentityFailureReason::READ_FAILED},
              "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO_OK\",\"backend_session_nonce\":\"123e4567-e89b-12d3-a456-426614174000\",\"controller_boot_id\":null,\"controller_state\":\"IDENTITY_UNTRUSTED\",\"software_state_trust\":\"UNTRUSTED\",\"capabilities\":[]}\n");
}

void test_uint32_max_and_insufficient_capacity() {
  uint8_t output[kHelloOkFrameCapacity];
  size_t length = 0;
  TEST_ASSERT_TRUE(writeHelloOk(NONCE, {true, UINT32_MAX, IdentityFailureReason::NONE},
                                output, sizeof(output), length));
  output[length] = '\0';
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<const char*>(output), "4294967295"));
  const size_t required = length;
  uint8_t guarded[260];
  memset(guarded, 0xA7, sizeof(guarded));
  length = 123;
  TEST_ASSERT_FALSE(writeHelloOk(NONCE, {true, UINT32_MAX, IdentityFailureReason::NONE},
                                 guarded + 1, required - 1, length));
  TEST_ASSERT_EQUAL_UINT32(0, length);
  TEST_ASSERT_EQUAL_UINT8(0xA7, guarded[0]);
  TEST_ASSERT_EQUAL_UINT8(0xA7, guarded[sizeof(guarded) - 1]);
}

void test_session_replacement_and_validation() {
  SessionState session;
  const BootIdentityResult trusted{true, 42, IdentityFailureReason::NONE};
  TEST_ASSERT_FALSE(session.active());
  TEST_ASSERT_EQUAL(SessionValidationResult::HANDSHAKE_REQUIRED,
                    session.validate(NONCE, BootIdPresence::VALUE, 42, trusted));
  session.establish(NONCE);
  TEST_ASSERT_TRUE(session.active());
  TEST_ASSERT_EQUAL_STRING(NONCE, session.nonce());
  session.establish(NONCE);
  TEST_ASSERT_EQUAL(SessionValidationResult::VALID,
                    session.validate(NONCE, BootIdPresence::VALUE, 42, trusted));
  TEST_ASSERT_EQUAL(SessionValidationResult::CONTROLLER_BOOT_MISMATCH,
                    session.validate(NONCE, BootIdPresence::NULL_VALUE, 0, trusted));
  TEST_ASSERT_EQUAL(SessionValidationResult::CONTROLLER_BOOT_MISMATCH,
                    session.validate(NONCE, BootIdPresence::VALUE, 41, trusted));
  session.establish(OTHER_NONCE);
  TEST_ASSERT_EQUAL(SessionValidationResult::STALE_SESSION,
                    session.validate(NONCE, BootIdPresence::VALUE, 42, trusted));
  TEST_ASSERT_EQUAL(SessionValidationResult::VALID,
                    session.validate(OTHER_NONCE, BootIdPresence::VALUE, 42, trusted));
  for (int i = 0; i < 100; ++i) {
    TEST_ASSERT_TRUE(session.active());
  }
  TEST_ASSERT_EQUAL_UINT32(42, trusted.controllerBootId);
}

void test_untrusted_diagnostic_validation() {
  SessionState session;
  session.establish(NONCE);
  const BootIdentityResult untrusted{false, 0, IdentityFailureReason::VERIFY_FAILED};
  TEST_ASSERT_EQUAL(SessionValidationResult::VALID,
                    session.validate(NONCE, BootIdPresence::NULL_VALUE, 0, untrusted));
  TEST_ASSERT_EQUAL(SessionValidationResult::CONTROLLER_IDENTITY_UNTRUSTED,
                    session.validate(NONCE, BootIdPresence::VALUE, 1, untrusted));
}

void test_invalid_hello_does_not_mutate_session_or_emit_response() {
  SessionState session;
  session.establish(NONCE);
  const char invalid[] =
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO\","
      "\"backend_session_nonce\":\"123E4567-E89B-12D3-A456-426614174000\"}";
  const ParseResult parsed = MessageParser().parse(
      reinterpret_cast<const uint8_t*>(invalid), strlen(invalid));
  size_t outputLength = 0;
  uint8_t output[kHelloOkFrameCapacity]{};
  if (parsed.status == ParseStatus::VALID_MESSAGE && parsed.message.type == MessageType::HELLO) {
    const BootIdentityResult identity{true, 1, IdentityFailureReason::NONE};
    if (writeHelloOk(parsed.message.backendSessionNonce, identity,
                     output, sizeof(output), outputLength)) {
      session.establish(parsed.message.backendSessionNonce);
    }
  }
  TEST_ASSERT_EQUAL(ParseStatus::INVALID_MESSAGE, parsed.status);
  TEST_ASSERT_EQUAL_UINT32(0, outputLength);
  TEST_ASSERT_EQUAL_STRING(NONCE, session.nonce());
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_exact_trusted_and_untrusted_frames);
  RUN_TEST(test_uint32_max_and_insufficient_capacity);
  RUN_TEST(test_session_replacement_and_validation);
  RUN_TEST(test_untrusted_diagnostic_validation);
  RUN_TEST(test_invalid_hello_does_not_mutate_session_or_emit_response);
  return UNITY_END();
}
