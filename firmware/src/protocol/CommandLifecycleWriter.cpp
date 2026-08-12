#include "protocol/CommandLifecycleWriter.h"

#include <stdio.h>
#include <string.h>

#if defined(__AVR__)
#include <avr/pgmspace.h>
#define LABFORGE_SNPRINTF snprintf_P
#define LABFORGE_FORMAT(format) PSTR(format)
#else
#define LABFORGE_SNPRINTF snprintf
#define LABFORGE_FORMAT(format) format
#endif

namespace labforge {
namespace {

const char* stateText(CommandState state) {
  if (state == CommandState::REJECTED) return "REJECTED";
  if (state == CommandState::ACCEPTED) return "ACCEPTED";
  if (state == CommandState::STARTED) return "STARTED";
  if (state == CommandState::COMPLETED) return "COMPLETED";
  if (state == CommandState::FAILED) return "FAILED";
  return nullptr;
}

const char* errorText(CommandErrorCode error) {
  if (error == CommandErrorCode::INVALID_FIELD) return "INVALID_FIELD";
  if (error == CommandErrorCode::UNSUPPORTED_COMMAND)
    return "UNSUPPORTED_COMMAND";
  if (error == CommandErrorCode::COMMAND_ID_CONFLICT)
    return "COMMAND_ID_CONFLICT";
  if (error == CommandErrorCode::CONTROLLER_BUSY) return "CONTROLLER_BUSY";
  if (error == CommandErrorCode::CONTROLLER_IDENTITY_UNTRUSTED)
    return "CONTROLLER_IDENTITY_UNTRUSTED";
  if (error == CommandErrorCode::PUMP_MOTION_TIMEOUT)
    return "PUMP_MOTION_TIMEOUT";
  if (error == CommandErrorCode::PUMP_HOME_SWITCH_UNEXPECTED)
    return "PUMP_HOME_SWITCH_UNEXPECTED";
  if (error == CommandErrorCode::PUMP_HOME_SWITCH_STUCK)
    return "PUMP_HOME_SWITCH_STUCK";
  if (error == CommandErrorCode::VALVE_MOTION_TIMEOUT)
    return "VALVE_MOTION_TIMEOUT";
  if (error == CommandErrorCode::VALVE_HOME_SWITCH_UNEXPECTED)
    return "VALVE_HOME_SWITCH_UNEXPECTED";
  if (error == CommandErrorCode::VALVE_HOME_SWITCH_STUCK)
    return "VALVE_HOME_SWITCH_STUCK";
  if (error == CommandErrorCode::COLUMN_VALVE_MOTION_TIMEOUT)
    return "COLUMN_VALVE_MOTION_TIMEOUT";
  if (error == CommandErrorCode::COLUMN_VALVE_HOME_SWITCH_UNEXPECTED)
    return "COLUMN_VALVE_HOME_SWITCH_UNEXPECTED";
  if (error == CommandErrorCode::COLUMN_VALVE_HOME_SWITCH_STUCK)
    return "COLUMN_VALVE_HOME_SWITCH_STUCK";
  if (error == CommandErrorCode::COMMAND_ABORTED) return "COMMAND_ABORTED";
  return nullptr;
}

}  // namespace

bool writeCommandLifecycle(const char* nonce,
                           const BootIdentityResult& identity,
                           const CommandStatusRecord& record, uint8_t* output,
                           size_t capacity, size_t& outputLength) {
  outputLength = 0;
  const char* state = stateText(record.state);
  if (!identity.trusted || state == nullptr || !record.phaseExecutionIdKnown)
    return false;

  char suffix[96] = "";
  if (record.state == CommandState::COMPLETED) {
    strcpy(suffix, ",\"result\":{}");
  } else if (record.state == CommandState::REJECTED ||
             record.state == CommandState::FAILED) {
    const char* error = errorText(record.errorCode);
    if (error == nullptr) return false;
    const int suffixLength = record.state == CommandState::FAILED
        ? snprintf(suffix, sizeof(suffix),
                   ",\"error_code\":\"%s\",\"execution_started\":%s", error,
                   record.executionStarted ? "true" : "false")
        : snprintf(suffix, sizeof(suffix), ",\"error_code\":\"%s\"", error);
    if (suffixLength < 0 || static_cast<size_t>(suffixLength) >= sizeof(suffix))
      return false;
  }

  char frame[kCommandLifecycleFrameCapacity];
  const int written = LABFORGE_SNPRINTF(
      frame, sizeof(frame),
      LABFORGE_FORMAT(
          "{\"protocol\":\"LABFORGE/1\",\"type\":\"%s\","
          "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":%lu,"
          "\"phase_execution_id\":\"%s\",\"operation_command_id\":\"%s\"%s}\n"),
      state, nonce, static_cast<unsigned long>(identity.controllerBootId),
      record.phaseExecutionId, record.operationCommandId, suffix);
  if (written < 0 || static_cast<size_t>(written) >= sizeof(frame) ||
      static_cast<size_t>(written) > capacity)
    return false;
  memcpy(output, frame, static_cast<size_t>(written));
  outputLength = static_cast<size_t>(written);
  return true;
}

}  // namespace labforge

#undef LABFORGE_FORMAT
#undef LABFORGE_SNPRINTF
