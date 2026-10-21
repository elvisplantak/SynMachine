#include "protocol/PumpFullAspirationContract.h"

#include <string.h>

namespace labforge {

PumpHomeContractStatus parsePumpFullAspiration(
    const InboundMessage& message, PumpFullAspirationCommand& command) {
  if (message.type != MessageType::COMMAND ||
      strcmp(message.command, "PUMP_ASPIRATE_FULL_STROKE") != 0)
    return PumpHomeContractStatus::UNSUPPORTED_COMMAND;
  if (message.argumentCount != 1)
    return PumpHomeContractStatus::INVALID_ARGUMENTS;
  const Argument& argument = message.arguments[0];
  if (strcmp(argument.key, "pump") != 0 ||
      argument.type != ArgumentType::STRING)
    return PumpHomeContractStatus::INVALID_ARGUMENTS;
  if (strcmp(argument.value.stringValue, "P1") == 0)
    command = {PumpId::P1};
  else if (strcmp(argument.value.stringValue, "P2") == 0)
    command = {PumpId::P2};
  else
    return PumpHomeContractStatus::INVALID_ARGUMENTS;
  return PumpHomeContractStatus::VALID;
}

CommandSemanticIdentity semanticIdentity(const PumpFullAspirationCommand& command) {
  return {CommandKind::PUMP_ASPIRATE_FULL_STROKE, command.pump, 0, ValveId::NONE, 0};
}

}  // namespace labforge
