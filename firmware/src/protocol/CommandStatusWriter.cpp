#include "protocol/CommandStatusWriter.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#if defined(__AVR__)
#include <avr/pgmspace.h>
#define LABFORGE_FORMAT(format) PSTR(format)
#define LABFORGE_TEXT(text) PSTR(text)
#define LABFORGE_TEXT_SPECIFIER "%S"
#define LABFORGE_VSNPRINTF vsnprintf_P
#else
#define LABFORGE_FORMAT(format) format
#define LABFORGE_TEXT(text) text
#define LABFORGE_TEXT_SPECIFIER "%s"
#define LABFORGE_VSNPRINTF vsnprintf
#endif

namespace labforge {
namespace {

bool append(char* frame, size_t capacity, size_t& length,
            const char* format, ...) {
  va_list arguments;
  va_start(arguments, format);
  const int written = LABFORGE_VSNPRINTF(
      frame + length, capacity - length, format, arguments);
  va_end(arguments);
  if (written < 0 || static_cast<size_t>(written) >= capacity - length) {
    return false;
  }
  length += static_cast<size_t>(written);
  return true;
}

const char* stateText(const CommandStatusEntry* entry) {
  if (entry == nullptr) return LABFORGE_TEXT("UNKNOWN");
  if (entry->record.state == CommandState::REJECTED)
    return LABFORGE_TEXT("REJECTED");
  if (entry->record.state == CommandState::ACCEPTED)
    return LABFORGE_TEXT("ACCEPTED");
  if (entry->record.state == CommandState::STARTED)
    return LABFORGE_TEXT("STARTED");
  if (entry->record.state == CommandState::COMPLETED)
    return LABFORGE_TEXT("COMPLETED");
  if (entry->record.state == CommandState::FAILED)
    return LABFORGE_TEXT("FAILED");
  return nullptr;
}

const char* errorText(CommandErrorCode error) {
  if (error == CommandErrorCode::UNSUPPORTED_COMMAND)
    return LABFORGE_TEXT("UNSUPPORTED_COMMAND");
  if (error == CommandErrorCode::COMMAND_ID_CONFLICT)
    return LABFORGE_TEXT("COMMAND_ID_CONFLICT");
  if (error == CommandErrorCode::CONTROLLER_BUSY)
    return LABFORGE_TEXT("CONTROLLER_BUSY");
  if (error == CommandErrorCode::CONTROLLER_IDENTITY_UNTRUSTED)
    return LABFORGE_TEXT("CONTROLLER_IDENTITY_UNTRUSTED");
  return nullptr;
}

}  // namespace

bool writeCommandStatus(const char* nonce, const char* requestId,
                        const char* operationCommandId,
                        const BootIdentityResult& identity,
                        const CommandStatusEntry* entry, uint8_t* output,
                        size_t capacity, size_t& outputLength) {
  char frame[kCommandStatusFrameCapacity];
  size_t length = 0;
  outputLength = 0;
  const char* state = stateText(entry);
  if (state == nullptr ||
      (entry != nullptr &&
       strcmp(entry->record.operationCommandId, operationCommandId) != 0)) {
    return false;
  }

  const bool headerWritten = identity.trusted
      ? append(frame, sizeof(frame), length,
               LABFORGE_FORMAT(
                   "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND_STATUS\","
                   "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":%lu,"
                   "\"request_id\":\"%s\","),
               nonce, static_cast<unsigned long>(identity.controllerBootId),
               requestId)
      : append(frame, sizeof(frame), length,
               LABFORGE_FORMAT(
                   "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND_STATUS\","
                   "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":null,"
                   "\"request_id\":\"%s\","),
               nonce, requestId);
  if (!headerWritten) return false;

  if (entry != nullptr && entry->record.phaseExecutionIdKnown &&
      !append(frame, sizeof(frame), length,
              LABFORGE_FORMAT("\"phase_execution_id\":\"%s\","),
              entry->record.phaseExecutionId)) {
    return false;
  }
  if (!append(frame, sizeof(frame), length,
              LABFORGE_FORMAT(
                  "\"operation_command_id\":\"%s\",\"command_state\":\""
                  LABFORGE_TEXT_SPECIFIER "\""),
              operationCommandId, state)) {
    return false;
  }

  if (entry != nullptr &&
      (entry->record.state == CommandState::REJECTED ||
       entry->record.state == CommandState::FAILED)) {
    const char* error = errorText(entry->record.errorCode);
    if (error == nullptr ||
        !append(frame, sizeof(frame), length,
                LABFORGE_FORMAT(",\"error_code\":\""
                                LABFORGE_TEXT_SPECIFIER "\""),
                error)) {
      return false;
    }
  }
  if (entry != nullptr && entry->record.state == CommandState::COMPLETED &&
      !append(frame, sizeof(frame), length,
              LABFORGE_FORMAT(",\"result\":{}"))) {
    return false;
  }
  if (entry != nullptr && entry->record.state == CommandState::FAILED &&
      !append(frame, sizeof(frame), length,
              entry->record.executionStarted
                  ? LABFORGE_FORMAT(",\"execution_started\":true")
                  : LABFORGE_FORMAT(",\"execution_started\":false"))) {
    return false;
  }
  if (!append(frame, sizeof(frame), length, LABFORGE_FORMAT("}\n")) ||
      length > capacity) {
    return false;
  }
  memcpy(output, frame, length);
  outputLength = length;
  return true;
}

}  // namespace labforge

#undef LABFORGE_FORMAT
#undef LABFORGE_TEXT
#undef LABFORGE_TEXT_SPECIFIER
#undef LABFORGE_VSNPRINTF
