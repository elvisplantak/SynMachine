#pragma once

#include "identity/BootIdentityStore.h"
#include "protocol/ProtocolTypes.h"

namespace labforge {

enum class SessionValidationResult : uint8_t {
  VALID,
  HANDSHAKE_REQUIRED,
  STALE_SESSION,
  CONTROLLER_BOOT_MISMATCH,
  CONTROLLER_IDENTITY_UNTRUSTED,
};

class SessionState {
 public:
  bool active() const { return active_; }
  const char* nonce() const { return nonce_; }
  void establish(const char* nonce);
  SessionValidationResult validate(const char* nonce, BootIdPresence bootIdPresence,
                                   uint32_t bootId, const BootIdentityResult& identity) const;

 private:
  bool active_ = false;
  char nonce_[kUuidTextCapacity]{};
};

}  // namespace labforge
