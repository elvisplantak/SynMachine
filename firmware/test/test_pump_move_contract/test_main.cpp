#include <unity.h>

#include <stdio.h>
#include <string.h>

#include "protocol/MessageParser.h"
#include "protocol/PumpMoveAbsoluteStepsContract.h"
#include "service/PumpMoveAbsoluteStepsService.h"

using namespace labforge;

namespace {

constexpr char NONCE[] = "123e4567-e89b-12d3-a456-426614174000";
constexpr char OPERATION[] = "323e4567-e89b-12d3-a456-426614174002";

InboundMessage parseCommand(const char* arguments,
                            const char* operation = OPERATION,
                            const char* phase = "phase-1",
                            const char* command = "PUMP_MOVE_ABSOLUTE_STEPS") {
  char frame[512];
  snprintf(frame, sizeof(frame),
           "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\","
           "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":7,"
           "\"phase_execution_id\":\"%s\",\"operation_command_id\":\"%s\","
           "\"command\":\"%s\",\"arguments\":%s}",
           NONCE, phase, operation, command, arguments);
  const ParseResult parsed = MessageParser().parse(
      reinterpret_cast<const uint8_t*>(frame), strlen(frame));
  TEST_ASSERT_EQUAL(ParseStatus::VALID_MESSAGE, parsed.status);
  return parsed.message;
}

class FakeExecutor : public PumpMoveAbsoluteStepsExecutor {
 public:
  PumpMovePreflightOutcome preflightOutcome = PumpMovePreflightOutcome::READY;
  PumpMoveExecutionOutcome outcome = PumpMoveExecutionOutcome::COMPLETED;
  unsigned preflightCalls = 0;
  unsigned calls = 0;
  PumpMoveAbsoluteStepsCommand last{};

  PumpMovePreflightOutcome preflight(
      const PumpMoveAbsoluteStepsCommand& command) override {
    ++preflightCalls;
    last = command;
    return preflightOutcome;
  }

  PumpMoveExecutionOutcome execute(
      const PumpMoveAbsoluteStepsCommand& command) override {
    ++calls;
    last = command;
    return outcome;
  }
};

void test_contract_accepts_only_exact_p1_schema_in_any_key_order() {
  PumpMoveAbsoluteStepsCommand command{};
  InboundMessage message =
      parseCommand("{\"pump\":\"P1\",\"target_steps\":10000}");
  TEST_ASSERT_EQUAL(PumpMoveContractStatus::VALID,
                    parsePumpMoveAbsoluteSteps(message, command));
  TEST_ASSERT_EQUAL(PumpId::P1, command.pump);
  TEST_ASSERT_EQUAL_UINT16(10000, command.targetSteps);

  message = parseCommand("{\"target_steps\":20500,\"pump\":\"P1\"}");
  TEST_ASSERT_EQUAL(PumpMoveContractStatus::VALID,
                    parsePumpMoveAbsoluteSteps(message, command));
  TEST_ASSERT_EQUAL_UINT16(20500, command.targetSteps);
}

void test_contract_rejects_wrong_types_ranges_and_extra_arguments() {
  const char* invalid[] = {
      "{\"pump\":\"P2\",\"target_steps\":1}",
      "{\"pump\":\"P1\",\"target_steps\":-1}",
      "{\"pump\":\"P1\",\"target_steps\":20501}",
      "{\"pump\":\"P1\",\"target_steps\":true}",
      "{\"pump\":\"P1\",\"target_steps\":1,\"speed\":2}",
      "{\"pump\":\"P1\"}",
  };
  for (const char* arguments : invalid) {
    PumpMoveAbsoluteStepsCommand command{};
    const InboundMessage message = parseCommand(arguments);
    TEST_ASSERT_EQUAL(PumpMoveContractStatus::INVALID_ARGUMENTS,
                      parsePumpMoveAbsoluteSteps(message, command));
  }
  PumpMoveAbsoluteStepsCommand command{};
  const InboundMessage unsupported =
      parseCommand("{}", OPERATION, "phase-1", "FUTURE_COMMAND");
  TEST_ASSERT_EQUAL(PumpMoveContractStatus::UNSUPPORTED_COMMAND,
                    parsePumpMoveAbsoluteSteps(unsupported, command));
}

void test_service_completes_once_and_exact_replay_never_executes_again() {
  CommandStatusCache cache;
  FakeExecutor executor;
  PumpMoveAbsoluteStepsService service;
  const InboundMessage message =
      parseCommand("{\"pump\":\"P1\",\"target_steps\":10000}");
  TEST_ASSERT_EQUAL(PumpMoveServiceStatus::COMPLETED,
                    service.execute(message, cache, executor));
  TEST_ASSERT_EQUAL_UINT32(1, executor.calls);
  TEST_ASSERT_EQUAL(CommandState::COMPLETED,
                    cache.find(OPERATION)->record.state);
  TEST_ASSERT_EQUAL(PumpMoveServiceStatus::REPLAYED,
                    service.execute(message, cache, executor));
  TEST_ASSERT_EQUAL_UINT32(1, executor.calls);
}

void test_same_operation_with_changed_target_or_phase_conflicts() {
  CommandStatusCache cache;
  FakeExecutor executor;
  PumpMoveAbsoluteStepsService service;
  TEST_ASSERT_EQUAL(PumpMoveServiceStatus::COMPLETED,
                    service.execute(parseCommand(
                        "{\"pump\":\"P1\",\"target_steps\":10000}"),
                                    cache, executor));
  TEST_ASSERT_EQUAL(PumpMoveServiceStatus::COMMAND_ID_CONFLICT,
                    service.execute(parseCommand(
                        "{\"pump\":\"P1\",\"target_steps\":10001}"),
                                    cache, executor));
  TEST_ASSERT_EQUAL(PumpMoveServiceStatus::COMMAND_ID_CONFLICT,
                    service.execute(parseCommand(
                        "{\"pump\":\"P1\",\"target_steps\":10000}",
                        OPERATION, "phase-2"), cache, executor));
  TEST_ASSERT_EQUAL_UINT32(1, executor.calls);
}

void test_fake_execution_failure_is_terminal_and_replayed() {
  CommandStatusCache cache;
  FakeExecutor executor;
  executor.outcome = PumpMoveExecutionOutcome::MOTION_TIMEOUT;
  PumpMoveAbsoluteStepsService service;
  const InboundMessage message =
      parseCommand("{\"pump\":\"P1\",\"target_steps\":5000}");
  TEST_ASSERT_EQUAL(PumpMoveServiceStatus::FAILED,
                    service.execute(message, cache, executor));
  const CommandStatusRecord& record = cache.find(OPERATION)->record;
  TEST_ASSERT_EQUAL(CommandState::FAILED, record.state);
  TEST_ASSERT_TRUE(record.executionStarted);
  TEST_ASSERT_EQUAL(CommandErrorCode::PUMP_MOTION_TIMEOUT, record.errorCode);
  TEST_ASSERT_EQUAL(PumpMoveServiceStatus::REPLAYED,
                    service.execute(message, cache, executor));
  TEST_ASSERT_EQUAL_UINT32(1, executor.calls);
}

void test_failed_preflight_never_starts_or_invokes_executor() {
  CommandStatusCache cache;
  FakeExecutor executor;
  executor.preflightOutcome = PumpMovePreflightOutcome::NOT_READY;
  PumpMoveAbsoluteStepsService service;
  const InboundMessage message =
      parseCommand("{\"pump\":\"P1\",\"target_steps\":5000}");
  TEST_ASSERT_EQUAL(PumpMoveServiceStatus::PREFLIGHT_REJECTED,
                    service.execute(message, cache, executor));
  TEST_ASSERT_EQUAL_UINT32(1, executor.preflightCalls);
  TEST_ASSERT_EQUAL_UINT32(0, executor.calls);
  TEST_ASSERT_NULL(cache.find(OPERATION));
}

void test_unknown_executor_outcome_fails_closed_without_invented_reason() {
  CommandStatusCache cache;
  FakeExecutor executor;
  executor.outcome = static_cast<PumpMoveExecutionOutcome>(255);
  PumpMoveAbsoluteStepsService service;
  const InboundMessage message =
      parseCommand("{\"pump\":\"P1\",\"target_steps\":5000}");
  TEST_ASSERT_EQUAL(PumpMoveServiceStatus::CACHE_ERROR,
                    service.execute(message, cache, executor));
  TEST_ASSERT_EQUAL_UINT32(1, executor.calls);
  const CommandStatusRecord& record = cache.find(OPERATION)->record;
  TEST_ASSERT_EQUAL(CommandState::STARTED, record.state);
  TEST_ASSERT_EQUAL(CommandErrorCode::NONE, record.errorCode);
}

void test_busy_cache_is_distinct_from_internal_cache_error() {
  CommandStatusCache cache;
  CommandStatusRecord active{};
  strcpy(active.operationCommandId,
         "423e4567-e89b-12d3-a456-426614174003");
  strcpy(active.phaseExecutionId, "other-phase");
  active.phaseExecutionIdKnown = true;
  active.semanticIdentityKnown = true;
  active.semanticIdentity = {CommandKind::PUMP_MOVE_ABSOLUTE_STEPS, PumpId::P1,
                             100};
  active.state = CommandState::ACCEPTED;
  active.errorCode = CommandErrorCode::NONE;
  TEST_ASSERT_TRUE(cache.store(active));

  FakeExecutor executor;
  PumpMoveAbsoluteStepsService service;
  const InboundMessage message =
      parseCommand("{\"pump\":\"P1\",\"target_steps\":5000}");
  TEST_ASSERT_EQUAL(PumpMoveServiceStatus::CONTROLLER_BUSY,
                    service.execute(message, cache, executor));
  TEST_ASSERT_EQUAL_UINT32(0, executor.calls);
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_contract_accepts_only_exact_p1_schema_in_any_key_order);
  RUN_TEST(test_contract_rejects_wrong_types_ranges_and_extra_arguments);
  RUN_TEST(test_service_completes_once_and_exact_replay_never_executes_again);
  RUN_TEST(test_same_operation_with_changed_target_or_phase_conflicts);
  RUN_TEST(test_fake_execution_failure_is_terminal_and_replayed);
  RUN_TEST(test_failed_preflight_never_starts_or_invokes_executor);
  RUN_TEST(test_unknown_executor_outcome_fails_closed_without_invented_reason);
  RUN_TEST(test_busy_cache_is_distinct_from_internal_cache_error);
  return UNITY_END();
}
