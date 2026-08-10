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
                     capacity, outputLength, p1MotionEnabled_)) {
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
    writeStatus(parsed.message.backendSessionNonce, parsed.message.requestId,
                identity, output, capacity, outputLength,
                &commandStatusCache, p1MotionEnabled_);
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
