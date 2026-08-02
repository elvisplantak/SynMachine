#include "protocol/StatusWriter.h"

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

bool writeStatus(const char* nonce, const char* requestId,
                 const BootIdentityResult& identity, uint8_t* output,
                 size_t capacity, size_t& outputLength) {
  char frame[kStatusFrameCapacity];
  const int written = identity.trusted
      ? LABFORGE_SNPRINTF(
            frame, sizeof(frame),
            LABFORGE_FORMAT(
                "{\"protocol\":\"LABFORGE/1\",\"type\":\"STATUS\","
                "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":%lu,"
                "\"request_id\":\"%s\",\"controller_state\":\"PROTOCOL_ONLY\","
                "\"software_state_trust\":\"TRUSTED\","
                "\"active_operation_command_id\":null}\n"),
            nonce, static_cast<unsigned long>(identity.controllerBootId), requestId)
      : LABFORGE_SNPRINTF(
            frame, sizeof(frame),
            LABFORGE_FORMAT(
                "{\"protocol\":\"LABFORGE/1\",\"type\":\"STATUS\","
                "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":null,"
                "\"request_id\":\"%s\","
                "\"controller_state\":\"IDENTITY_UNTRUSTED\","
                "\"software_state_trust\":\"UNTRUSTED\","
                "\"active_operation_command_id\":null}\n"),
            nonce, requestId);
  outputLength = 0;
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
