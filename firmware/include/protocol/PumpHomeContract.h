#pragma once

#include <stdint.h>

#include "protocol/CommandStatusCache.h"
#include "protocol/ProtocolTypes.h"

namespace labforge {

enum class PumpHomeContractStatus : uint8_t {
  VALID,
  UNSUPPORTED_COMMAND,
  INVALID_ARGUMENTS,
};

struct PumpHomeCommand {
  PumpId pump;
};

PumpHomeContractStatus parsePumpHome(const InboundMessage& message,
                                     PumpHomeCommand& command);
CommandSemanticIdentity semanticIdentity(const PumpHomeCommand& command);

}  // namespace labforge
