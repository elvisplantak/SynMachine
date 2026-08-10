#include <unity.h>

#include <stdio.h>
#include <string.h>

#include "actuator/P1MotionController.h"
#include "protocol/CommandLifecycleWriter.h"
#include "service/P1CommandRuntime.h"

using namespace labforge;

void setUp() {}
void tearDown() {}

namespace {

constexpr char NONCE[] = "123e4567-e89b-12d3-a456-426614174000";
constexpr char OPERATION[] = "323e4567-e89b-12d3-a456-426614174002";
constexpr BootIdentityResult IDENTITY{true, 7, IdentityFailureReason::NONE};

class FakeIo : public P1MotionIo {
 public:
  bool home = false;
  bool direction = false;
  bool step = false;
  unsigned directionWrites = 0;
  unsigned risingEdges = 0;

  bool homeActive() const override { return home; }
  void writeDirection(bool high) override {
    direction = high;
    ++directionWrites;
  }
  void writeStep(bool high) override {
    if (high && !step) ++risingEdges;
    step = high;
  }
};

void establishSession(SessionState& session) { session.establish(NONCE); }

void makeCommand(char* frame, size_t capacity, const char* command,
                 const char* arguments, const char* operation = OPERATION) {
  snprintf(frame, capacity,
           "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\","
           "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":7,"
           "\"phase_execution_id\":\"phase-1\","
           "\"operation_command_id\":\"%s\",\"command\":\"%s\","
           "\"arguments\":%s}",
           NONCE, operation, command, arguments);
}

DispatchResult dispatch(P1CommandRuntime& runtime, SessionState& session,
                        CommandStatusCache& cache, const char* frame,
                        uint8_t* output, size_t capacity) {
  memset(output, 0, capacity);
  return runtime.dispatch(reinterpret_cast<const uint8_t*>(frame),
                          strlen(frame), IDENTITY, session, cache, output,
                          capacity);
}

void test_started_is_serialized_before_any_motion_side_effect() {
  FakeIo io;
  P1MotionController controller(io);
  P1CommandRuntime runtime(controller);
  SessionState session;
  establishSession(session);
  CommandStatusCache cache;
  char command[384];
  makeCommand(command, sizeof(command), "PUMP_HOME", "{\"pump\":\"P1\"}");
  uint8_t output[kCommandLifecycleFrameCapacity]{};

  DispatchResult result = dispatch(runtime, session, cache, command, output,
                                   sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"type\":\"ACCEPTED\""));
  TEST_ASSERT_EQUAL_UINT32(0, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);

  size_t length = 0;
  bool startsMotion = false;
  memset(output, 0, sizeof(output));
  TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(
      IDENTITY, cache, output, sizeof(output), length, startsMotion));
  TEST_ASSERT_TRUE(startsMotion);
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"type\":\"STARTED\""));
  TEST_ASSERT_EQUAL_UINT32(0, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);
  TEST_ASSERT_TRUE(runtime.confirmStartedFrameWritten(100));
  TEST_ASSERT_EQUAL_UINT32(1, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);
  runtime.update(100 + kP1DirectionSetupUs - 1, cache);
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);
  runtime.update(100 + kP1DirectionSetupUs, cache);
  TEST_ASSERT_EQUAL_UINT32(1, io.risingEdges);
  TEST_ASSERT_GREATER_THAN_UINT32(0, result.outputLength);
}

void test_small_started_buffer_cannot_start_or_advance_cache() {
  FakeIo io;
  P1MotionController controller(io);
  P1CommandRuntime runtime(controller);
  SessionState session;
  establishSession(session);
  CommandStatusCache cache;
  char command[384];
  makeCommand(command, sizeof(command), "PUMP_HOME", "{\"pump\":\"P1\"}");
  uint8_t output[kCommandLifecycleFrameCapacity]{};
  dispatch(runtime, session, cache, command, output, sizeof(output));

  size_t length = 99;
  bool startsMotion = true;
  TEST_ASSERT_FALSE(runtime.nextLifecycleFrame(IDENTITY, cache, output, 1,
                                                length, startsMotion));
  TEST_ASSERT_EQUAL_UINT32(0, length);
  TEST_ASSERT_FALSE(startsMotion);
  TEST_ASSERT_EQUAL(CommandState::ACCEPTED,
                    cache.find(OPERATION)->record.state);
  TEST_ASSERT_EQUAL_UINT32(0, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);
}

void test_command_session_failure_is_protocol_error_not_rejection() {
  FakeIo io;
  P1MotionController controller(io);
  P1CommandRuntime runtime(controller);
  SessionState session;
  CommandStatusCache cache;
  char command[384];
  makeCommand(command, sizeof(command), "PUMP_HOME", "{\"pump\":\"P1\"}");
  uint8_t output[kCommandLifecycleFrameCapacity]{};
  dispatch(runtime, session, cache, command, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"type\":\"PROTOCOL_ERROR\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "HANDSHAKE_REQUIRED"));
  TEST_ASSERT_NULL(cache.find(OPERATION));
}

void test_running_command_reports_busy_and_abort_is_truthful() {
  FakeIo io;
  P1MotionController controller(io);
  P1CommandRuntime runtime(controller);
  SessionState session;
  establishSession(session);
  CommandStatusCache cache;
  char command[384];
  makeCommand(command, sizeof(command), "PUMP_HOME", "{\"pump\":\"P1\"}");
  uint8_t output[kCommandLifecycleFrameCapacity]{};
  dispatch(runtime, session, cache, command, output, sizeof(output));
  size_t length = 0;
  bool startsMotion = false;
  TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(
      IDENTITY, cache, output, sizeof(output), length, startsMotion));
  TEST_ASSERT_TRUE(runtime.confirmStartedFrameWritten(0));

  const char query[] =
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"QUERY_STATUS\","
      "\"backend_session_nonce\":\"123e4567-e89b-12d3-a456-426614174000\","
      "\"controller_boot_id\":7,"
      "\"request_id\":\"423e4567-e89b-12d3-a456-426614174003\"}";
  dispatch(runtime, session, cache, query, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"controller_state\":\"BUSY\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), OPERATION));

  TEST_ASSERT_TRUE(runtime.abort(cache));
  memset(output, 0, sizeof(output));
  TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(
      IDENTITY, cache, output, sizeof(output), length, startsMotion));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"type\":\"FAILED\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"error_code\":\"COMMAND_ABORTED\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"execution_started\":true"));
  TEST_ASSERT_FALSE(io.step);

  dispatch(runtime, session, cache, query, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"controller_state\":\"IDLE\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"active_operation_command_id\":null"));
}

void test_hello_advertises_only_integrated_p1_capabilities() {
  FakeIo io;
  P1MotionController controller(io);
  P1CommandRuntime runtime(controller);
  SessionState session;
  CommandStatusCache cache;
  const char hello[] =
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO\","
      "\"backend_session_nonce\":"
      "\"123e4567-e89b-12d3-a456-426614174000\"}";
  uint8_t output[kCommandLifecycleFrameCapacity]{};

  dispatch(runtime, session, cache, hello, output, sizeof(output));

  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"controller_state\":\"IDLE\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"PUMP_HOME\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"PUMP_MOVE_ABSOLUTE_STEPS\""));
  TEST_ASSERT_NULL(strstr(reinterpret_cast<char*>(output), "CAROUSEL"));
}

void test_invalid_move_is_rejected_without_gpio_writes() {
  FakeIo io;
  P1MotionController controller(io);
  P1CommandRuntime runtime(controller);
  SessionState session;
  establishSession(session);
  CommandStatusCache cache;
  char command[384];
  makeCommand(command, sizeof(command), "PUMP_MOVE_ABSOLUTE_STEPS",
              "{\"pump\":\"P1\",\"target_steps\":0}");
  uint8_t output[kCommandLifecycleFrameCapacity]{};
  dispatch(runtime, session, cache, command, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"type\":\"REJECTED\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"error_code\":\"INVALID_FIELD\""));
  TEST_ASSERT_EQUAL_UINT32(0, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);
}

void test_home_completion_is_cached_and_duplicate_only_replays() {
  FakeIo io;
  io.home = true;
  P1MotionController controller(io);
  P1CommandRuntime runtime(controller);
  SessionState session;
  establishSession(session);
  CommandStatusCache cache;
  char command[384];
  makeCommand(command, sizeof(command), "PUMP_HOME", "{\"pump\":\"P1\"}");
  uint8_t output[kCommandLifecycleFrameCapacity]{};
  dispatch(runtime, session, cache, command, output, sizeof(output));
  size_t length = 0;
  bool startsMotion = false;
  TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(
      IDENTITY, cache, output, sizeof(output), length, startsMotion));
  TEST_ASSERT_TRUE(runtime.confirmStartedFrameWritten(0));
  runtime.update(kP1HomeStableUs, cache);
  TEST_ASSERT_TRUE(runtime.hasPendingLifecycleFrame());
  memset(output, 0, sizeof(output));
  TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(
      IDENTITY, cache, output, sizeof(output), length, startsMotion));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"type\":\"COMPLETED\""));
  TEST_ASSERT_EQUAL(CommandState::COMPLETED,
                    cache.find(OPERATION)->record.state);
  const unsigned directionWrites = io.directionWrites;
  const unsigned risingEdges = io.risingEdges;

  dispatch(runtime, session, cache, command, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"type\":\"COMPLETED\""));
  TEST_ASSERT_EQUAL_UINT32(directionWrites, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(risingEdges, io.risingEdges);
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_started_is_serialized_before_any_motion_side_effect);
  RUN_TEST(test_small_started_buffer_cannot_start_or_advance_cache);
  RUN_TEST(test_command_session_failure_is_protocol_error_not_rejection);
  RUN_TEST(test_running_command_reports_busy_and_abort_is_truthful);
  RUN_TEST(test_hello_advertises_only_integrated_p1_capabilities);
  RUN_TEST(test_invalid_move_is_rejected_without_gpio_writes);
  RUN_TEST(test_home_completion_is_cached_and_duplicate_only_replays);
  return UNITY_END();
}
