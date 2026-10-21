#pragma once

#include "protocol/PumpHomeContract.h"

namespace labforge {

struct PumpFullAspirationCommand {
  PumpId pump;
};

PumpHomeContractStatus parsePumpFullAspiration(
    const InboundMessage& message, PumpFullAspirationCommand& command);
CommandSemanticIdentity semanticIdentity(const PumpFullAspirationCommand& command);

}  // namespace labforge
