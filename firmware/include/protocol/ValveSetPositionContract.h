#pragma once

#include "protocol/CommandStatusCache.h"
#include "protocol/ProtocolTypes.h"

namespace labforge {

enum class ValveSetPositionContractStatus : uint8_t {
  VALID,
  UNSUPPORTED_COMMAND,
  INVALID_ARGUMENTS,
};

struct ValveSetPositionCommand {
  ValveId valve;
  uint16_t targetDegrees;
};

ValveSetPositionContractStatus parseValveSetPosition(
    const InboundMessage& message, ValveSetPositionCommand& command);
CommandSemanticIdentity semanticIdentity(
    const ValveSetPositionCommand& command);

}  // namespace labforge
