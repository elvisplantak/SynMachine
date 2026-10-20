#pragma once

#include "protocol/CommandStatusCache.h"
#include "protocol/ProtocolTypes.h"

namespace labforge {

enum class ColumnValveContractStatus : uint8_t {
  VALID,
  UNSUPPORTED_COMMAND,
  INVALID_ARGUMENTS,
};

struct ColumnBottomValveCommand {
  CommandKind kind;
  uint16_t targetDegrees;
};

ColumnValveContractStatus parseColumnBottomValve(
    const InboundMessage& message, ColumnBottomValveCommand& command);
CommandSemanticIdentity semanticIdentity(
    const ColumnBottomValveCommand& command);

}  // namespace labforge
