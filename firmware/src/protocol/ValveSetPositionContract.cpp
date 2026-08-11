#include "protocol/ValveSetPositionContract.h"

#include <string.h>

namespace labforge {
namespace {

ValveId parseValve(const char* value) {
  if (value[0] != 'V' || value[2] != '\0' || value[1] < '1' || value[1] > '8')
    return ValveId::NONE;
  return static_cast<ValveId>(static_cast<uint8_t>(ValveId::V1) +
                              static_cast<uint8_t>(value[1] - '1'));
}

bool validDegrees(int64_t value) {
  return value == 0 || value == 90 || value == 180;
}

}  // namespace

ValveSetPositionContractStatus parseValveSetPosition(
    const InboundMessage& message, ValveSetPositionCommand& command) {
  if (message.type != MessageType::COMMAND ||
      strcmp(message.command, "VALVE_SET_POSITION") != 0)
    return ValveSetPositionContractStatus::UNSUPPORTED_COMMAND;
  if (message.argumentCount != 2)
    return ValveSetPositionContractStatus::INVALID_ARGUMENTS;
  ValveSetPositionCommand parsed{};
  bool valveFound = false;
  bool positionFound = false;
  for (uint8_t i = 0; i < message.argumentCount; ++i) {
    const Argument& argument = message.arguments[i];
    if (strcmp(argument.key, "valve") == 0) {
      if (valveFound || argument.type != ArgumentType::STRING)
        return ValveSetPositionContractStatus::INVALID_ARGUMENTS;
      parsed.valve = parseValve(argument.value.stringValue);
      if (parsed.valve == ValveId::NONE)
        return ValveSetPositionContractStatus::INVALID_ARGUMENTS;
      valveFound = true;
    } else if (strcmp(argument.key, "position_degrees") == 0) {
      if (positionFound || argument.type != ArgumentType::INTEGER ||
          !validDegrees(argument.value.integerValue))
        return ValveSetPositionContractStatus::INVALID_ARGUMENTS;
      parsed.targetDegrees =
          static_cast<uint16_t>(argument.value.integerValue);
      positionFound = true;
    } else {
      return ValveSetPositionContractStatus::INVALID_ARGUMENTS;
    }
  }
  if (!valveFound || !positionFound)
    return ValveSetPositionContractStatus::INVALID_ARGUMENTS;
  command = parsed;
  return ValveSetPositionContractStatus::VALID;
}

CommandSemanticIdentity semanticIdentity(
    const ValveSetPositionCommand& command) {
  return {CommandKind::VALVE_SET_POSITION, PumpId::NONE, 0, command.valve,
          command.targetDegrees};
}

}  // namespace labforge
