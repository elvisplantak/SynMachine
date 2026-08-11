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
  bool homeActive() const override { return home; }
  void writeDirection(bool high) override {
    direction = high;
    ++directionWrites;
  }
  void writeStep(bool) override {}
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

}  // namespace

void setUp() {}
void tearDown() {}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_v8_home_waits_for_complete_started_frame_then_selects_only_v8);
  RUN_TEST(test_position_requires_that_selected_valve_has_been_homed);
  return UNITY_END();
}
