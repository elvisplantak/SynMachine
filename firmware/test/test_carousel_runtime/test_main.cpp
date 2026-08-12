#include <unity.h>

#include <cstdio>
#include <cstring>

#include "actuator/ColumnBottomValveMotionController.h"
#include "protocol/CommandLifecycleWriter.h"
#include "protocol/HelloOkWriter.h"
#include "service/P1CommandRuntime.h"

using namespace labforge;

namespace {
constexpr char NONCE[] = "123e4567-e89b-12d3-a456-426614174000";
constexpr char NONCE_B[] = "223e4567-e89b-12d3-a456-426614174001";
constexpr BootIdentityResult IDENTITY{true, 7, IdentityFailureReason::NONE};

class PumpIo : public P1MotionIo {
 public:
  bool homeActive() const override { return false; }
  void writeDirection(bool) override {}
  void writeStep(bool) override {}
  void pulseStep(uint16_t) override {}
};
class ValveIo : public ValveMotionIo {
 public:
  bool home = false;
  bool homeActive() const override { return home; }
  void writeDirection(bool) override {}
  void writeStep(bool) override {}
  void pulseStep(uint16_t) override { ++pulses; }
  uint32_t pulses = 0;
};
class CarouselIo : public CarouselMotionIo {
 public:
  void writeDirection(bool high) override { direction = high; ++directionWrites; }
  void writeStep(bool high) override { step = high; }
  void pulseStep(uint16_t width) override { ++pulses; lastWidth = width; step = false; }
  bool direction = false;
  bool step = false;
  uint16_t directionWrites = 0;
  uint16_t pulses = 0;
  uint16_t lastWidth = 0;
};

void makeCommandForNonce(char* frame, size_t capacity, const char* nonce,
                         const char* operation, const char* command,
                         uint8_t position) {
  std::snprintf(frame, capacity,
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\","
      "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":7,"
      "\"phase_execution_id\":\"phase-1\","
      "\"operation_command_id\":\"%s\",\"command\":\"%s\","
      "\"arguments\":{\"position\":%u}}",
      nonce, operation, command, position);
}

void makeCommand(char* frame, size_t capacity, const char* operation,
                 const char* command, uint8_t position) {
  makeCommandForNonce(frame, capacity, NONCE, operation, command, position);
}

void closeColumn(ColumnBottomValveMotionController& column, ValveIo& io) {
  TEST_ASSERT_EQUAL(ColumnValvePrepareResult::READY, column.prepareHome());
  TEST_ASSERT_TRUE(column.start(0));
  io.home = true;
  column.update(1);
  TEST_ASSERT_EQUAL(ColumnValveMotionResult::COMPLETED,
                    column.update(1 + kColumnValveHomeStableUs));
  TEST_ASSERT_EQUAL(ColumnValvePrepareResult::READY,
                    column.prepareSetPosition(4));
  TEST_ASSERT_TRUE(column.start(40000));
  io.home = false;
  uint32_t now = 40000;
  for (uint16_t i = 0; i < kColumnValveClosedSteps + 100 && column.busy(); ++i) {
    now += kColumnValveStepIntervalUs;
    column.update(now);
  }
  TEST_ASSERT_EQUAL_UINT32(kColumnValveClosedSteps, column.positionSteps());
}

void completeLifecycle(P1CommandRuntime& runtime, CommandStatusCache& cache,
                       uint8_t* output, size_t capacity, uint32_t now) {
  size_t length = 0;
  bool startsMotion = false;
  TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(IDENTITY, cache, output, capacity,
                                              length, startsMotion));
  TEST_ASSERT_TRUE(startsMotion);
  TEST_ASSERT_TRUE(runtime.confirmStartedFrameWritten(now, cache));
}

void test_reference_has_truthful_lifecycle_and_no_gpio() {
  PumpIo pumpIo; P1MotionController p1(pumpIo), p2(pumpIo);
  ValveIo columnIo; ColumnBottomValveMotionController column(columnIo);
  CarouselIo io; CarouselMotionController carousel(io);
  P1CommandRuntime runtime(p1, p2, nullptr, 0, column, carousel);
  SessionState session; session.establish(NONCE); CommandStatusCache cache;
  char command[384]; uint8_t output[kCommandLifecycleFrameCapacity]{};
  makeCommand(command, sizeof(command), "323e4567-e89b-12d3-a456-426614174002",
              "CAROUSEL_SET_REFERENCE", 7);
  const DispatchResult accepted = runtime.dispatch(
      reinterpret_cast<const uint8_t*>(command), std::strlen(command), IDENTITY,
      session, cache, output, sizeof(output));
  TEST_ASSERT_GREATER_THAN_UINT32(0, accepted.outputLength);
  TEST_ASSERT_EQUAL_UINT16(0, io.directionWrites);
  completeLifecycle(runtime, cache, output, sizeof(output), 100);
  TEST_ASSERT_EQUAL_UINT16(0, io.directionWrites);
  runtime.update(100, cache);
  TEST_ASSERT_EQUAL_UINT8(7, carousel.position());
  TEST_ASSERT_EQUAL(CarouselPositionTrust::TRUSTED, carousel.positionTrust());
}

void test_move_requires_trusted_closed_column() {
  PumpIo pumpIo; P1MotionController p1(pumpIo), p2(pumpIo);
  ValveIo columnIo; ColumnBottomValveMotionController column(columnIo);
  CarouselIo io; CarouselMotionController carousel(io);
  carousel.prepareSetReference(1); carousel.start(0); carousel.update(0);
  P1CommandRuntime runtime(p1, p2, nullptr, 0, column, carousel);
  SessionState session; session.establish(NONCE); CommandStatusCache cache;
  char command[384]; uint8_t output[kCommandLifecycleFrameCapacity]{};
  makeCommand(command, sizeof(command), "323e4567-e89b-12d3-a456-426614174003",
              "CAROUSEL_MOVE_TO_POSITION", 2);
  runtime.dispatch(reinterpret_cast<const uint8_t*>(command), std::strlen(command),
                   IDENTITY, session, cache, output, sizeof(output));
  TEST_ASSERT_NOT_NULL(std::strstr(reinterpret_cast<char*>(output),
                                  "CAROUSEL_COLUMN_VALVE_NOT_CLOSED"));
  TEST_ASSERT_EQUAL_UINT16(0, io.directionWrites);
}

void test_move_waits_for_started_then_completes_250_pulses() {
  PumpIo pumpIo; P1MotionController p1(pumpIo), p2(pumpIo);
  ValveIo columnIo; ColumnBottomValveMotionController column(columnIo);
  closeColumn(column, columnIo);
  CarouselIo io; CarouselMotionController carousel(io);
  carousel.prepareSetReference(1); carousel.start(0); carousel.update(0);
  P1CommandRuntime runtime(p1, p2, nullptr, 0, column, carousel);
  SessionState session; session.establish(NONCE); CommandStatusCache cache;
  char command[384]; uint8_t output[kCommandLifecycleFrameCapacity]{};
  makeCommand(command, sizeof(command), "323e4567-e89b-12d3-a456-426614174004",
              "CAROUSEL_MOVE_TO_POSITION", 2);
  runtime.dispatch(reinterpret_cast<const uint8_t*>(command), std::strlen(command),
                   IDENTITY, session, cache, output, sizeof(output));
  TEST_ASSERT_EQUAL_UINT16(0, io.directionWrites);
  completeLifecycle(runtime, cache, output, sizeof(output), 100);
  TEST_ASSERT_EQUAL_UINT16(1, io.directionWrites);
  TEST_ASSERT_TRUE(io.direction);
  uint32_t now = 100;
  for (uint16_t i = 0; i < 250; ++i) {
    now += 7000;
    runtime.update(now, cache);
  }
  TEST_ASSERT_EQUAL_UINT16(250, io.pulses);
  TEST_ASSERT_EQUAL_UINT16(kCarouselStepHighUs, io.lastWidth);
}

void test_started_abort_is_failed_and_invalidates_position_trust() {
  PumpIo pumpIo; P1MotionController p1(pumpIo), p2(pumpIo);
  ValveIo columnIo; ColumnBottomValveMotionController column(columnIo);
  closeColumn(column, columnIo);
  CarouselIo io; CarouselMotionController carousel(io);
  carousel.prepareSetReference(1); carousel.start(0); carousel.update(0);
  P1CommandRuntime runtime(p1, p2, nullptr, 0, column, carousel);
  SessionState session; session.establish(NONCE); CommandStatusCache cache;
  char command[384]; uint8_t output[kCommandLifecycleFrameCapacity]{};
  constexpr char operation[] = "323e4567-e89b-12d3-a456-426614174005";
  makeCommand(command, sizeof(command), operation,
              "CAROUSEL_MOVE_TO_POSITION", 2);
  runtime.dispatch(reinterpret_cast<const uint8_t*>(command), std::strlen(command),
                   IDENTITY, session, cache, output, sizeof(output));
  completeLifecycle(runtime, cache, output, sizeof(output), 100);
  runtime.update(7000, cache);
  TEST_ASSERT_EQUAL_UINT16(1, io.pulses);
  TEST_ASSERT_TRUE(runtime.abort(cache));
  TEST_ASSERT_FALSE(io.step);
  TEST_ASSERT_EQUAL(CarouselPositionTrust::UNTRUSTED,
                    carousel.positionTrust());
  const CommandStatusEntry* entry = cache.find(operation);
  TEST_ASSERT_NOT_NULL(entry);
  TEST_ASSERT_EQUAL(CommandState::FAILED, entry->record.state);
  TEST_ASSERT_EQUAL(CommandErrorCode::COMMAND_ABORTED,
                    entry->record.errorCode);
}

void test_started_reference_abort_is_failed_and_invalidates_previous_trust() {
  PumpIo pumpIo; P1MotionController p1(pumpIo), p2(pumpIo);
  ValveIo columnIo; ColumnBottomValveMotionController column(columnIo);
  CarouselIo io; CarouselMotionController carousel(io);
  carousel.prepareSetReference(5); carousel.start(0); carousel.update(0);
  P1CommandRuntime runtime(p1, p2, nullptr, 0, column, carousel);
  SessionState session; session.establish(NONCE); CommandStatusCache cache;
  char command[384]; uint8_t output[kCommandLifecycleFrameCapacity]{};
  constexpr char operation[] = "323e4567-e89b-12d3-a456-426614174007";
  makeCommand(command, sizeof(command), operation,
              "CAROUSEL_SET_REFERENCE", 12);
  runtime.dispatch(reinterpret_cast<const uint8_t*>(command), std::strlen(command),
                   IDENTITY, session, cache, output, sizeof(output));
  completeLifecycle(runtime, cache, output, sizeof(output), 100);
  TEST_ASSERT_TRUE(runtime.abort(cache));
  TEST_ASSERT_EQUAL_UINT16(0, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT16(0, io.pulses);
  TEST_ASSERT_FALSE(io.step);
  TEST_ASSERT_EQUAL(CarouselPositionTrust::UNTRUSTED,
                    carousel.positionTrust());
  const CommandStatusEntry* entry = cache.find(operation);
  TEST_ASSERT_NOT_NULL(entry);
  TEST_ASSERT_EQUAL(CommandState::FAILED, entry->record.state);
  TEST_ASSERT_TRUE(entry->record.executionStarted);
  TEST_ASSERT_EQUAL(CommandErrorCode::COMMAND_ABORTED,
                    entry->record.errorCode);
}

void test_session_replacement_invalidates_idle_reference_without_gpio() {
  PumpIo pumpIo; P1MotionController p1(pumpIo), p2(pumpIo);
  ValveIo columnIo; ColumnBottomValveMotionController column(columnIo);
  closeColumn(column, columnIo);
  CarouselIo io; CarouselMotionController carousel(io);
  carousel.prepareSetReference(5); carousel.start(0); carousel.update(0);
  P1CommandRuntime runtime(p1, p2, nullptr, 0, column, carousel);
  SessionState session; session.establish(NONCE); CommandStatusCache cache;
  uint8_t output[kHelloOkFrameCapacity]{};
  const char hello[] =
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO\","
      "\"backend_session_nonce\":\"223e4567-e89b-12d3-a456-426614174001\"}";
  const DispatchResult result = runtime.dispatch(
      reinterpret_cast<const uint8_t*>(hello), std::strlen(hello), IDENTITY,
      session, cache, output, sizeof(output));
  TEST_ASSERT_GREATER_THAN_UINT32(0, result.outputLength);
  TEST_ASSERT_EQUAL_STRING(NONCE_B, session.nonce());
  TEST_ASSERT_EQUAL(CarouselPositionTrust::UNTRUSTED,
                    carousel.positionTrust());
  TEST_ASSERT_EQUAL_UINT16(0, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT16(0, io.pulses);

  constexpr char operation[] = "323e4567-e89b-12d3-a456-426614174008";
  char command[384];
  makeCommandForNonce(command, sizeof(command), NONCE_B, operation,
                      "CAROUSEL_MOVE_TO_POSITION", 6);
  runtime.dispatch(reinterpret_cast<const uint8_t*>(command), std::strlen(command),
                   IDENTITY, session, cache, output, sizeof(output));
  const CommandStatusEntry* entry = cache.find(operation);
  TEST_ASSERT_NOT_NULL(entry);
  TEST_ASSERT_EQUAL(CommandState::REJECTED, entry->record.state);
  TEST_ASSERT_EQUAL_UINT16(0, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT16(0, io.pulses);
}

void test_session_replacement_during_move_does_not_replay_and_leaves_untrusted() {
  PumpIo pumpIo; P1MotionController p1(pumpIo), p2(pumpIo);
  ValveIo columnIo; ColumnBottomValveMotionController column(columnIo);
  closeColumn(column, columnIo);
  CarouselIo io; CarouselMotionController carousel(io);
  carousel.prepareSetReference(1); carousel.start(0); carousel.update(0);
  P1CommandRuntime runtime(p1, p2, nullptr, 0, column, carousel);
  SessionState session; session.establish(NONCE); CommandStatusCache cache;
  char command[384]; uint8_t output[kHelloOkFrameCapacity]{};
  constexpr char operation[] = "323e4567-e89b-12d3-a456-426614174006";
  makeCommand(command, sizeof(command), operation,
              "CAROUSEL_MOVE_TO_POSITION", 2);
  runtime.dispatch(reinterpret_cast<const uint8_t*>(command), std::strlen(command),
                   IDENTITY, session, cache, output, sizeof(output));
  completeLifecycle(runtime, cache, output, sizeof(output), 100);
  runtime.update(7000, cache);
  TEST_ASSERT_EQUAL_UINT16(1, io.pulses);
  const char hello[] =
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO\","
      "\"backend_session_nonce\":\"223e4567-e89b-12d3-a456-426614174001\"}";
  runtime.dispatch(reinterpret_cast<const uint8_t*>(hello), std::strlen(hello),
                   IDENTITY, session, cache, output, sizeof(output));
  TEST_ASSERT_EQUAL_UINT16(1, io.pulses);
  TEST_ASSERT_EQUAL_UINT16(1, io.directionWrites);
  uint32_t now = 7000;
  for (uint16_t i = 1; i < kCarouselPulsesPerPosition; ++i) {
    now += kCarouselStartIntervalUs;
    runtime.update(now, cache);
  }
  TEST_ASSERT_EQUAL_UINT16(kCarouselPulsesPerPosition, io.pulses);
  TEST_ASSERT_EQUAL_UINT16(1, io.directionWrites);
  TEST_ASSERT_EQUAL(CarouselPositionTrust::UNTRUSTED,
                    carousel.positionTrust());
  const CommandStatusEntry* entry = cache.find(operation);
  TEST_ASSERT_NOT_NULL(entry);
  TEST_ASSERT_EQUAL(CommandState::COMPLETED, entry->record.state);
}
}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_reference_has_truthful_lifecycle_and_no_gpio);
  RUN_TEST(test_move_requires_trusted_closed_column);
  RUN_TEST(test_move_waits_for_started_then_completes_250_pulses);
  RUN_TEST(test_started_abort_is_failed_and_invalidates_position_trust);
  RUN_TEST(test_started_reference_abort_is_failed_and_invalidates_previous_trust);
  RUN_TEST(test_session_replacement_invalidates_idle_reference_without_gpio);
  RUN_TEST(test_session_replacement_during_move_does_not_replay_and_leaves_untrusted);
  return UNITY_END();
}
