#include "protocol/ProtocolErrorWriter.h"

#include <stdio.h>
#include <string.h>

#if defined(__AVR__)
#include <avr/pgmspace.h>
#define LABFORGE_SNPRINTF snprintf_P
#define LABFORGE_FORMAT(format) PSTR(format)
#define LABFORGE_ERROR_TEXT(text) PSTR(text)
#define LABFORGE_ERROR_SPECIFIER "%S"
#else
#define LABFORGE_SNPRINTF snprintf
#define LABFORGE_FORMAT(format) format
#define LABFORGE_ERROR_TEXT(text) text
#define LABFORGE_ERROR_SPECIFIER "%s"
#endif

namespace labforge {
namespace {

const char* errorText(ProtocolErrorCode error) {
  if (error == ProtocolErrorCode::MALFORMED_MESSAGE)
    return LABFORGE_ERROR_TEXT("MALFORMED_MESSAGE");
  if (error == ProtocolErrorCode::LINE_TOO_LONG)
    return LABFORGE_ERROR_TEXT("LINE_TOO_LONG");
  if (error == ProtocolErrorCode::UNSUPPORTED_PROTOCOL_VERSION)
    return LABFORGE_ERROR_TEXT("UNSUPPORTED_PROTOCOL_VERSION");
  if (error == ProtocolErrorCode::HANDSHAKE_REQUIRED)
    return LABFORGE_ERROR_TEXT("HANDSHAKE_REQUIRED");
  if (error == ProtocolErrorCode::STALE_SESSION)
    return LABFORGE_ERROR_TEXT("STALE_SESSION");
  if (error == ProtocolErrorCode::CONTROLLER_BOOT_MISMATCH)
    return LABFORGE_ERROR_TEXT("CONTROLLER_BOOT_MISMATCH");
  if (error == ProtocolErrorCode::CONTROLLER_IDENTITY_UNTRUSTED)
    return LABFORGE_ERROR_TEXT("CONTROLLER_IDENTITY_UNTRUSTED");
  if (error == ProtocolErrorCode::MISSING_FIELD)
    return LABFORGE_ERROR_TEXT("MISSING_FIELD");
  if (error == ProtocolErrorCode::INVALID_FIELD)
    return LABFORGE_ERROR_TEXT("INVALID_FIELD");
  if (error == ProtocolErrorCode::UNSUPPORTED_MESSAGE_TYPE)
    return LABFORGE_ERROR_TEXT("UNSUPPORTED_MESSAGE_TYPE");
  return nullptr;
}

}  // namespace

bool writeProtocolError(ProtocolErrorCode error,
                        const ErrorCorrelation& correlation,
                        const BootIdentityResult& identity, uint8_t* output,
                        size_t capacity, size_t& outputLength) {
  char frame[kProtocolErrorFrameCapacity];
  const char* code = errorText(error);
  outputLength = 0;
  if (code == nullptr) return false;

  int written = -1;
  if (correlation.kind == ErrorCorrelationKind::NONE) {
    written = LABFORGE_SNPRINTF(
        frame, sizeof(frame),
        LABFORGE_FORMAT(
            "{\"protocol\":\"LABFORGE/1\",\"type\":\"PROTOCOL_ERROR\","
            "\"error_code\":\"" LABFORGE_ERROR_SPECIFIER "\"}\n"),
        code);
  } else if (correlation.kind == ErrorCorrelationKind::QUERY) {
    written = identity.trusted
        ? LABFORGE_SNPRINTF(
              frame, sizeof(frame),
              LABFORGE_FORMAT(
                  "{\"protocol\":\"LABFORGE/1\",\"type\":\"PROTOCOL_ERROR\","
                  "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":%lu,"
                  "\"request_id\":\"%s\",\"error_code\":\""
                  LABFORGE_ERROR_SPECIFIER "\"}\n"),
              correlation.backendSessionNonce,
              static_cast<unsigned long>(identity.controllerBootId),
              correlation.requestId, code)
        : LABFORGE_SNPRINTF(
              frame, sizeof(frame),
              LABFORGE_FORMAT(
                  "{\"protocol\":\"LABFORGE/1\",\"type\":\"PROTOCOL_ERROR\","
                  "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":null,"
                  "\"request_id\":\"%s\",\"error_code\":\""
                  LABFORGE_ERROR_SPECIFIER "\"}\n"),
              correlation.backendSessionNonce, correlation.requestId, code);
  } else {
    written = identity.trusted
        ? LABFORGE_SNPRINTF(
              frame, sizeof(frame),
              LABFORGE_FORMAT(
                  "{\"protocol\":\"LABFORGE/1\",\"type\":\"PROTOCOL_ERROR\","
                  "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":%lu,"
                  "\"phase_execution_id\":\"%s\",\"operation_command_id\":\"%s\","
                  "\"error_code\":\"" LABFORGE_ERROR_SPECIFIER "\"}\n"),
              correlation.backendSessionNonce,
              static_cast<unsigned long>(identity.controllerBootId),
              correlation.phaseExecutionId, correlation.operationCommandId, code)
        : LABFORGE_SNPRINTF(
              frame, sizeof(frame),
              LABFORGE_FORMAT(
                  "{\"protocol\":\"LABFORGE/1\",\"type\":\"PROTOCOL_ERROR\","
                  "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":null,"
                  "\"phase_execution_id\":\"%s\",\"operation_command_id\":\"%s\","
                  "\"error_code\":\"" LABFORGE_ERROR_SPECIFIER "\"}\n"),
              correlation.backendSessionNonce, correlation.phaseExecutionId,
              correlation.operationCommandId, code);
  }

  if (written < 0 || static_cast<size_t>(written) >= sizeof(frame) ||
      static_cast<size_t>(written) > capacity) {
    return false;
  }
  memcpy(output, frame, static_cast<size_t>(written));
  outputLength = static_cast<size_t>(written);
  return true;
}

}  // namespace labforge

#undef LABFORGE_FORMAT
#undef LABFORGE_SNPRINTF
#undef LABFORGE_ERROR_SPECIFIER
#undef LABFORGE_ERROR_TEXT
