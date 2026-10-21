#pragma once

#include <stddef.h>
#include <stdint.h>

#include "identity/BootIdentityStore.h"
#include "actuator/ColumnBottomValveMotionController.h"
#include "actuator/P1MotionController.h"
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
  explicit NoMotionDispatcher(
      bool p1MotionEnabled = false,
      ColumnBottomValveMotionController* columnValveController = nullptr,
      P1MotionController* p1Controller = nullptr,
      P1MotionController* p2Controller = nullptr)
      : p1MotionEnabled_(p1MotionEnabled),
        columnValveController_(columnValveController),
        p1Controller_(p1Controller), p2Controller_(p2Controller) {}
  DispatchResult dispatch(const uint8_t* payload, size_t length,
                          const BootIdentityResult& identity,
                          SessionState& session,
                          const CommandStatusCache& commandStatusCache,
                          uint8_t* output,
                          size_t capacity) const;
  DispatchResult dispatchParsed(
      const ParseResult& parsed, const uint8_t* payload, size_t length,
      const BootIdentityResult& identity, SessionState& session,
      const CommandStatusCache& commandStatusCache, uint8_t* output,
      size_t capacity) const;
  DispatchResult lineTooLong(const BootIdentityResult& identity,
                             uint8_t* output, size_t capacity) const;

 private:
  MessageParser parser_;
  bool p1MotionEnabled_;
  ColumnBottomValveMotionController* columnValveController_;
  P1MotionController* p1Controller_;
  P1MotionController* p2Controller_;
};

}  // namespace labforge
