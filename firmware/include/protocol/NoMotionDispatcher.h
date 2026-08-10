#pragma once

#include <stddef.h>
#include <stdint.h>

#include "identity/BootIdentityStore.h"
#include "protocol/CommandStatusCache.h"
#include "protocol/MessageParser.h"
#include "protocol/ProtocolTypes.h"
#include "protocol/SessionState.h"

namespace labforge {

struct DispatchResult {
  ParseStatus parseStatus;
  size_t outputLength;
};

class NoMotionDispatcher {
 public:
  explicit NoMotionDispatcher(bool p1MotionEnabled = false)
      : p1MotionEnabled_(p1MotionEnabled) {}
  DispatchResult dispatch(const uint8_t* payload, size_t length,
                          const BootIdentityResult& identity,
                          SessionState& session,
                          const CommandStatusCache& commandStatusCache,
                          uint8_t* output,
                          size_t capacity) const;
  DispatchResult lineTooLong(const BootIdentityResult& identity,
                             uint8_t* output, size_t capacity) const;

 private:
  MessageParser parser_;
  bool p1MotionEnabled_;
};

}  // namespace labforge
