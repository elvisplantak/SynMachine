#include "protocol/HelloOkWriter.h"

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

bool writeHelloOk(const char* nonce, const BootIdentityResult& identity,
                  uint8_t* output, size_t capacity, size_t& outputLength,
                  bool p1MotionEnabled) {
  char frame[kHelloOkFrameCapacity];
  const int written = identity.trusted && p1MotionEnabled
      ? LABFORGE_SNPRINTF(
            frame, sizeof(frame),
            LABFORGE_FORMAT(
                "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO_OK\","
                "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":%lu,"
                "\"controller_state\":\"IDLE\","
                "\"software_state_trust\":\"TRUSTED\","
                "\"capabilities\":[\"PUMP_HOME\","
                "\"PUMP_MOVE_ABSOLUTE_STEPS\"]}\n"),
            nonce, static_cast<unsigned long>(identity.controllerBootId))
      : identity.trusted
      ? LABFORGE_SNPRINTF(
            frame, sizeof(frame),
            LABFORGE_FORMAT(
                "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO_OK\","
                "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":%lu,"
                "\"controller_state\":\"PROTOCOL_ONLY\","
                "\"software_state_trust\":\"TRUSTED\",\"capabilities\":[]}\n"),
            nonce, static_cast<unsigned long>(identity.controllerBootId))
      : LABFORGE_SNPRINTF(
            frame, sizeof(frame),
            LABFORGE_FORMAT(
                "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO_OK\","
                "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":null,"
                "\"controller_state\":\"IDENTITY_UNTRUSTED\","
                "\"software_state_trust\":\"UNTRUSTED\",\"capabilities\":[]}\n"),
            nonce);
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
