#include <unity.h>

#include <stdio.h>
#include <string.h>

#include "actuator/P1MotionController.h"
#include "protocol/CommandLifecycleWriter.h"
#include "protocol/CommandStatusWriter.h"
#include "protocol/CooperativeFrameTransport.h"
#include "service/P1CommandRuntime.h"

using namespace labforge;

void setUp() {}
void tearDown() {}

namespace {

constexpr char NONCE[] = "123e4567-e89b-12d3-a456-426614174000";
constexpr char NONCE_B[] = "223e4567-e89b-12d3-a456-426614174001";
constexpr char OPERATION[] = "323e4567-e89b-12d3-a456-426614174002";
constexpr BootIdentityResult IDENTITY{true, 7, IdentityFailureReason::NONE};

class FakeIo : public P1MotionIo {
 public:
  bool home = false;
  bool direction = false;
  bool step = false;
  unsigned directionWrites = 0;
  unsigned risingEdges = 0;
  uint16_t lastPulseHighUs = 0;

  bool homeActive() const override { return home; }
  void writeDirection(bool high) override {
    direction = high;
    ++directionWrites;
  }
  void writeStep(bool high) override {
    if (high && !step) ++risingEdges;
    step = high;
  }
  void pulseStep(uint16_t highUs) override {
    step = true;
    ++risingEdges;
    lastPulseHighUs = highUs;
    step = false;
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
  TEST_ASSERT_TRUE(runtime.confirmStartedFrameWritten(100, cache));
  TEST_ASSERT_EQUAL_UINT32(1, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);
  runtime.update(100 + kP1DirectionSetupUs - 1, cache);
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);
  runtime.update(100 + kP1DirectionSetupUs, cache);
  TEST_ASSERT_EQUAL_UINT32(1, io.risingEdges);
  TEST_ASSERT_GREATER_THAN_UINT32(0, result.outputLength);
}

void test_started_transport_must_complete_before_first_gpio_side_effect() {
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
  TEST_ASSERT_TRUE(startsMotion);
  CooperativeFrameTransport transport;
  TEST_ASSERT_TRUE(transport.begin(length, startsMotion));

  while (transport.pending()) {
    const FrameTxSlice slice = transport.nextSlice(7);
    const FrameTxCompletion completion =
        transport.commit(slice.length, slice.length);
    if (completion == FrameTxCompletion::STARTED_FRAME_COMPLETE) {
      TEST_ASSERT_TRUE(runtime.confirmStartedFrameWritten(100, cache));
    } else {
      TEST_ASSERT_EQUAL_UINT32(0, io.directionWrites);
      TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);
      TEST_ASSERT_EQUAL(CommandState::ACCEPTED,
                        cache.find(OPERATION)->record.state);
    }
  }

  TEST_ASSERT_EQUAL_UINT32(1, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);
  TEST_ASSERT_EQUAL(CommandState::STARTED,
                    cache.find(OPERATION)->record.state);
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

void test_short_started_transport_is_retryable_without_false_started_state() {
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
  TEST_ASSERT_TRUE(startsMotion);
  TEST_ASSERT_EQUAL(CommandState::ACCEPTED,
                    cache.find(OPERATION)->record.state);
  TEST_ASSERT_TRUE(runtime.startedFrameTransportFailed());
  TEST_ASSERT_EQUAL_UINT32(0, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);

  TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(
      IDENTITY, cache, output, sizeof(output), length, startsMotion));
  TEST_ASSERT_TRUE(runtime.confirmStartedFrameWritten(100, cache));
  TEST_ASSERT_EQUAL(CommandState::STARTED,
                    cache.find(OPERATION)->record.state);
  TEST_ASSERT_EQUAL_UINT32(1, io.directionWrites);
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

void test_stale_session_and_boot_mismatch_do_not_touch_motion_or_cache() {
  FakeIo io;
  P1MotionController controller(io);
  P1CommandRuntime runtime(controller);
  SessionState session;
  establishSession(session);
  CommandStatusCache cache;
  uint8_t output[kCommandLifecycleFrameCapacity]{};
  const char stale[] =
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\","
      "\"backend_session_nonce\":\"223e4567-e89b-12d3-a456-426614174001\","
      "\"controller_boot_id\":7,\"phase_execution_id\":\"phase-1\","
      "\"operation_command_id\":\"323e4567-e89b-12d3-a456-426614174002\","
      "\"command\":\"PUMP_HOME\",\"arguments\":{\"pump\":\"P1\"}}";
  dispatch(runtime, session, cache, stale, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), "STALE_SESSION"));
  TEST_ASSERT_NULL(cache.find(OPERATION));

  const char wrongBoot[] =
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\","
      "\"backend_session_nonce\":\"123e4567-e89b-12d3-a456-426614174000\","
      "\"controller_boot_id\":8,\"phase_execution_id\":\"phase-1\","
      "\"operation_command_id\":\"323e4567-e89b-12d3-a456-426614174002\","
      "\"command\":\"PUMP_HOME\",\"arguments\":{\"pump\":\"P1\"}}";
  dispatch(runtime, session, cache, wrongBoot, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "CONTROLLER_BOOT_MISMATCH"));
  TEST_ASSERT_NULL(cache.find(OPERATION));
  TEST_ASSERT_EQUAL_UINT32(0, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);

}

void test_untrusted_identity_rejects_physical_command_before_preflight() {
  FakeIo io;
  P1MotionController controller(io);
  P1CommandRuntime runtime(controller);
  SessionState session;
  session.establish(NONCE);
  CommandStatusCache cache;
  const BootIdentityResult untrusted{
      false, 0, IdentityFailureReason::NO_VALID_RECORD};
  const char command[] =
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\","
      "\"backend_session_nonce\":\"123e4567-e89b-12d3-a456-426614174000\","
      "\"controller_boot_id\":null,\"phase_execution_id\":\"phase-1\","
      "\"operation_command_id\":\"323e4567-e89b-12d3-a456-426614174002\","
      "\"command\":\"PUMP_HOME\",\"arguments\":{\"pump\":\"P1\"}}";
  uint8_t output[kCommandLifecycleFrameCapacity]{};
  runtime.dispatch(reinterpret_cast<const uint8_t*>(command), strlen(command),
                   untrusted, session, cache, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "CONTROLLER_IDENTITY_UNTRUSTED"));
  TEST_ASSERT_NULL(cache.find(OPERATION));
  TEST_ASSERT_EQUAL(P1MotionState::IDLE, controller.state());
  TEST_ASSERT_EQUAL_UINT32(0, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);
}

void test_session_replacement_keeps_running_and_suppresses_old_lifecycle() {
  FakeIo io;
  P1MotionController controller(io);
  P1CommandRuntime runtime(controller);
  SessionState session;
  establishSession(session);
  CommandStatusCache cache;
  char command[384];
  makeCommand(command, sizeof(command), "PUMP_HOME", "{\"pump\":\"P1\"}");
  uint8_t output[kCommandStatusFrameCapacity]{};
  dispatch(runtime, session, cache, command, output, sizeof(output));
  size_t length = 0;
  bool startsMotion = false;
  TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(
      IDENTITY, cache, output, sizeof(output), length, startsMotion));
  TEST_ASSERT_TRUE(runtime.confirmStartedFrameWritten(0, cache));

  const char helloB[] =
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO\","
      "\"backend_session_nonce\":\"223e4567-e89b-12d3-a456-426614174001\"}";
  dispatch(runtime, session, cache, helloB, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"controller_state\":\"BUSY\""));
  TEST_ASSERT_EQUAL_STRING(NONCE_B, session.nonce());
  TEST_ASSERT_FALSE(runtime.hasPendingLifecycleFrame());

  io.home = true;
  runtime.update(100, cache);
  runtime.update(100 + kP1HomeStableUs, cache);
  TEST_ASSERT_EQUAL(CommandState::COMPLETED,
                    cache.find(OPERATION)->record.state);
  TEST_ASSERT_FALSE(runtime.hasPendingLifecycleFrame());

  const char query[] =
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"QUERY_COMMAND\","
      "\"backend_session_nonce\":\"223e4567-e89b-12d3-a456-426614174001\","
      "\"controller_boot_id\":7,"
      "\"request_id\":\"423e4567-e89b-12d3-a456-426614174003\","
      "\"operation_command_id\":\"323e4567-e89b-12d3-a456-426614174002\"}";
  dispatch(runtime, session, cache, query, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"command_state\":\"COMPLETED\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), NONCE_B));
}

void test_session_replacement_after_short_started_write_uses_new_nonce() {
  FakeIo io;
  P1MotionController controller(io);
  P1CommandRuntime runtime(controller);
  SessionState session;
  establishSession(session);
  CommandStatusCache cache;
  char command[384];
  makeCommand(command, sizeof(command), "PUMP_HOME", "{\"pump\":\"P1\"}");
  uint8_t output[kCommandStatusFrameCapacity]{};
  dispatch(runtime, session, cache, command, output, sizeof(output));

  size_t length = 0;
  bool startsMotion = false;
  TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(
      IDENTITY, cache, output, sizeof(output), length, startsMotion));
  TEST_ASSERT_TRUE(runtime.startedFrameTransportFailed());

  const char helloB[] =
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO\","
      "\"backend_session_nonce\":\"223e4567-e89b-12d3-a456-426614174001\"}";
  dispatch(runtime, session, cache, helloB, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"controller_state\":\"BUSY\""));

  memset(output, 0, sizeof(output));
  TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(
      IDENTITY, cache, output, sizeof(output), length, startsMotion));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output), NONCE_B));
  TEST_ASSERT_NULL(strstr(reinterpret_cast<char*>(output), NONCE));
  TEST_ASSERT_TRUE(runtime.confirmStartedFrameWritten(100, cache));
  TEST_ASSERT_EQUAL_UINT32(1, io.directionWrites);
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
  TEST_ASSERT_TRUE(runtime.confirmStartedFrameWritten(0, cache));

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

void test_duplicate_identity_conflict_and_new_command_busy_are_rejected() {
  FakeIo io;
  P1MotionController controller(io);
  P1CommandRuntime runtime(controller);
  SessionState session;
  establishSession(session);
  CommandStatusCache cache;
  uint8_t output[kCommandLifecycleFrameCapacity]{};
  char command[384];
  makeCommand(command, sizeof(command), "PUMP_HOME", "{\"pump\":\"P1\"}");
  dispatch(runtime, session, cache, command, output, sizeof(output));

  makeCommand(command, sizeof(command), "PUMP_MOVE_ABSOLUTE_STEPS",
              "{\"pump\":\"P1\",\"target_steps\":100}");
  dispatch(runtime, session, cache, command, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "COMMAND_ID_CONFLICT"));

  makeCommand(command, sizeof(command), "PUMP_HOME", "{\"pump\":\"P1\"}",
              "523e4567-e89b-12d3-a456-426614174004");
  dispatch(runtime, session, cache, command, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "CONTROLLER_BUSY"));
  TEST_ASSERT_EQUAL(CommandState::ACCEPTED,
                    cache.find(OPERATION)->record.state);
  TEST_ASSERT_EQUAL_UINT32(0, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);

  size_t length = 0;
  bool startsMotion = false;
  TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(
      IDENTITY, cache, output, sizeof(output), length, startsMotion));
  TEST_ASSERT_TRUE(runtime.confirmStartedFrameWritten(100, cache));

  makeCommand(command, sizeof(command), "PUMP_HOME", "{\"pump\":\"P1\"}",
              "623e4567-e89b-12d3-a456-426614174005");
  dispatch(runtime, session, cache, command, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "CONTROLLER_BUSY"));
  TEST_ASSERT_EQUAL(CommandState::STARTED,
                    cache.find(OPERATION)->record.state);
  TEST_ASSERT_EQUAL_UINT32(1, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(0, io.risingEdges);
}

void test_hello_advertises_all_integrated_actuator_capabilities() {
  FakeIo io;
  P1MotionController controller(io);
  P1CommandRuntime runtime(controller);
  SessionState session;
  CommandStatusCache cache;
  const char hello[] =
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO\","
      "\"backend_session_nonce\":"
      "\"123e4567-e89b-12d3-a456-426614174000\"}";
  uint8_t output[kCommandStatusFrameCapacity]{};

  dispatch(runtime, session, cache, hello, output, sizeof(output));

  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"controller_state\":\"IDLE\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"PUMP_HOME\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"PUMP_MOVE_ABSOLUTE_STEPS\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"VALVE_HOME\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"VALVE_SET_POSITION\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"COLUMN_BOTTOM_VALVE_HOME\""));
  TEST_ASSERT_NOT_NULL(strstr(
      reinterpret_cast<char*>(output),
      "\"COLUMN_BOTTOM_VALVE_SET_POSITION\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"CAROUSEL_SET_REFERENCE\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"CAROUSEL_MOVE_TO_POSITION\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"SF_MIXER_SET_STATE\""));
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
  TEST_ASSERT_TRUE(runtime.confirmStartedFrameWritten(0, cache));
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

void test_p2_command_selects_only_p2_controller() {
  FakeIo p1Io;
  FakeIo p2Io;
  P1MotionController p1Controller(p1Io);
  P1MotionController p2Controller(p2Io);
  P1CommandRuntime runtime(p1Controller, p2Controller);
  SessionState session;
  establishSession(session);
  CommandStatusCache cache;
  char command[384];
  makeCommand(command, sizeof(command), "PUMP_HOME", "{\"pump\":\"P2\"}");
  uint8_t output[kCommandLifecycleFrameCapacity]{};

  dispatch(runtime, session, cache, command, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"type\":\"ACCEPTED\""));
  size_t length = 0;
  bool startsMotion = false;
  TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(
      IDENTITY, cache, output, sizeof(output), length, startsMotion));
  TEST_ASSERT_TRUE(startsMotion);
  TEST_ASSERT_TRUE(runtime.confirmStartedFrameWritten(100, cache));

  TEST_ASSERT_EQUAL_UINT32(0, p1Io.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(0, p1Io.risingEdges);
  TEST_ASSERT_EQUAL_UINT32(1, p2Io.directionWrites);
  runtime.update(100 + kP1DirectionSetupUs, cache);
  TEST_ASSERT_EQUAL_UINT32(0, p1Io.risingEdges);
  TEST_ASSERT_EQUAL_UINT32(1, p2Io.risingEdges);
  TEST_ASSERT_EQUAL(PumpId::P2,
                    cache.find(OPERATION)->record.semanticIdentity.pump);
}

void test_p2_is_rejected_when_runtime_has_no_p2_controller() {
  FakeIo p1Io;
  P1MotionController p1Controller(p1Io);
  P1CommandRuntime runtime(p1Controller);
  SessionState session;
  establishSession(session);
  CommandStatusCache cache;
  char command[384];
  makeCommand(command, sizeof(command), "PUMP_HOME", "{\"pump\":\"P2\"}");
  uint8_t output[kCommandLifecycleFrameCapacity]{};

  dispatch(runtime, session, cache, command, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"type\":\"REJECTED\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"error_code\":\"INVALID_FIELD\""));
  TEST_ASSERT_EQUAL_UINT32(0, p1Io.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(0, p1Io.risingEdges);
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_started_is_serialized_before_any_motion_side_effect);
  RUN_TEST(test_started_transport_must_complete_before_first_gpio_side_effect);
  RUN_TEST(test_small_started_buffer_cannot_start_or_advance_cache);
  RUN_TEST(test_short_started_transport_is_retryable_without_false_started_state);
  RUN_TEST(test_command_session_failure_is_protocol_error_not_rejection);
  RUN_TEST(test_stale_session_and_boot_mismatch_do_not_touch_motion_or_cache);
  RUN_TEST(test_untrusted_identity_rejects_physical_command_before_preflight);
  RUN_TEST(test_session_replacement_keeps_running_and_suppresses_old_lifecycle);
  RUN_TEST(test_session_replacement_after_short_started_write_uses_new_nonce);
  RUN_TEST(test_running_command_reports_busy_and_abort_is_truthful);
  RUN_TEST(test_duplicate_identity_conflict_and_new_command_busy_are_rejected);
  RUN_TEST(test_hello_advertises_all_integrated_actuator_capabilities);
  RUN_TEST(test_invalid_move_is_rejected_without_gpio_writes);
  RUN_TEST(test_home_completion_is_cached_and_duplicate_only_replays);
  RUN_TEST(test_p2_command_selects_only_p2_controller);
  RUN_TEST(test_p2_is_rejected_when_runtime_has_no_p2_controller);
  return UNITY_END();
}
