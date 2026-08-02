#include <unity.h>

#include <limits.h>
#include <string.h>

#include "protocol/SessionState.h"
#include "protocol/StatusWriter.h"

using namespace labforge;

namespace {

constexpr char NONCE[] = "123e4567-e89b-12d3-a456-426614174000";
constexpr char OTHER_NONCE[] = "223e4567-e89b-12d3-a456-426614174000";
constexpr char REQUEST_ID[] = "423e4567-e89b-12d3-a456-426614174003";

void assertFrame(const BootIdentityResult& identity, const char* expected) {
  uint8_t guarded[kStatusFrameCapacity + 2];
  memset(guarded, 0xCC, sizeof(guarded));
  size_t length = 99;
  TEST_ASSERT_TRUE(writeStatus(NONCE, REQUEST_ID, identity, guarded + 1,
                               kStatusFrameCapacity, length));
  TEST_ASSERT_EQUAL_UINT8(0xCC, guarded[0]);
  TEST_ASSERT_EQUAL_UINT8(0xCC, guarded[sizeof(guarded) - 1]);
  TEST_ASSERT_EQUAL(strlen(expected), length);
  TEST_ASSERT_EQUAL_MEMORY(expected, guarded + 1, length);
  TEST_ASSERT_EQUAL_UINT8('\n', guarded[length]);
  TEST_ASSERT_TRUE(length - 1 <= 512);
}

void test_exact_trusted_and_untrusted_frames() {
  assertFrame(
      {true, UINT32_MAX, IdentityFailureReason::NONE},
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"STATUS\",\"backend_session_nonce\":\"123e4567-e89b-12d3-a456-426614174000\",\"controller_boot_id\":4294967295,\"request_id\":\"423e4567-e89b-12d3-a456-426614174003\",\"controller_state\":\"PROTOCOL_ONLY\",\"software_state_trust\":\"TRUSTED\",\"active_operation_command_id\":null}\n");
  assertFrame(
      {false, 0, IdentityFailureReason::READ_FAILED},
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"STATUS\",\"backend_session_nonce\":\"123e4567-e89b-12d3-a456-426614174000\",\"controller_boot_id\":null,\"request_id\":\"423e4567-e89b-12d3-a456-426614174003\",\"controller_state\":\"IDENTITY_UNTRUSTED\",\"software_state_trust\":\"UNTRUSTED\",\"active_operation_command_id\":null}\n");
}

void test_insufficient_capacity_is_transactional() {
  uint8_t output[kStatusFrameCapacity];
  size_t required = 0;
  TEST_ASSERT_TRUE(writeStatus(NONCE, REQUEST_ID,
                               {true, UINT32_MAX, IdentityFailureReason::NONE},
                               output, sizeof(output), required));

  uint8_t guarded[kStatusFrameCapacity + 2];
  memset(guarded, 0xA7, sizeof(guarded));
  size_t length = 123;
  TEST_ASSERT_FALSE(writeStatus(NONCE, REQUEST_ID,
                                {true, UINT32_MAX, IdentityFailureReason::NONE},
                                guarded + 1, required - 1, length));
  TEST_ASSERT_EQUAL_UINT32(0, length);
  for (size_t i = 0; i < sizeof(guarded); ++i) {
    TEST_ASSERT_EQUAL_UINT8(0xA7, guarded[i]);
  }
}

void test_only_valid_session_and_boot_identity_can_reach_writer() {
  SessionState session;
  const BootIdentityResult trusted{true, 7, IdentityFailureReason::NONE};
  TEST_ASSERT_EQUAL(SessionValidationResult::HANDSHAKE_REQUIRED,
                    session.validate(NONCE, BootIdPresence::VALUE, 7, trusted));
  session.establish(NONCE);
  TEST_ASSERT_EQUAL(SessionValidationResult::STALE_SESSION,
                    session.validate(OTHER_NONCE, BootIdPresence::VALUE, 7, trusted));
  TEST_ASSERT_EQUAL(SessionValidationResult::CONTROLLER_BOOT_MISMATCH,
                    session.validate(NONCE, BootIdPresence::VALUE, 8, trusted));
  TEST_ASSERT_EQUAL(SessionValidationResult::VALID,
                    session.validate(NONCE, BootIdPresence::VALUE, 7, trusted));

  const BootIdentityResult untrusted{false, 0, IdentityFailureReason::VERIFY_FAILED};
  TEST_ASSERT_EQUAL(SessionValidationResult::VALID,
                    session.validate(NONCE, BootIdPresence::NULL_VALUE, 0, untrusted));
  TEST_ASSERT_EQUAL(SessionValidationResult::CONTROLLER_IDENTITY_UNTRUSTED,
                    session.validate(NONCE, BootIdPresence::VALUE, 0, untrusted));
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_exact_trusted_and_untrusted_frames);
  RUN_TEST(test_insufficient_capacity_is_transactional);
  RUN_TEST(test_only_valid_session_and_boot_identity_can_reach_writer);
  return UNITY_END();
}
