#include "protocol/SessionState.h"

#include <string.h>

namespace labforge {

void SessionState::establish(const char* nonce) {
  memcpy(nonce_, nonce, kUuidTextCapacity);
  active_ = true;
}

SessionValidationResult SessionState::validate(const char* nonce, BootIdPresence bootIdPresence,
                                               uint32_t bootId,
                                               const BootIdentityResult& identity) const {
  if (!active_) return SessionValidationResult::HANDSHAKE_REQUIRED;
  if (strcmp(nonce_, nonce) != 0) return SessionValidationResult::STALE_SESSION;
  if (identity.trusted) {
    if (bootIdPresence != BootIdPresence::VALUE || bootId != identity.controllerBootId) {
      return SessionValidationResult::CONTROLLER_BOOT_MISMATCH;
    }
    return SessionValidationResult::VALID;
  }
  return bootIdPresence == BootIdPresence::NULL_VALUE
             ? SessionValidationResult::VALID
             : SessionValidationResult::CONTROLLER_IDENTITY_UNTRUSTED;
}

}  // namespace labforge
