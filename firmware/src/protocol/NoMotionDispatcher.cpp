#include "protocol/NoMotionDispatcher.h"

#include <string.h>

#include "protocol/CommandStatusWriter.h"
#include "protocol/HelloOkWriter.h"
#include "protocol/ProtocolErrorWriter.h"
#include "protocol/StatusWriter.h"

namespace labforge {
namespace {

ProtocolErrorCode sessionError(SessionValidationResult validation) {
  if (validation == SessionValidationResult::HANDSHAKE_REQUIRED)
    return ProtocolErrorCode::HANDSHAKE_REQUIRED;
  if (validation == SessionValidationResult::STALE_SESSION)
    return ProtocolErrorCode::STALE_SESSION;
  if (validation == SessionValidationResult::CONTROLLER_BOOT_MISMATCH)
    return ProtocolErrorCode::CONTROLLER_BOOT_MISMATCH;
  if (validation == SessionValidationResult::CONTROLLER_IDENTITY_UNTRUSTED)
    return ProtocolErrorCode::CONTROLLER_IDENTITY_UNTRUSTED;
  if (validation == SessionValidationResult::VALID)
    return ProtocolErrorCode::NONE;
  return ProtocolErrorCode::INVALID_FIELD;
}

const char* columnStateName(ColumnValveMotionState state) {
  switch (state) {
    case ColumnValveMotionState::IDLE:
      return "IDLE";
    case ColumnValveMotionState::PREPARED_HOME:
      return "PREPARED_HOME";
    case ColumnValveMotionState::PREPARED_MOVE:
      return "PREPARED_MOVE";
    case ColumnValveMotionState::CONFIRMING_HOME:
      return "CONFIRMING_HOME";
    case ColumnValveMotionState::CONFIRMING_TRUSTED_HOME:
      return "CONFIRMING_TRUSTED_HOME";
    case ColumnValveMotionState::CONFIRMING_HOME_RELEASE:
      return "CONFIRMING_HOME_RELEASE";
    case ColumnValveMotionState::SEARCHING_HOME:
      return "SEARCHING_HOME";
    case ColumnValveMotionState::MOVING:
      return "MOVING";
    case ColumnValveMotionState::CONFIRMING_UNEXPECTED_HOME:
      return "CONFIRMING_UNEXPECTED_HOME";
  }
  return "UNKNOWN";
}

ErrorCorrelation queryCorrelation(const InboundMessage& message) {
  ErrorCorrelation correlation{};
  correlation.kind = ErrorCorrelationKind::QUERY;
  memcpy(correlation.backendSessionNonce, message.backendSessionNonce,
         sizeof(correlation.backendSessionNonce));
  memcpy(correlation.requestId, message.requestId,
         sizeof(correlation.requestId));
  return correlation;
}

}  // namespace

DispatchResult NoMotionDispatcher::dispatch(
    const uint8_t* payload, size_t length, const BootIdentityResult& identity,
    SessionState& session, const CommandStatusCache& commandStatusCache,
    uint8_t* output, size_t capacity) const {
  const ParseResult parsed = parser_.parse(payload, length);
  return dispatchParsed(parsed, payload, length, identity, session,
                        commandStatusCache, output, capacity);
}

DispatchResult NoMotionDispatcher::dispatchParsed(
    const ParseResult& parsed, const uint8_t* payload, size_t length,
    const BootIdentityResult& identity, SessionState& session,
    const CommandStatusCache& commandStatusCache, uint8_t* output,
    size_t capacity) const {
  size_t outputLength = 0;
  if (parsed.status != ParseStatus::VALID_MESSAGE) {
    const ErrorCorrelation correlation =
        parser_.recoverErrorCorrelation(payload, length);
    writeProtocolError(parsed.error, correlation, identity, output, capacity,
                       outputLength);
    return {parsed.status, outputLength};
  }

  if (parsed.message.type == MessageType::HELLO) {
    if (writeHelloOk(parsed.message.backendSessionNonce, identity, output,
                     capacity, outputLength, p1MotionEnabled_,
                     &commandStatusCache)) {
      session.establish(parsed.message.backendSessionNonce);
    }
    return {parsed.status, outputLength};
  }

  if (parsed.message.type != MessageType::QUERY_STATUS &&
      parsed.message.type != MessageType::QUERY_COMMAND) {
    return {parsed.status, 0};
  }

  const SessionValidationResult validation = session.validate(
      parsed.message.backendSessionNonce,
      parsed.message.controllerBootIdPresence,
      parsed.message.controllerBootId, identity);
  if (validation != SessionValidationResult::VALID) {
    const ErrorCorrelation correlation = queryCorrelation(parsed.message);
    writeProtocolError(sessionError(validation), correlation, identity, output,
                       capacity, outputLength);
    return {parsed.status, outputLength};
  }

  if (parsed.message.type == MessageType::QUERY_STATUS) {
    ColumnValveStatusDiagnostics columnDiagnostics{};
    const ColumnValveStatusDiagnostics* diagnostics = nullptr;
    if (columnValveController_ != nullptr) {
      columnDiagnostics = {
          columnStateName(columnValveController_->state()),
          columnValveController_->stageSteps(),
          columnValveController_->homeActive(),
      };
      diagnostics = &columnDiagnostics;
    }
    writeStatus(parsed.message.backendSessionNonce, parsed.message.requestId,
                identity, output, capacity, outputLength,
                &commandStatusCache, p1MotionEnabled_, diagnostics);
  } else {
    writeCommandStatus(
        parsed.message.backendSessionNonce, parsed.message.requestId,
        parsed.message.operationCommandId, identity,
        commandStatusCache.find(parsed.message.operationCommandId), output,
        capacity, outputLength);
  }
  return {parsed.status, outputLength};
}

DispatchResult NoMotionDispatcher::lineTooLong(
    const BootIdentityResult& identity, uint8_t* output,
    size_t capacity) const {
  ErrorCorrelation correlation{};
  correlation.kind = ErrorCorrelationKind::NONE;
  size_t outputLength = 0;
  writeProtocolError(ProtocolErrorCode::LINE_TOO_LONG, correlation, identity,
                     output, capacity, outputLength);
  return {ParseStatus::OVERSIZED_FRAME, outputLength};
}

}  // namespace labforge
