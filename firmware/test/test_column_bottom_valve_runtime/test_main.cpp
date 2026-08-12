#include <unity.h>

#include <cstdio>
#include <cstring>

#include "actuator/ColumnBottomValveMotionController.h"
#include "actuator/P1MotionController.h"
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

class MotionIo final : public ValveMotionIo {
 public:
  bool home = false;
  unsigned directionWrites = 0;
  uint32_t pulses = 0;
  bool step = false;
  bool direction = true;
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
      "\"arguments\":%s}",
      NONCE, OPERATION, command, arguments);
}

void test_home_waits_for_started_transport_and_completes_truthfully() {
  PumpIo pumpIo;
  P1MotionController p1(pumpIo);
  P1MotionController p2(pumpIo);
  MotionIo ordinaryIo;
  ValveMotionController ordinary(ordinaryIo, true);
  ValveMotionController* valves[] = {&ordinary};
  MotionIo columnIo;
  ColumnBottomValveMotionController column(columnIo);
  P1CommandRuntime runtime(p1, p2, valves, 1, column);
  SessionState session;
  session.establish(NONCE);
  CommandStatusCache cache;
  char command[384];
  makeCommand(command, sizeof(command), "COLUMN_BOTTOM_VALVE_HOME", "{}");
  uint8_t output[kCommandLifecycleFrameCapacity]{};

  const DispatchResult accepted = runtime.dispatch(
      reinterpret_cast<const uint8_t*>(command), std::strlen(command),
      IDENTITY, session, cache, output, sizeof(output));
  TEST_ASSERT_GREATER_THAN_UINT32(0, accepted.outputLength);
  TEST_ASSERT_EQUAL_UINT32(0, columnIo.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(0, ordinaryIo.directionWrites);

  size_t length = 0;
  bool startsMotion = false;
  TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(
      IDENTITY, cache, output, sizeof(output), length, startsMotion));
  TEST_ASSERT_TRUE(startsMotion);
  TEST_ASSERT_EQUAL_UINT32(0, columnIo.directionWrites);
  TEST_ASSERT_TRUE(runtime.confirmStartedFrameWritten(100, cache));
  TEST_ASSERT_EQUAL_UINT32(1, columnIo.directionWrites);
  TEST_ASSERT_FALSE(columnIo.direction);
  TEST_ASSERT_EQUAL_UINT32(0, ordinaryIo.directionWrites);

  columnIo.home = true;
  runtime.update(101, cache);
  runtime.update(101 + kColumnValveHomeStableUs, cache);
  const CommandStatusEntry* entry = cache.find(OPERATION);
  TEST_ASSERT_NOT_NULL(entry);
  TEST_ASSERT_EQUAL(CommandState::COMPLETED, entry->record.state);
  TEST_ASSERT_EQUAL(ColumnValvePositionTrust::TRUSTED,
                    column.positionTrust());
  TEST_ASSERT_FALSE(columnIo.step);
}

void test_position_rejects_untrusted_without_gpio_writes() {
  PumpIo pumpIo;
  P1MotionController p1(pumpIo);
  P1MotionController p2(pumpIo);
  MotionIo columnIo;
  ColumnBottomValveMotionController column(columnIo);
  P1CommandRuntime runtime(p1, p2, nullptr, 0, column);
  SessionState session;
  session.establish(NONCE);
  CommandStatusCache cache;
  char command[384];
  makeCommand(command, sizeof(command), "COLUMN_BOTTOM_VALVE_SET_POSITION",
              "{\"position_degrees\":94}");
  uint8_t output[kCommandLifecycleFrameCapacity]{};
  runtime.dispatch(reinterpret_cast<const uint8_t*>(command),
                   std::strlen(command), IDENTITY, session, cache, output,
                   sizeof(output));
  TEST_ASSERT_NOT_NULL(std::strstr(reinterpret_cast<char*>(output),
                                   "\"type\":\"REJECTED\""));
  TEST_ASSERT_EQUAL_UINT32(0, columnIo.directionWrites);
}

void test_abort_invalidates_trust_and_records_precise_failure() {
  PumpIo pumpIo;
  P1MotionController p1(pumpIo);
  P1MotionController p2(pumpIo);
  MotionIo columnIo;
  ColumnBottomValveMotionController column(columnIo);
  P1CommandRuntime runtime(p1, p2, nullptr, 0, column);
  SessionState session;
  session.establish(NONCE);
  CommandStatusCache cache;
  char command[384];
  makeCommand(command, sizeof(command), "COLUMN_BOTTOM_VALVE_HOME", "{}");
  uint8_t output[kCommandLifecycleFrameCapacity]{};

  runtime.dispatch(reinterpret_cast<const uint8_t*>(command),
                   std::strlen(command), IDENTITY, session, cache, output,
                   sizeof(output));
  size_t length = 0;
  bool startsMotion = false;
  TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(
      IDENTITY, cache, output, sizeof(output), length, startsMotion));
  TEST_ASSERT_TRUE(runtime.confirmStartedFrameWritten(100, cache));
  runtime.update(105, cache);
  TEST_ASSERT_TRUE(runtime.abort(cache));

  const CommandStatusEntry* entry = cache.find(OPERATION);
  TEST_ASSERT_NOT_NULL(entry);
  TEST_ASSERT_EQUAL(CommandState::FAILED, entry->record.state);
  TEST_ASSERT_EQUAL(CommandErrorCode::COMMAND_ABORTED,
                    entry->record.errorCode);
  TEST_ASSERT_TRUE(entry->record.executionStarted);
  TEST_ASSERT_EQUAL(ColumnValvePositionTrust::UNTRUSTED,
                    column.positionTrust());
  TEST_ASSERT_FALSE(columnIo.step);
}

}  // namespace

void setUp() {}
void tearDown() {}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_home_waits_for_started_transport_and_completes_truthfully);
  RUN_TEST(test_position_rejects_untrusted_without_gpio_writes);
  RUN_TEST(test_abort_invalidates_trust_and_records_precise_failure);
  return UNITY_END();
}
