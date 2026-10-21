#include "service/P1CommandRuntime.h"

#include <string.h>

#include "protocol/CommandLifecycleWriter.h"
#include "protocol/CarouselContract.h"
#include "protocol/ColumnBottomValveContract.h"
#include "protocol/ProtocolErrorWriter.h"
#include "protocol/PumpHomeContract.h"
#include "protocol/PumpFullAspirationContract.h"
#include "protocol/PumpMoveAbsoluteStepsContract.h"
#include "protocol/SfMixerContract.h"
#include "protocol/ValveHomeContract.h"
#include "protocol/ValveSetPositionContract.h"

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

CommandErrorCode preflightError(ValvePrepareResult result) {
  if (result == ValvePrepareResult::BUSY)
    return CommandErrorCode::CONTROLLER_BUSY;
  return CommandErrorCode::INVALID_FIELD;
}

CommandErrorCode preflightError(ColumnValvePrepareResult result) {
  if (result == ColumnValvePrepareResult::BUSY)
    return CommandErrorCode::CONTROLLER_BUSY;
  return CommandErrorCode::INVALID_FIELD;
}

CommandErrorCode preflightError(CarouselPrepareResult result) {
  if (result == CarouselPrepareResult::BUSY)
    return CommandErrorCode::CONTROLLER_BUSY;
  return CommandErrorCode::INVALID_FIELD;
}

CommandErrorCode preflightError(SfMixerPrepareResult result) {
  if (result == SfMixerPrepareResult::BUSY)
    return CommandErrorCode::CONTROLLER_BUSY;
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
    : p1Controller_(controller), protocolDispatcher_(true) {}

P1CommandRuntime::P1CommandRuntime(P1MotionController& p1Controller,
                                   P1MotionController& p2Controller)
    : p1Controller_(p1Controller),
      p2Controller_(&p2Controller),
      protocolDispatcher_(true) {}

P1CommandRuntime::P1CommandRuntime(
    P1MotionController& p1Controller, P1MotionController& p2Controller,
    ValveMotionController* const* valveControllers,
    uint8_t valveControllerCount)
    : p1Controller_(p1Controller),
      p2Controller_(&p2Controller),
      valveControllers_(valveControllers),
      valveControllerCount_(valveControllerCount),
      protocolDispatcher_(true) {}

P1CommandRuntime::P1CommandRuntime(
    P1MotionController& p1Controller, P1MotionController& p2Controller,
    ValveMotionController* const* valveControllers,
    uint8_t valveControllerCount,
    ColumnBottomValveMotionController& columnValveController,
    CarouselMotionController& carouselController)
    : p1Controller_(p1Controller),
      p2Controller_(&p2Controller),
      valveControllers_(valveControllers),
      valveControllerCount_(valveControllerCount),
      columnValveController_(&columnValveController),
      carouselController_(&carouselController),
      protocolDispatcher_(true, &columnValveController) {}

P1CommandRuntime::P1CommandRuntime(
    P1MotionController& p1Controller, P1MotionController& p2Controller,
    ValveMotionController* const* valveControllers,
    uint8_t valveControllerCount,
    ColumnBottomValveMotionController& columnValveController,
    CarouselMotionController& carouselController,
    SfMixerMotionController& sfMixerController)
    : p1Controller_(p1Controller),
      p2Controller_(&p2Controller),
      valveControllers_(valveControllers),
      valveControllerCount_(valveControllerCount),
      columnValveController_(&columnValveController),
      carouselController_(&carouselController),
      sfMixerController_(&sfMixerController),
      protocolDispatcher_(true, &columnValveController) {}

P1CommandRuntime::P1CommandRuntime(
    P1MotionController& p1Controller, P1MotionController& p2Controller,
    ValveMotionController* const* valveControllers,
    uint8_t valveControllerCount,
    ColumnBottomValveMotionController& columnValveController)
    : p1Controller_(p1Controller),
      p2Controller_(&p2Controller),
      valveControllers_(valveControllers),
      valveControllerCount_(valveControllerCount),
      columnValveController_(&columnValveController),
      protocolDispatcher_(true, &columnValveController) {}

DispatchResult P1CommandRuntime::dispatch(
    const uint8_t* payload, size_t length, const BootIdentityResult& identity,
    SessionState& session, CommandStatusCache& cache, uint8_t* output,
    size_t capacity) {
  const ParseResult parsed = parser_.parse(payload, length);
  if (parsed.status != ParseStatus::VALID_MESSAGE ||
      parsed.message.type != MessageType::COMMAND) {
    const bool replacesSession =
        parsed.status == ParseStatus::VALID_MESSAGE &&
        parsed.message.type == MessageType::HELLO && session.active() &&
        strcmp(session.nonce(), parsed.message.backendSessionNonce) != 0;
    const DispatchResult result = protocolDispatcher_.dispatchParsed(
        parsed, payload, length, identity, session, cache, output, capacity);
    if (replacesSession && result.outputLength > 0)
      handleSessionReplacement(parsed.message.backendSessionNonce);
    return result;
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

  if (!identity.trusted) {
    writeProtocolError(ProtocolErrorCode::CONTROLLER_IDENTITY_UNTRUSTED,
                       commandCorrelation(message), identity, output,
                       capacity, outputLength);
    return {ParseStatus::VALID_MESSAGE, outputLength};
  }

  PumpFullAspirationCommand fullAspiration{};
  const PumpHomeContractStatus fullAspirationStatus =
      parsePumpFullAspiration(message, fullAspiration);
  PumpHomeCommand home{};
  const PumpHomeContractStatus homeStatus = parsePumpHome(message, home);
  PumpMoveAbsoluteStepsCommand move{};
  const PumpMoveContractStatus moveStatus =
      parsePumpMoveAbsoluteSteps(message, move);
  ValveHomeCommand valveHome{};
  const ValveHomeContractStatus valveHomeStatus =
      parseValveHome(message, valveHome);
  ValveSetPositionCommand valvePosition{};
  const ValveSetPositionContractStatus valvePositionStatus =
      parseValveSetPosition(message, valvePosition);
  ColumnBottomValveCommand columnValve{};
  const ColumnValveContractStatus columnValveStatus =
      parseColumnBottomValve(message, columnValve);
  CarouselCommand carousel{};
  const CarouselContractStatus carouselStatus =
      parseCarousel(message, carousel);
  SfMixerCommand sfMixer{};
  const SfMixerContractStatus sfMixerStatus = parseSfMixer(message, sfMixer);

  CommandSemanticIdentity semantic{};
  P1PrepareResult prepared = P1PrepareResult::INVALID_TARGET;
  if (homeStatus == PumpHomeContractStatus::VALID) {
    semantic = semanticIdentity(home);
  } else if (fullAspirationStatus == PumpHomeContractStatus::VALID) {
    semantic = semanticIdentity(fullAspiration);
  } else if (moveStatus == PumpMoveContractStatus::VALID) {
    semantic = semanticIdentity(move);
  } else if (valveHomeStatus == ValveHomeContractStatus::VALID) {
    semantic = semanticIdentity(valveHome);
  } else if (valvePositionStatus == ValveSetPositionContractStatus::VALID) {
    semantic = semanticIdentity(valvePosition);
  } else if (columnValveStatus == ColumnValveContractStatus::VALID) {
    semantic = semanticIdentity(columnValve);
  } else if (carouselStatus == CarouselContractStatus::VALID) {
    semantic = semanticIdentity(carousel);
  } else if (sfMixerStatus == SfMixerContractStatus::VALID) {
    semantic = semanticIdentity(sfMixer);
  } else {
    const bool supported =
        homeStatus != PumpHomeContractStatus::UNSUPPORTED_COMMAND ||
        fullAspirationStatus != PumpHomeContractStatus::UNSUPPORTED_COMMAND ||
        moveStatus != PumpMoveContractStatus::UNSUPPORTED_COMMAND ||
        valveHomeStatus != ValveHomeContractStatus::UNSUPPORTED_COMMAND ||
        valvePositionStatus !=
            ValveSetPositionContractStatus::UNSUPPORTED_COMMAND ||
        columnValveStatus != ColumnValveContractStatus::UNSUPPORTED_COMMAND ||
        carouselStatus != CarouselContractStatus::UNSUPPORTED_COMMAND ||
        sfMixerStatus != SfMixerContractStatus::UNSUPPORTED_COMMAND;
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

  if (sfMixerController_ != nullptr && sfMixerController_->running() &&
      semantic.command != CommandKind::SF_MIXER_SET_STATE) {
    reject(message, identity, cache, CommandErrorCode::CONTROLLER_BUSY, output,
           capacity, outputLength, &semantic);
    return {ParseStatus::VALID_MESSAGE, outputLength};
  }

  P1MotionController* selectedController = nullptr;
  ValveMotionController* selectedValveController = nullptr;
  ColumnBottomValveMotionController* selectedColumnValveController = nullptr;
  CarouselMotionController* selectedCarouselController = nullptr;
  SfMixerMotionController* selectedSfMixerController = nullptr;
  if (semantic.command == CommandKind::PUMP_HOME ||
      semantic.command == CommandKind::PUMP_ASPIRATE_FULL_STROKE ||
      semantic.command == CommandKind::PUMP_MOVE_ABSOLUTE_STEPS) {
    selectedController = controllerFor(semantic.pump);
    if (selectedController == nullptr) {
      reject(message, identity, cache, CommandErrorCode::INVALID_FIELD, output,
             capacity, outputLength, &semantic);
      return {ParseStatus::VALID_MESSAGE, outputLength};
    }
    if (semantic.command == CommandKind::PUMP_HOME)
      prepared = selectedController->prepareHome();
    else if (semantic.command == CommandKind::PUMP_ASPIRATE_FULL_STROKE)
      prepared = selectedController->prepareFullAspiration();
    else
      prepared = selectedController->prepareMoveAbsolute(semantic.targetSteps);
    if (prepared != P1PrepareResult::READY) {
      reject(message, identity, cache, preflightError(prepared), output,
             capacity, outputLength, &semantic);
      return {ParseStatus::VALID_MESSAGE, outputLength};
    }
  } else if (semantic.command == CommandKind::VALVE_HOME ||
             semantic.command == CommandKind::VALVE_SET_POSITION) {
    selectedValveController = controllerFor(semantic.valve);
    if (selectedValveController == nullptr) {
      reject(message, identity, cache, CommandErrorCode::INVALID_FIELD, output,
             capacity, outputLength, &semantic);
      return {ParseStatus::VALID_MESSAGE, outputLength};
    }
    const ValvePrepareResult valvePrepared =
        semantic.command == CommandKind::VALVE_HOME
            ? selectedValveController->prepareHome()
            : selectedValveController->prepareSetPosition(
                  semantic.targetDegrees);
    if (valvePrepared != ValvePrepareResult::READY) {
      reject(message, identity, cache, preflightError(valvePrepared), output,
             capacity, outputLength, &semantic);
      return {ParseStatus::VALID_MESSAGE, outputLength};
    }
  } else if (semantic.command == CommandKind::COLUMN_BOTTOM_VALVE_HOME ||
             semantic.command ==
                 CommandKind::COLUMN_BOTTOM_VALVE_SET_POSITION) {
    selectedColumnValveController = columnValveController_;
    if (selectedColumnValveController == nullptr) {
      reject(message, identity, cache, CommandErrorCode::INVALID_FIELD, output,
             capacity, outputLength, &semantic);
      return {ParseStatus::VALID_MESSAGE, outputLength};
    }
    const ColumnValvePrepareResult columnPrepared =
        semantic.command == CommandKind::COLUMN_BOTTOM_VALVE_HOME
            ? selectedColumnValveController->prepareHome()
            : selectedColumnValveController->prepareSetPosition(
                  semantic.targetDegrees);
    if (columnPrepared != ColumnValvePrepareResult::READY) {
      reject(message, identity, cache, preflightError(columnPrepared), output,
             capacity, outputLength, &semantic);
      return {ParseStatus::VALID_MESSAGE, outputLength};
    }
  } else if (semantic.command == CommandKind::CAROUSEL_SET_REFERENCE ||
             semantic.command == CommandKind::CAROUSEL_MOVE_TO_POSITION) {
    selectedCarouselController = carouselController_;
    if (selectedCarouselController == nullptr) {
      reject(message, identity, cache, CommandErrorCode::INVALID_FIELD, output,
             capacity, outputLength, &semantic);
      return {ParseStatus::VALID_MESSAGE, outputLength};
    }
    if (semantic.command == CommandKind::CAROUSEL_MOVE_TO_POSITION &&
        (columnValveController_ == nullptr ||
         columnValveController_->positionTrust() !=
             ColumnValvePositionTrust::TRUSTED ||
         columnValveController_->positionSteps() != kColumnValveClosedSteps)) {
      reject(message, identity, cache,
             CommandErrorCode::CAROUSEL_COLUMN_VALVE_NOT_CLOSED, output,
             capacity, outputLength, &semantic);
      return {ParseStatus::VALID_MESSAGE, outputLength};
    }
    const CarouselPrepareResult carouselPrepared =
        semantic.command == CommandKind::CAROUSEL_SET_REFERENCE
            ? selectedCarouselController->prepareSetReference(
                  semantic.carouselPosition)
            : selectedCarouselController->prepareMoveToPosition(
                  semantic.carouselPosition);
    if (carouselPrepared != CarouselPrepareResult::READY) {
      reject(message, identity, cache, preflightError(carouselPrepared), output,
             capacity, outputLength, &semantic);
      return {ParseStatus::VALID_MESSAGE, outputLength};
    }
  } else {
    selectedSfMixerController = sfMixerController_;
    if (selectedSfMixerController == nullptr) {
      reject(message, identity, cache, CommandErrorCode::INVALID_FIELD, output,
             capacity, outputLength, &semantic);
      return {ParseStatus::VALID_MESSAGE, outputLength};
    }
    const SfMixerPrepareResult mixerPrepared =
        selectedSfMixerController->prepareSetRunning(semantic.mixerRunning);
    if (mixerPrepared != SfMixerPrepareResult::READY) {
      reject(message, identity, cache, preflightError(mixerPrepared), output,
             capacity, outputLength, &semantic);
      return {ParseStatus::VALID_MESSAGE, outputLength};
    }
  }

  if (!accept(message, semantic, identity, cache, output, capacity,
              outputLength)) {
    if (selectedController != nullptr) selectedController->abort();
    if (selectedValveController != nullptr) selectedValveController->abort();
    if (selectedColumnValveController != nullptr)
      selectedColumnValveController->abort();
    if (selectedCarouselController != nullptr)
      selectedCarouselController->abort();
    if (selectedSfMixerController != nullptr)
      selectedSfMixerController->abort();
    outputLength = 0;
  } else {
    activeController_ = selectedController;
    activeValveController_ = selectedValveController;
    activeColumnValveController_ = selectedColumnValveController;
    activeCarouselController_ = selectedCarouselController;
    activeSfMixerController_ = selectedSfMixerController;
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
  suppressUnsolicitedLifecycle_ = false;
  runtimeState_ = RuntimeState::EMIT_STARTED;
  return true;
}

bool P1CommandRuntime::nextLifecycleFrame(
    const BootIdentityResult& identity, CommandStatusCache& cache,
    uint8_t* output, size_t capacity, size_t& outputLength,
    bool& startsMotion) {
  outputLength = 0;
  startsMotion = false;
  (void)cache;
  if (runtimeState_ == RuntimeState::EMIT_STARTED) {
    CommandStatusRecord started = activeRecord_;
    started.state = CommandState::STARTED;
    if (!writeCommandLifecycle(lifecycleNonce_, identity, started, output,
                               capacity, outputLength))
      return false;
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

bool P1CommandRuntime::confirmStartedFrameWritten(uint32_t nowUs,
                                                  CommandStatusCache& cache) {
  if (runtimeState_ != RuntimeState::WAIT_STARTED_WRITE) return false;
  CommandStatusRecord started = activeRecord_;
  started.state = CommandState::STARTED;
  if (!cache.store(started)) return false;
  activeRecord_ = started;
  const bool motionStarted = activeController_ != nullptr
                                 ? activeController_->start(nowUs)
                                 : activeValveController_ != nullptr
                                 ? activeValveController_->start(nowUs)
                                 : activeColumnValveController_ != nullptr
                                 ? activeColumnValveController_->start(nowUs)
                                 : activeCarouselController_ != nullptr
                                 ? activeCarouselController_->start(nowUs)
                                 : activeSfMixerController_ != nullptr &&
                                       activeSfMixerController_->start(nowUs);
  if (!motionStarted)
    return false;
  runtimeState_ = RuntimeState::RUNNING;
  return true;
}

bool P1CommandRuntime::startedFrameTransportFailed() {
  if (runtimeState_ != RuntimeState::WAIT_STARTED_WRITE) return false;
  runtimeState_ = RuntimeState::EMIT_STARTED;
  return true;
}

void P1CommandRuntime::update(uint32_t nowUs, CommandStatusCache& cache) {
  const SfMixerCommandResult mixerResult =
      sfMixerController_ != nullptr ? sfMixerController_->update(nowUs)
                                    : SfMixerCommandResult::NONE;
  if (runtimeState_ != RuntimeState::RUNNING) return;
  if (activeController_ != nullptr) {
    const P1MotionResult result = activeController_->update(nowUs);
    if (result != P1MotionResult::NONE) finish(result, cache);
  } else if (activeValveController_ != nullptr) {
    const ValveMotionResult result = activeValveController_->update(nowUs);
    if (result != ValveMotionResult::NONE) finishValve(result, cache);
  } else if (activeColumnValveController_ != nullptr) {
    const ColumnValveMotionResult result =
        activeColumnValveController_->update(nowUs);
    if (result != ColumnValveMotionResult::NONE)
      finishColumnValve(result, cache);
  } else if (activeCarouselController_ != nullptr) {
    const CarouselMotionResult result =
        activeCarouselController_->update(nowUs);
    if (result != CarouselMotionResult::NONE) finishCarousel(result, cache);
  } else if (activeSfMixerController_ != nullptr &&
             mixerResult != SfMixerCommandResult::NONE) {
    finishSfMixer(mixerResult, cache);
  }
}

void P1CommandRuntime::finishSfMixer(SfMixerCommandResult result,
                                     CommandStatusCache& cache) {
  if (result != SfMixerCommandResult::COMPLETED) return;
  activeRecord_.state = CommandState::COMPLETED;
  if (cache.store(activeRecord_)) {
    runtimeState_ = suppressUnsolicitedLifecycle_
                        ? RuntimeState::IDLE
                        : RuntimeState::EMIT_TERMINAL;
  }
  activeSfMixerController_ = nullptr;
}

void P1CommandRuntime::finishCarousel(CarouselMotionResult result,
                                      CommandStatusCache& cache) {
  if (result != CarouselMotionResult::COMPLETED) return;
  activeRecord_.state = CommandState::COMPLETED;
  if (cache.store(activeRecord_)) {
    runtimeState_ = suppressUnsolicitedLifecycle_
                        ? RuntimeState::IDLE
                        : RuntimeState::EMIT_TERMINAL;
  }
  activeCarouselController_ = nullptr;
}

void P1CommandRuntime::finishColumnValve(ColumnValveMotionResult result,
                                         CommandStatusCache& cache) {
  if (result == ColumnValveMotionResult::COMPLETED) {
    activeRecord_.state = CommandState::COMPLETED;
  } else {
    activeRecord_.state = CommandState::FAILED;
    activeRecord_.executionStarted = true;
    if (result == ColumnValveMotionResult::MOTION_TIMEOUT)
      activeRecord_.errorCode = CommandErrorCode::COLUMN_VALVE_MOTION_TIMEOUT;
    else if (result == ColumnValveMotionResult::HOME_SWITCH_STUCK)
      activeRecord_.errorCode =
          CommandErrorCode::COLUMN_VALVE_HOME_SWITCH_STUCK;
    else
      activeRecord_.errorCode =
          CommandErrorCode::COLUMN_VALVE_HOME_SWITCH_UNEXPECTED;
  }
  if (cache.store(activeRecord_)) {
    runtimeState_ = suppressUnsolicitedLifecycle_
                        ? RuntimeState::IDLE
                        : RuntimeState::EMIT_TERMINAL;
  }
  activeColumnValveController_ = nullptr;
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
  if (cache.store(activeRecord_)) {
    runtimeState_ = suppressUnsolicitedLifecycle_
                        ? RuntimeState::IDLE
                        : RuntimeState::EMIT_TERMINAL;
  }
  activeController_ = nullptr;
}

void P1CommandRuntime::finishValve(ValveMotionResult result,
                                   CommandStatusCache& cache) {
  if (result == ValveMotionResult::COMPLETED) {
    activeRecord_.state = CommandState::COMPLETED;
  } else {
    activeRecord_.state = CommandState::FAILED;
    activeRecord_.executionStarted = true;
    if (result == ValveMotionResult::MOTION_TIMEOUT)
      activeRecord_.errorCode = CommandErrorCode::VALVE_MOTION_TIMEOUT;
    else if (result == ValveMotionResult::HOME_SWITCH_STUCK)
      activeRecord_.errorCode = CommandErrorCode::VALVE_HOME_SWITCH_STUCK;
    else
      activeRecord_.errorCode =
          CommandErrorCode::VALVE_HOME_SWITCH_UNEXPECTED;
  }
  if (cache.store(activeRecord_)) {
    runtimeState_ = suppressUnsolicitedLifecycle_
                        ? RuntimeState::IDLE
                        : RuntimeState::EMIT_TERMINAL;
  }
  activeValveController_ = nullptr;
}

bool P1CommandRuntime::abort(CommandStatusCache& cache) {
  if (runtimeState_ != RuntimeState::RUNNING)
    return false;
  const bool aborted = activeController_ != nullptr
                           ? activeController_->abort()
                           : activeValveController_ != nullptr
                           ? activeValveController_->abort()
                           : activeColumnValveController_ != nullptr
                           ? activeColumnValveController_->abort()
                           : activeCarouselController_ != nullptr
                           ? activeCarouselController_->abort()
                           : activeSfMixerController_ != nullptr &&
                                 activeSfMixerController_->abort();
  if (!aborted) return false;
  activeRecord_.state = CommandState::FAILED;
  activeRecord_.executionStarted = true;
  activeRecord_.errorCode = CommandErrorCode::COMMAND_ABORTED;
  if (!cache.store(activeRecord_)) return false;
  runtimeState_ = suppressUnsolicitedLifecycle_
                      ? RuntimeState::IDLE
                      : RuntimeState::EMIT_TERMINAL;
  activeController_ = nullptr;
  activeValveController_ = nullptr;
  activeColumnValveController_ = nullptr;
  activeCarouselController_ = nullptr;
  activeSfMixerController_ = nullptr;
  return true;
}

ValveMotionController* P1CommandRuntime::controllerFor(ValveId valve) {
  if (valve < ValveId::V1 || valve > ValveId::V8 ||
      valveControllers_ == nullptr)
    return nullptr;
  const uint8_t index = static_cast<uint8_t>(valve) -
                        static_cast<uint8_t>(ValveId::V1);
  return index < valveControllerCount_ ? valveControllers_[index] : nullptr;
}

P1MotionController* P1CommandRuntime::controllerFor(PumpId pump) {
  if (pump == PumpId::P1) return &p1Controller_;
  if (pump == PumpId::P2) return p2Controller_;
  return nullptr;
}

void P1CommandRuntime::handleSessionReplacement(const char* newNonce) {
  if (carouselController_ != nullptr)
    carouselController_->invalidatePositionTrust();
  if (runtimeState_ == RuntimeState::IDLE ||
      strcmp(lifecycleNonce_, newNonce) == 0)
    return;
  if (runtimeState_ == RuntimeState::EMIT_STARTED ||
      runtimeState_ == RuntimeState::WAIT_STARTED_WRITE) {
    strcpy(lifecycleNonce_, newNonce);
    suppressUnsolicitedLifecycle_ = false;
    return;
  }
  suppressUnsolicitedLifecycle_ = true;
  if (runtimeState_ == RuntimeState::EMIT_TERMINAL)
    runtimeState_ = RuntimeState::IDLE;
}

bool P1CommandRuntime::hasPendingLifecycleFrame() const {
  return runtimeState_ == RuntimeState::EMIT_STARTED ||
         runtimeState_ == RuntimeState::EMIT_TERMINAL;
}

}  // namespace labforge
