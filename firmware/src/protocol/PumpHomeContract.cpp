#include "protocol/PumpHomeContract.h"

#include <string.h>

namespace labforge {

PumpHomeContractStatus parsePumpHome(const InboundMessage& message,
                                     PumpHomeCommand& command) {
  if (message.type != MessageType::COMMAND ||
      strcmp(message.command, "PUMP_HOME") != 0) {
    return PumpHomeContractStatus::UNSUPPORTED_COMMAND;
  }
  if (message.argumentCount != 1)
    return PumpHomeContractStatus::INVALID_ARGUMENTS;

  const Argument& argument = message.arguments[0];
  if (strcmp(argument.key, "pump") != 0 ||
      argument.type != ArgumentType::STRING ||
      strcmp(argument.value.stringValue, "P1") != 0) {
    return PumpHomeContractStatus::INVALID_ARGUMENTS;
  }

  command = {PumpId::P1};
  return PumpHomeContractStatus::VALID;
}

CommandSemanticIdentity semanticIdentity(const PumpHomeCommand& command) {
  return {CommandKind::PUMP_HOME, command.pump, 0};
}

}  // namespace labforge
