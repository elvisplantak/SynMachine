#include "protocol/PumpMoveAbsoluteStepsContract.h"

#include <string.h>

namespace labforge {

PumpMoveContractStatus parsePumpMoveAbsoluteSteps(
    const InboundMessage& message, PumpMoveAbsoluteStepsCommand& command) {
  if (message.type != MessageType::COMMAND ||
      strcmp(message.command, "PUMP_MOVE_ABSOLUTE_STEPS") != 0) {
    return PumpMoveContractStatus::UNSUPPORTED_COMMAND;
  }
  if (message.argumentCount != 2)
    return PumpMoveContractStatus::INVALID_ARGUMENTS;

  bool pumpFound = false;
  bool targetFound = false;
  PumpMoveAbsoluteStepsCommand parsed{};
  for (uint8_t i = 0; i < message.argumentCount; ++i) {
    const Argument& argument = message.arguments[i];
    if (strcmp(argument.key, "pump") == 0) {
      if (pumpFound || argument.type != ArgumentType::STRING) {
        return PumpMoveContractStatus::INVALID_ARGUMENTS;
      }
      if (strcmp(argument.value.stringValue, "P1") == 0)
        parsed.pump = PumpId::P1;
      else if (strcmp(argument.value.stringValue, "P2") == 0)
        parsed.pump = PumpId::P2;
      else
        return PumpMoveContractStatus::INVALID_ARGUMENTS;
      pumpFound = true;
    } else if (strcmp(argument.key, "target_steps") == 0) {
      if (targetFound || argument.type != ArgumentType::INTEGER ||
          argument.value.integerValue < 1 ||
          argument.value.integerValue > kP1MaximumAbsoluteSteps) {
        return PumpMoveContractStatus::INVALID_ARGUMENTS;
      }
      parsed.targetSteps = static_cast<uint16_t>(argument.value.integerValue);
      targetFound = true;
    } else {
      return PumpMoveContractStatus::INVALID_ARGUMENTS;
    }
  }
  if (!pumpFound || !targetFound)
    return PumpMoveContractStatus::INVALID_ARGUMENTS;
  command = parsed;
  return PumpMoveContractStatus::VALID;
}

CommandSemanticIdentity semanticIdentity(
    const PumpMoveAbsoluteStepsCommand& command) {
  return {CommandKind::PUMP_MOVE_ABSOLUTE_STEPS, command.pump,
          command.targetSteps};
}

}  // namespace labforge
