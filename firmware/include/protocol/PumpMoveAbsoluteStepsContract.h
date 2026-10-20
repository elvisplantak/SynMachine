#pragma once

#include <stdint.h>

#include "protocol/CommandStatusCache.h"
#include "protocol/ProtocolTypes.h"

namespace labforge {

enum class PumpMoveContractStatus : uint8_t {
  VALID,
  UNSUPPORTED_COMMAND,
  INVALID_ARGUMENTS,
};

struct PumpMoveAbsoluteStepsCommand {
  PumpId pump;
  uint16_t targetSteps;
};

PumpMoveContractStatus parsePumpMoveAbsoluteSteps(
    const InboundMessage& message, PumpMoveAbsoluteStepsCommand& command);
CommandSemanticIdentity semanticIdentity(
    const PumpMoveAbsoluteStepsCommand& command);

}  // namespace labforge
