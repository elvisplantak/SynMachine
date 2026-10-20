#include "protocol/ColumnBottomValveContract.h"

#include <string.h>

namespace labforge {

ColumnValveContractStatus parseColumnBottomValve(
    const InboundMessage& message, ColumnBottomValveCommand& command) {
  if (message.type != MessageType::COMMAND)
    return ColumnValveContractStatus::UNSUPPORTED_COMMAND;
  if (strcmp(message.command, "COLUMN_BOTTOM_VALVE_HOME") == 0) {
    if (message.argumentCount != 0)
      return ColumnValveContractStatus::INVALID_ARGUMENTS;
    command = {CommandKind::COLUMN_BOTTOM_VALVE_HOME, 0};
    return ColumnValveContractStatus::VALID;
  }
  if (strcmp(message.command, "COLUMN_BOTTOM_VALVE_SET_POSITION") != 0)
    return ColumnValveContractStatus::UNSUPPORTED_COMMAND;
  if (message.argumentCount != 1 ||
      strcmp(message.arguments[0].key, "position_degrees") != 0 ||
      message.arguments[0].type != ArgumentType::INTEGER)
    return ColumnValveContractStatus::INVALID_ARGUMENTS;
  const int64_t degrees = message.arguments[0].value.integerValue;
  if (degrees != 4 && degrees != 94)
    return ColumnValveContractStatus::INVALID_ARGUMENTS;
  command = {CommandKind::COLUMN_BOTTOM_VALVE_SET_POSITION,
             static_cast<uint16_t>(degrees)};
  return ColumnValveContractStatus::VALID;
}

CommandSemanticIdentity semanticIdentity(
    const ColumnBottomValveCommand& command) {
  return {command.kind, PumpId::NONE, 0, ValveId::NONE,
          command.targetDegrees};
}

}  // namespace labforge
