#include <unity.h>
#include <limits.h>
#include <string.h>
#include "protocol/StatusWriter.h"
#include "service/P1CommandRuntime.h"
using namespace labforge;
namespace {
constexpr char NONCE[] = "123e4567-e89b-12d3-a456-426614174000";
constexpr char QUERY[] =
    "{\"protocol\":\"LABFORGE/1\",\"type\":\"QUERY_STATUS\","
    "\"backend_session_nonce\":\"123e4567-e89b-12d3-a456-426614174000\","
    "\"controller_boot_id\":7,"
    "\"request_id\":\"423e4567-e89b-12d3-a456-426614174003\"}";
class Io : public P1MotionIo {
 public:
  bool active = false;
  mutable unsigned reads = 0;
  unsigned writes = 0;
  bool homeActive() const override { ++reads; return active; }
  void writeDirection(bool) override { ++writes; }
  void writeStep(bool) override { ++writes; }
  void pulseStep(uint16_t) override { ++writes; }
};
void test_queries_sample_both_inputs_without_gpio_writes_or_reference_changes() {
  Io one, two;
  one.active = true;
  P1MotionController p1(one), p2(two);
  P1CommandRuntime runtime(p1, p2);
  SessionState session;
  session.establish(NONCE);
  CommandStatusCache cache;
  uint8_t output[kStatusFrameCapacity]{};
  for (unsigned sample = 0; sample < 2; ++sample) {
    memset(output, 0, sizeof(output));
    const DispatchResult result = runtime.dispatch(
        reinterpret_cast<const uint8_t*>(QUERY), strlen(QUERY),
        {true, 7, IdentityFailureReason::NONE}, session, cache, output, sizeof(output));
    TEST_ASSERT_TRUE(result.outputLength > 0);
    const char* text = reinterpret_cast<char*>(output);
    TEST_ASSERT_NOT_NULL(strstr(text, sample == 0 ? "\"p1_home_active\":true" : "\"p1_home_active\":false"));
    TEST_ASSERT_NOT_NULL(strstr(text, sample == 0 ? "\"p2_home_active\":false" : "\"p2_home_active\":true"));
    one.active = false;
    two.active = true;
  }
  TEST_ASSERT_EQUAL_UINT32(2, one.reads);
  TEST_ASSERT_EQUAL_UINT32(2, two.reads);
  TEST_ASSERT_EQUAL_UINT32(0, one.writes + two.writes);
  TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED, p1.positionTrust());
  TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED, p2.positionTrust());
  TEST_ASSERT_EQUAL(P1MotionState::IDLE, p1.state());
  TEST_ASSERT_NULL(cache.active());
}
void test_invalid_session_never_samples_inputs() {
  Io one;
  P1MotionController p1(one);
  P1CommandRuntime runtime(p1);
  SessionState session;
  CommandStatusCache cache;
  uint8_t output[kStatusFrameCapacity]{};
  runtime.dispatch(reinterpret_cast<const uint8_t*>(QUERY), strlen(QUERY),
      {true, 7, IdentityFailureReason::NONE}, session, cache, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), "HANDSHAKE_REQUIRED"));
  TEST_ASSERT_EQUAL_UINT32(0, one.reads + one.writes);
}
void test_single_pump_does_not_invent_second_input() {
  Io one;
  P1MotionController p1(one);
  P1CommandRuntime runtime(p1);
  SessionState session;
  session.establish(NONCE);
  CommandStatusCache cache;
  uint8_t output[kStatusFrameCapacity]{};
  runtime.dispatch(reinterpret_cast<const uint8_t*>(QUERY), strlen(QUERY),
      {true, 7, IdentityFailureReason::NONE}, session, cache, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), "\"p1_home_active\":false"));
  TEST_ASSERT_NULL(strstr(reinterpret_cast<char*>(output), "p2_home_active"));
  TEST_ASSERT_EQUAL_UINT32(0, one.writes);
}
void test_worst_busy_frame_with_column_and_pumps_fits_and_small_buffer_is_untouched() {
  CommandStatusCache cache;
  CommandStatusRecord record{};
  strcpy(record.operationCommandId, "323e4567-e89b-12d3-a456-426614174002");
  strcpy(record.phaseExecutionId, "phase");
  record.phaseExecutionIdKnown = true;
  record.semanticIdentityKnown = true;
  record.semanticIdentity = {CommandKind::PUMP_HOME, PumpId::P1};
  record.state = CommandState::ACCEPTED;
  TEST_ASSERT_TRUE(cache.store(record));
  const ColumnValveStatusDiagnostics column{
      "CONFIRMING_UNEXPECTED_HOME", UINT32_MAX, false};
  const PumpHomeStatusDiagnostics pumps{false, true, false};
  uint8_t guarded[kStatusFrameCapacity + 2];
  memset(guarded, 0xA7, sizeof(guarded));
  size_t length = 0;
  TEST_ASSERT_TRUE(writeStatus(NONCE, "423e4567-e89b-12d3-a456-426614174003",
      {true, UINT32_MAX, IdentityFailureReason::NONE}, guarded + 1, kStatusFrameCapacity,
      length, &cache, true, &column, &pumps));
  TEST_ASSERT_TRUE(length - 1 <= 512);
  TEST_ASSERT_EQUAL_UINT8(0xA7, guarded[0]);
  TEST_ASSERT_EQUAL_UINT8(0xA7, guarded[sizeof(guarded) - 1]);
  const size_t required = length;
  memset(guarded, 0xA7, sizeof(guarded));
  TEST_ASSERT_FALSE(writeStatus(NONCE, "423e4567-e89b-12d3-a456-426614174003",
      {true, UINT32_MAX, IdentityFailureReason::NONE}, guarded + 1, required - 1,
      length, &cache, true, &column, &pumps));
  TEST_ASSERT_EQUAL_UINT32(0, length);
  for (size_t i = 0; i < sizeof(guarded); ++i) TEST_ASSERT_EQUAL_UINT8(0xA7, guarded[i]);
}
}
int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_queries_sample_both_inputs_without_gpio_writes_or_reference_changes);
  RUN_TEST(test_invalid_session_never_samples_inputs);
  RUN_TEST(test_single_pump_does_not_invent_second_input);
  RUN_TEST(test_worst_busy_frame_with_column_and_pumps_fits_and_small_buffer_is_untouched);
  return UNITY_END();
}
