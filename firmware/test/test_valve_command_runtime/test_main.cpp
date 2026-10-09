#include <unity.h>

#include <cstdio>
#include <cstring>

#include "actuator/P1MotionController.h"
#include "actuator/ValveMotionController.h"
#include "protocol/CommandLifecycleWriter.h"
#include "service/P1CommandRuntime.h"

using namespace labforge;

namespace {

constexpr char NONCE[] = "123e4567-e89b-12d3-a456-426614174000";
constexpr char OPERATION[] = "323e4567-e89b-12d3-a456-426614174002";
constexpr BootIdentityResult IDENTITY{true, 7, IdentityFailureReason::NONE};

class PumpIo final : public P1MotionIo {
 public:
  bool homeActive() const override { return false; }
  void writeDirection(bool) override {}
  void writeStep(bool) override {}
  void pulseStep(uint16_t) override {}
};

class ValveIo final : public ValveMotionIo {
 public:
  bool home = false;
  unsigned directionWrites = 0;
  unsigned pulses = 0;
  bool direction = false;
  bool step = false;
  bool homeActive() const override { return home; }
  void writeDirection(bool high) override {
    direction = high;
    ++directionWrites;
  }
  void writeStep(bool high) override { step = high; }
  void pulseStep(uint16_t) override { ++pulses; }
};

void makeCommand(char* frame, size_t capacity, const char* command,
                 const char* arguments) {
  std::snprintf(
      frame, capacity,
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\","
      "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":7,"
      "\"phase_execution_id\":\"phase-1\","
      "\"operation_command_id\":\"%s\",\"command\":\"%s\","
      "\"arguments\":%s}", NONCE, OPERATION, command, arguments);
}

void dispatchAndStart(P1CommandRuntime& runtime, SessionState& session,
                      CommandStatusCache& cache, const char* commandName,
                      const char* arguments, uint32_t now) {
  char command[384];
  makeCommand(command, sizeof(command), commandName, arguments);
  uint8_t output[kCommandLifecycleFrameCapacity]{};
  runtime.dispatch(reinterpret_cast<const uint8_t*>(command),
                   std::strlen(command), IDENTITY, session, cache, output,
                   sizeof(output));
  size_t length = 0;
  bool startsMotion = false;
  TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(
      IDENTITY, cache, output, sizeof(output), length, startsMotion));
  TEST_ASSERT_TRUE(startsMotion);
  TEST_ASSERT_TRUE(runtime.confirmStartedFrameWritten(now, cache));
}

void establishValveHome(ValveMotionController& valve, ValveIo& io,
                        uint32_t now) {
  io.home = true;
  TEST_ASSERT_EQUAL(ValvePrepareResult::READY, valve.prepareHome());
  TEST_ASSERT_TRUE(valve.start(now));
  TEST_ASSERT_EQUAL(ValveMotionResult::COMPLETED,
                    valve.update(now + kValveHomeStableUs));
}

void test_v8_home_waits_for_complete_started_frame_then_selects_only_v8() {
  PumpIo pumpIo;
  P1MotionController p1(pumpIo);
  P1MotionController p2(pumpIo);
  ValveIo valveIo[8];
  ValveMotionController valves[] = {
      {valveIo[0], true}, {valveIo[1], false}, {valveIo[2], true},
      {valveIo[3], true}, {valveIo[4], true},  {valveIo[5], false},
      {valveIo[6], true}, {valveIo[7], true},
  };
  ValveMotionController* pointers[] = {&valves[0], &valves[1], &valves[2],
                                       &valves[3], &valves[4], &valves[5],
                                       &valves[6], &valves[7]};
  P1CommandRuntime runtime(p1, p2, pointers, 8);
  SessionState session;
  session.establish(NONCE);
  CommandStatusCache cache;
  char command[384];
  makeCommand(command, sizeof(command), "VALVE_HOME", "{\"valve\":\"V8\"}");
  uint8_t output[kCommandLifecycleFrameCapacity]{};

  const DispatchResult accepted = runtime.dispatch(
      reinterpret_cast<const uint8_t*>(command), std::strlen(command),
      IDENTITY, session, cache, output, sizeof(output));
  TEST_ASSERT_GREATER_THAN_UINT32(0, accepted.outputLength);
  TEST_ASSERT_NOT_NULL(std::strstr(reinterpret_cast<char*>(output),
                                   "\"type\":\"ACCEPTED\""));
  for (const ValveIo& io : valveIo)
    TEST_ASSERT_EQUAL_UINT32(0, io.directionWrites);

  size_t length = 0;
  bool startsMotion = false;
  TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(
      IDENTITY, cache, output, sizeof(output), length, startsMotion));
  TEST_ASSERT_TRUE(startsMotion);
  for (const ValveIo& io : valveIo)
    TEST_ASSERT_EQUAL_UINT32(0, io.directionWrites);
  TEST_ASSERT_TRUE(runtime.confirmStartedFrameWritten(100, cache));
  for (uint8_t i = 0; i < 7; ++i)
    TEST_ASSERT_EQUAL_UINT32(0, valveIo[i].directionWrites);
  TEST_ASSERT_EQUAL_UINT32(1, valveIo[7].directionWrites);
  TEST_ASSERT_TRUE(valveIo[7].direction);
}

void test_position_requires_that_selected_valve_has_been_homed() {
  PumpIo pumpIo;
  P1MotionController p1(pumpIo);
  P1MotionController p2(pumpIo);
  ValveIo valveIo;
  ValveMotionController valve(valveIo, true);
  ValveMotionController* pointers[] = {&valve};
  P1CommandRuntime runtime(p1, p2, pointers, 1);
  SessionState session;
  session.establish(NONCE);
  CommandStatusCache cache;
  char command[384];
  makeCommand(command, sizeof(command), "VALVE_SET_POSITION",
              "{\"valve\":\"V1\",\"position_degrees\":90}");
  uint8_t output[kCommandLifecycleFrameCapacity]{};
  runtime.dispatch(reinterpret_cast<const uint8_t*>(command),
                   std::strlen(command), IDENTITY, session, cache, output,
                   sizeof(output));
  TEST_ASSERT_NOT_NULL(std::strstr(reinterpret_cast<char*>(output),
                                   "\"type\":\"REJECTED\""));
  TEST_ASSERT_EQUAL_UINT32(0, valveIo.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(0, valveIo.pulses);
}

void test_runtime_maps_missing_home_to_valve_motion_timeout() {
  PumpIo pumpIo;
  P1MotionController p1(pumpIo);
  P1MotionController p2(pumpIo);
  ValveIo io;
  ValveMotionController valve(io, true);
  ValveMotionController* pointers[] = {&valve};
  P1CommandRuntime runtime(p1, p2, pointers, 1);
  SessionState session;
  session.establish(NONCE);
  CommandStatusCache cache;
  uint32_t now = 100;
  dispatchAndStart(runtime, session, cache, "VALVE_HOME",
                   "{\"valve\":\"V1\"}", now);
  for (uint16_t i = 0; i < kValveMaximumSearchSteps; ++i) {
    now += kValveStepIntervalUs;
    runtime.update(now, cache);
  }
  const CommandStatusEntry* entry = cache.find(OPERATION);
  TEST_ASSERT_NOT_NULL(entry);
  TEST_ASSERT_EQUAL(CommandState::FAILED, entry->record.state);
  TEST_ASSERT_EQUAL(CommandErrorCode::VALVE_MOTION_TIMEOUT,
                    entry->record.errorCode);
  TEST_ASSERT_EQUAL(ValvePositionTrust::UNTRUSTED, valve.positionTrust());
  TEST_ASSERT_FALSE(io.step);
}

void test_runtime_maps_stuck_home_during_release() {
  PumpIo pumpIo;
  P1MotionController p1(pumpIo);
  P1MotionController p2(pumpIo);
  ValveIo io;
  ValveMotionController valve(io, true);
  establishValveHome(valve, io, 100);
  ValveMotionController* pointers[] = {&valve};
  P1CommandRuntime runtime(p1, p2, pointers, 1);
  SessionState session;
  session.establish(NONCE);
  CommandStatusCache cache;
  uint32_t now = 40000;
  dispatchAndStart(runtime, session, cache, "VALVE_SET_POSITION",
                   "{\"valve\":\"V1\",\"position_degrees\":90}", now);
  for (uint16_t i = 0; i < kValveStepsPer90Degrees; ++i) {
    now += kValveStepIntervalUs;
    runtime.update(now, cache);
  }
  const CommandStatusEntry* entry = cache.find(OPERATION);
  TEST_ASSERT_NOT_NULL(entry);
  TEST_ASSERT_EQUAL(CommandState::FAILED, entry->record.state);
  TEST_ASSERT_EQUAL(CommandErrorCode::VALVE_HOME_SWITCH_STUCK,
                    entry->record.errorCode);
  TEST_ASSERT_EQUAL(ValvePositionTrust::UNTRUSTED, valve.positionTrust());
  TEST_ASSERT_FALSE(io.step);
}

void test_runtime_maps_stable_unexpected_home_during_positioning() {
  PumpIo pumpIo;
  P1MotionController p1(pumpIo);
  P1MotionController p2(pumpIo);
  ValveIo io;
  ValveMotionController valve(io, true);
  establishValveHome(valve, io, 100);
  ValveMotionController* pointers[] = {&valve};
  P1CommandRuntime runtime(p1, p2, pointers, 1);
  SessionState session;
  session.establish(NONCE);
  CommandStatusCache cache;
  uint32_t now = 40000;
  dispatchAndStart(runtime, session, cache, "VALVE_SET_POSITION",
                   "{\"valve\":\"V1\",\"position_degrees\":90}", now);
  io.home = false;
  runtime.update(now, cache);
  now += kValveHomeStableUs;
  runtime.update(now, cache);
  now += kValveStepIntervalUs;
  runtime.update(now, cache);
  io.home = true;
  runtime.update(++now, cache);
  runtime.update(now + kValveHomeStableUs, cache);
  const CommandStatusEntry* entry = cache.find(OPERATION);
  TEST_ASSERT_NOT_NULL(entry);
  TEST_ASSERT_EQUAL(CommandState::FAILED, entry->record.state);
  TEST_ASSERT_EQUAL(CommandErrorCode::VALVE_HOME_SWITCH_UNEXPECTED,
                    entry->record.errorCode);
  TEST_ASSERT_EQUAL(ValvePositionTrust::UNTRUSTED, valve.positionTrust());
  TEST_ASSERT_FALSE(io.step);
}

void test_each_valve_parks_only_after_started_and_replays_without_movement() {
  for (uint8_t selected = 0; selected < 8; ++selected) {
    PumpIo pumpIo;
    P1MotionController p1(pumpIo);
    P1MotionController p2(pumpIo);
    ValveIo io[8];
    ValveMotionController valves[] = {
        {io[0], true}, {io[1], false}, {io[2], true}, {io[3], true},
        {io[4], true}, {io[5], false}, {io[6], true}, {io[7], true}};
    ValveMotionController* pointers[] = {&valves[0], &valves[1], &valves[2], &valves[3],
                                        &valves[4], &valves[5], &valves[6], &valves[7]};
    establishValveHome(valves[selected], io[selected], 0);
    P1CommandRuntime runtime(p1, p2, pointers, 8);
    SessionState session;
    session.establish(NONCE);
    CommandStatusCache cache;
    char arguments[64];
    std::snprintf(arguments, sizeof(arguments),
                  "{\"valve\":\"V%u\",\"position_degrees\":5}", selected + 1U);
    char command[384];
    makeCommand(command, sizeof(command), "VALVE_SET_POSITION", arguments);
    uint8_t output[kCommandLifecycleFrameCapacity]{};
    runtime.dispatch(reinterpret_cast<const uint8_t*>(command), std::strlen(command),
                     IDENTITY, session, cache, output, sizeof(output));
    TEST_ASSERT_NOT_NULL(std::strstr(reinterpret_cast<char*>(output), "\"type\":\"ACCEPTED\""));
    TEST_ASSERT_EQUAL_UINT32(0, io[selected].directionWrites);
    size_t length = 0;
    bool startsMotion = false;
    TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(IDENTITY, cache, output, sizeof(output), length, startsMotion));
    TEST_ASSERT_TRUE(startsMotion);
    TEST_ASSERT_EQUAL_UINT32(0, io[selected].directionWrites);
    uint32_t now = kValveHomeStableUs;
    TEST_ASSERT_TRUE(runtime.confirmStartedFrameWritten(now, cache));
    for (uint16_t step = 0; step < kValveParkHomeSteps; ++step) {
      now += kValveStepIntervalUs;
      runtime.update(now, cache);
    }
    TEST_ASSERT_EQUAL(CommandState::STARTED, cache.find(OPERATION)->record.state);
    io[selected].home = false;
    runtime.update(++now, cache);
    runtime.update(now + kValveHomeStableUs, cache);
    TEST_ASSERT_EQUAL(CommandState::COMPLETED, cache.find(OPERATION)->record.state);
    TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(IDENTITY, cache, output, sizeof(output), length, startsMotion));
    runtime.dispatch(reinterpret_cast<const uint8_t*>(command), std::strlen(command),
                     IDENTITY, session, cache, output, sizeof(output));
    TEST_ASSERT_NOT_NULL(std::strstr(reinterpret_cast<char*>(output), "\"type\":\"COMPLETED\""));
    for (uint8_t other = 0; other < 8; ++other)
      TEST_ASSERT_EQUAL_UINT32(other == selected ? kValveParkHomeSteps : 0, io[other].pulses);
    TEST_ASSERT_EQUAL_UINT16(5, valves[selected].positionDegrees());
  }
}

void test_parking_unreleased_switch_maps_to_cached_failure_without_extra_motion() {
  PumpIo pumpIo;
  P1MotionController p1(pumpIo);
  P1MotionController p2(pumpIo);
  ValveIo io;
  ValveMotionController valve(io, true);
  establishValveHome(valve, io, 0);
  ValveMotionController* pointers[] = {&valve};
  P1CommandRuntime runtime(p1, p2, pointers, 1);
  SessionState session;
  session.establish(NONCE);
  CommandStatusCache cache;
  uint32_t now = kValveHomeStableUs;
  dispatchAndStart(runtime, session, cache, "VALVE_SET_POSITION",
                   "{\"valve\":\"V1\",\"position_degrees\":5}", now);
  for (uint16_t step = 0; step < kValveParkHomeSteps; ++step) {
    now += kValveStepIntervalUs;
    runtime.update(now, cache);
  }
  runtime.update(now + 2 * kValveHomeStableUs, cache);
  TEST_ASSERT_EQUAL(CommandState::FAILED, cache.find(OPERATION)->record.state);
  TEST_ASSERT_EQUAL(CommandErrorCode::VALVE_HOME_SWITCH_STUCK, cache.find(OPERATION)->record.errorCode);
  TEST_ASSERT_TRUE(cache.find(OPERATION)->record.executionStarted);
  TEST_ASSERT_EQUAL_UINT16(22, io.pulses);
  TEST_ASSERT_FALSE(io.step);
  TEST_ASSERT_EQUAL(ValvePositionTrust::UNTRUSTED, valve.positionTrust());
}

}  // namespace

void setUp() {}
void tearDown() {}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_v8_home_waits_for_complete_started_frame_then_selects_only_v8);
  RUN_TEST(test_position_requires_that_selected_valve_has_been_homed);
  RUN_TEST(test_runtime_maps_missing_home_to_valve_motion_timeout);
  RUN_TEST(test_runtime_maps_stuck_home_during_release);
  RUN_TEST(test_runtime_maps_stable_unexpected_home_during_positioning);
  RUN_TEST(test_each_valve_parks_only_after_started_and_replays_without_movement);
  RUN_TEST(test_parking_unreleased_switch_maps_to_cached_failure_without_extra_motion);
  return UNITY_END();
}
