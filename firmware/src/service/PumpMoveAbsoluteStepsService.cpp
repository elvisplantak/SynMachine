#include "service/PumpMoveAbsoluteStepsService.h"

#include <string.h>

namespace labforge {
namespace {

CommandStatusRecord makeRecord(const InboundMessage& message,
                               const PumpMoveAbsoluteStepsCommand& command,
                               CommandState state) {
  CommandStatusRecord record{};
  memcpy(record.operationCommandId, message.operationCommandId,
         sizeof(record.operationCommandId));
  memcpy(record.phaseExecutionId, message.phaseExecutionId,
         sizeof(record.phaseExecutionId));
  record.phaseExecutionIdKnown = true;
  record.semanticIdentityKnown = true;
  record.semanticIdentity = semanticIdentity(command);
  record.state = state;
  record.errorCode = CommandErrorCode::NONE;
  record.executionStarted = false;
  return record;
}

}  // namespace

PumpMoveServiceStatus PumpMoveAbsoluteStepsService::execute(
    const InboundMessage& message, CommandStatusCache& cache,
    PumpMoveAbsoluteStepsExecutor& executor) const {
  PumpMoveAbsoluteStepsCommand command{};
  const PumpMoveContractStatus contract =
      parsePumpMoveAbsoluteSteps(message, command);
  if (contract == PumpMoveContractStatus::UNSUPPORTED_COMMAND)
    return PumpMoveServiceStatus::UNSUPPORTED_COMMAND;
  if (contract != PumpMoveContractStatus::VALID)
    return PumpMoveServiceStatus::INVALID_ARGUMENTS;

  const CommandStatusEntry* existing = cache.find(message.operationCommandId);
  if (existing != nullptr) {
    const CommandSemanticIdentity identity = semanticIdentity(command);
    if (!existing->record.phaseExecutionIdKnown ||
        strcmp(existing->record.phaseExecutionId,
               message.phaseExecutionId) != 0 ||
        !existing->record.semanticIdentityKnown ||
        !commandSemanticIdentityEqual(existing->record.semanticIdentity,
                                      identity)) {
      return PumpMoveServiceStatus::COMMAND_ID_CONFLICT;
    }
    return PumpMoveServiceStatus::REPLAYED;
  }

  if (executor.preflight(command) != PumpMovePreflightOutcome::READY)
    return PumpMoveServiceStatus::PREFLIGHT_REJECTED;

  CommandStatusRecord record =
      makeRecord(message, command, CommandState::ACCEPTED);
  const CommandStatusStoreResult accepted = cache.storeDetailed(record);
  if (accepted == CommandStatusStoreResult::BUSY)
    return PumpMoveServiceStatus::CONTROLLER_BUSY;
  if (accepted != CommandStatusStoreResult::STORED)
    return PumpMoveServiceStatus::CACHE_ERROR;
  record.state = CommandState::STARTED;
  if (!cache.store(record)) return PumpMoveServiceStatus::CACHE_ERROR;

  const PumpMoveExecutionOutcome outcome = executor.execute(command);
  if (outcome == PumpMoveExecutionOutcome::COMPLETED) {
    record.state = CommandState::COMPLETED;
  } else if (outcome == PumpMoveExecutionOutcome::MOTION_TIMEOUT) {
    record.state = CommandState::FAILED;
    record.executionStarted = true;
    record.errorCode = CommandErrorCode::PUMP_MOTION_TIMEOUT;
  } else if (outcome == PumpMoveExecutionOutcome::HOME_SWITCH_UNEXPECTED) {
    record.state = CommandState::FAILED;
    record.executionStarted = true;
    record.errorCode = CommandErrorCode::PUMP_HOME_SWITCH_UNEXPECTED;
  } else {
    return PumpMoveServiceStatus::CACHE_ERROR;
  }
  if (!cache.store(record)) return PumpMoveServiceStatus::CACHE_ERROR;
  return outcome == PumpMoveExecutionOutcome::COMPLETED
             ? PumpMoveServiceStatus::COMPLETED
             : PumpMoveServiceStatus::FAILED;
}

}  // namespace labforge
