#include "service/P1CommandRuntime.h"

#include <string.h>

#include "protocol/CommandLifecycleWriter.h"
#include "protocol/ProtocolErrorWriter.h"
#include "protocol/PumpHomeContract.h"
#include "protocol/PumpMoveAbsoluteStepsContract.h"

namespace labforge {
namespace {

CommandStatusRecord makeRecord(
    const InboundMessage& message, CommandState state,
    const CommandSemanticIdentity* semanticIdentity = nullptr) {
  CommandStatusRecord record{};
  strcpy(record.operationCommandId, message.operationCommandId);
  strcpy(record.phaseExecutionId, message.phaseExecutionId);
  record.phaseExecutionIdKnown = true;
  record.semanticIdentityKnown = semanticIdentity != nullptr;
  if (semanticIdentity != nullptr) record.semanticIdentity = *semanticIdentity;
  record.state = state;
  return record;
}

CommandErrorCode preflightError(P1PrepareResult result) {
  if (result == P1PrepareResult::BUSY) return CommandErrorCode::CONTROLLER_BUSY;
  return CommandErrorCode::INVALID_FIELD;
}

ProtocolErrorCode sessionError(SessionValidationResult validation) {
  if (validation == SessionValidationResult::HANDSHAKE_REQUIRED)
    return ProtocolErrorCode::HANDSHAKE_REQUIRED;
  if (validation == SessionValidationResult::STALE_SESSION)
    return ProtocolErrorCode::STALE_SESSION;
  if (validation == SessionValidationResult::CONTROLLER_BOOT_MISMATCH)
    return ProtocolErrorCode::CONTROLLER_BOOT_MISMATCH;
  if (validation == SessionValidationResult::CONTROLLER_IDENTITY_UNTRUSTED)
    return ProtocolErrorCode::CONTROLLER_IDENTITY_UNTRUSTED;
  return ProtocolErrorCode::INVALID_FIELD;
}

ErrorCorrelation commandCorrelation(const InboundMessage& message) {
  ErrorCorrelation correlation{};
  correlation.kind = ErrorCorrelationKind::COMMAND;
  strcpy(correlation.backendSessionNonce, message.backendSessionNonce);
  strcpy(correlation.phaseExecutionId, message.phaseExecutionId);
  strcpy(correlation.operationCommandId, message.operationCommandId);
  return correlation;
}

}  // namespace

P1CommandRuntime::P1CommandRuntime(P1MotionController& controller)
    : controller_(controller), protocolDispatcher_(true) {}

DispatchResult P1CommandRuntime::dispatch(
    const uint8_t* payload, size_t length, const BootIdentityResult& identity,
    SessionState& session, CommandStatusCache& cache, uint8_t* output,
    size_t capacity) {
  const ParseResult parsed = parser_.parse(payload, length);
  if (parsed.status != ParseStatus::VALID_MESSAGE ||
      parsed.message.type != MessageType::COMMAND) {
    return protocolDispatcher_.dispatch(payload, length, identity, session,
                                        cache, output, capacity);
  }
  return dispatchCommand(parsed.message, identity, session, cache, output,
                         capacity);
}

DispatchResult P1CommandRuntime::dispatchCommand(
    const InboundMessage& message, const BootIdentityResult& identity,
    SessionState& session, CommandStatusCache& cache, uint8_t* output,
    size_t capacity) {
  size_t outputLength = 0;
  const SessionValidationResult validation = session.validate(
      message.backendSessionNonce, message.controllerBootIdPresence,
      message.controllerBootId, identity);
  if (validation != SessionValidationResult::VALID) {
    writeProtocolError(sessionError(validation), commandCorrelation(message),
                       identity, output, capacity, outputLength);
    return {ParseStatus::VALID_MESSAGE, outputLength};
  }

  PumpHomeCommand home{};
  const PumpHomeContractStatus homeStatus = parsePumpHome(message, home);
  PumpMoveAbsoluteStepsCommand move{};
  const PumpMoveContractStatus moveStatus =
      parsePumpMoveAbsoluteSteps(message, move);

  CommandSemanticIdentity semantic{};
  P1PrepareResult prepared = P1PrepareResult::INVALID_TARGET;
  if (homeStatus == PumpHomeContractStatus::VALID) {
    semantic = semanticIdentity(home);
  } else if (moveStatus == PumpMoveContractStatus::VALID) {
    semantic = semanticIdentity(move);
  } else {
    const bool supported =
        homeStatus != PumpHomeContractStatus::UNSUPPORTED_COMMAND ||
        moveStatus != PumpMoveContractStatus::UNSUPPORTED_COMMAND;
    reject(message, identity, cache,
           supported ? CommandErrorCode::INVALID_FIELD
                     : CommandErrorCode::UNSUPPORTED_COMMAND,
           output, capacity, outputLength);
    return {ParseStatus::VALID_MESSAGE, outputLength};
  }

  const CommandStatusEntry* existing = cache.find(message.operationCommandId);
  if (existing != nullptr) {
    if (!existing->record.phaseExecutionIdKnown ||
        strcmp(existing->record.phaseExecutionId, message.phaseExecutionId) !=
            0 ||
        !existing->record.semanticIdentityKnown ||
        !commandSemanticIdentityEqual(existing->record.semanticIdentity,
                                      semantic)) {
      CommandStatusRecord conflict = makeRecord(
          message, CommandState::REJECTED, &semantic);
      conflict.errorCode = CommandErrorCode::COMMAND_ID_CONFLICT;
      writeCommandLifecycle(message.backendSessionNonce, identity, conflict,
                            output, capacity, outputLength);
    } else {
      writeCommandLifecycle(message.backendSessionNonce, identity,
                            existing->record, output, capacity, outputLength);
    }
    return {ParseStatus::VALID_MESSAGE, outputLength};
  }

  if (cache.active() != nullptr) {
    reject(message, identity, cache, CommandErrorCode::CONTROLLER_BUSY, output,
           capacity, outputLength, &semantic);
    return {ParseStatus::VALID_MESSAGE, outputLength};
  }

  prepared = semantic.command == CommandKind::PUMP_HOME
                 ? controller_.prepareHome()
                 : controller_.prepareMoveAbsolute(semantic.targetSteps);
  if (prepared != P1PrepareResult::READY) {
    reject(message, identity, cache, preflightError(prepared), output,
           capacity, outputLength, &semantic);
    return {ParseStatus::VALID_MESSAGE, outputLength};
  }

  if (!accept(message, semantic, identity, cache, output, capacity,
              outputLength)) {
    controller_.abort();
    outputLength = 0;
  }
  return {ParseStatus::VALID_MESSAGE, outputLength};
}

bool P1CommandRuntime::reject(
    const InboundMessage& message, const BootIdentityResult& identity,
    CommandStatusCache& cache, CommandErrorCode error, uint8_t* output,
    size_t capacity, size_t& outputLength,
    const CommandSemanticIdentity* semanticIdentity) {
  CommandStatusRecord record =
      makeRecord(message, CommandState::REJECTED, semanticIdentity);
  record.errorCode = error;
  const CommandStatusStoreResult stored = cache.storeDetailed(record);
  if (stored != CommandStatusStoreResult::STORED &&
      stored != CommandStatusStoreResult::REPLAYED)
    return false;
  return writeCommandLifecycle(message.backendSessionNonce, identity, record,
                               output, capacity, outputLength);
}

bool P1CommandRuntime::accept(
    const InboundMessage& message,
    const CommandSemanticIdentity& semanticIdentity,
    const BootIdentityResult& identity, CommandStatusCache& cache,
    uint8_t* output, size_t capacity, size_t& outputLength) {
  CommandStatusRecord accepted =
      makeRecord(message, CommandState::ACCEPTED, &semanticIdentity);
  if (!writeCommandLifecycle(message.backendSessionNonce, identity, accepted,
                             output, capacity, outputLength) ||
      cache.storeDetailed(accepted) != CommandStatusStoreResult::STORED)
    return false;
  activeRecord_ = accepted;
  strcpy(lifecycleNonce_, message.backendSessionNonce);
  runtimeState_ = RuntimeState::EMIT_STARTED;
  return true;
}

bool P1CommandRuntime::nextLifecycleFrame(
    const BootIdentityResult& identity, CommandStatusCache& cache,
    uint8_t* output, size_t capacity, size_t& outputLength,
    bool& startsMotion) {
  outputLength = 0;
  startsMotion = false;
  if (runtimeState_ == RuntimeState::EMIT_STARTED) {
    CommandStatusRecord started = activeRecord_;
    started.state = CommandState::STARTED;
    if (!writeCommandLifecycle(lifecycleNonce_, identity, started, output,
                               capacity, outputLength) ||
        !cache.store(started))
      return false;
    activeRecord_ = started;
    runtimeState_ = RuntimeState::WAIT_STARTED_WRITE;
    startsMotion = true;
    return true;
  }
  if (runtimeState_ == RuntimeState::EMIT_TERMINAL) {
    if (!writeCommandLifecycle(lifecycleNonce_, identity, activeRecord_, output,
                               capacity, outputLength))
      return false;
    runtimeState_ = RuntimeState::IDLE;
    return true;
  }
  return false;
}

bool P1CommandRuntime::confirmStartedFrameWritten(uint32_t nowUs) {
  if (runtimeState_ != RuntimeState::WAIT_STARTED_WRITE) return false;
  if (!controller_.start(nowUs)) return false;
  runtimeState_ = RuntimeState::RUNNING;
  return true;
}

void P1CommandRuntime::update(uint32_t nowUs, CommandStatusCache& cache) {
  if (runtimeState_ != RuntimeState::RUNNING) return;
  const P1MotionResult result = controller_.update(nowUs);
  if (result != P1MotionResult::NONE) finish(result, cache);
}

void P1CommandRuntime::finish(P1MotionResult result,
                              CommandStatusCache& cache) {
  if (result == P1MotionResult::COMPLETED) {
    activeRecord_.state = CommandState::COMPLETED;
  } else {
    activeRecord_.state = CommandState::FAILED;
    activeRecord_.executionStarted = true;
    if (result == P1MotionResult::MOTION_TIMEOUT)
      activeRecord_.errorCode = CommandErrorCode::PUMP_MOTION_TIMEOUT;
    else if (result == P1MotionResult::HOME_SWITCH_STUCK)
      activeRecord_.errorCode = CommandErrorCode::PUMP_HOME_SWITCH_STUCK;
    else
      activeRecord_.errorCode =
          CommandErrorCode::PUMP_HOME_SWITCH_UNEXPECTED;
  }
  if (cache.store(activeRecord_)) runtimeState_ = RuntimeState::EMIT_TERMINAL;
}

bool P1CommandRuntime::abort(CommandStatusCache& cache) {
  if (runtimeState_ != RuntimeState::RUNNING || !controller_.abort())
    return false;
  activeRecord_.state = CommandState::FAILED;
  activeRecord_.executionStarted = true;
  activeRecord_.errorCode = CommandErrorCode::COMMAND_ABORTED;
  if (!cache.store(activeRecord_)) return false;
  runtimeState_ = RuntimeState::EMIT_TERMINAL;
  return true;
}

bool P1CommandRuntime::hasPendingLifecycleFrame() const {
  return runtimeState_ == RuntimeState::EMIT_STARTED ||
         runtimeState_ == RuntimeState::EMIT_TERMINAL;
}

}  // namespace labforge
