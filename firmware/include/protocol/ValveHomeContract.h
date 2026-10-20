#pragma once

#include "protocol/CommandStatusCache.h"
#include "protocol/ProtocolTypes.h"

namespace labforge {

enum class ValveHomeContractStatus : uint8_t {
  VALID,
  UNSUPPORTED_COMMAND,
  INVALID_ARGUMENTS,
};

struct ValveHomeCommand { ValveId valve; };

ValveHomeContractStatus parseValveHome(const InboundMessage& message,
                                       ValveHomeCommand& command);
CommandSemanticIdentity semanticIdentity(const ValveHomeCommand& command);

}  // namespace labforge
