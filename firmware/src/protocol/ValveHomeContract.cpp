#include "protocol/ValveHomeContract.h"

#include <string.h>

namespace labforge {
namespace {

ValveId parseValve(const char* value) {
  if (value[0] != 'V' || value[2] != '\0' || value[1] < '1' || value[1] > '8')
    return ValveId::NONE;
  return static_cast<ValveId>(static_cast<uint8_t>(ValveId::V1) +
                              static_cast<uint8_t>(value[1] - '1'));
}

}  // namespace

ValveHomeContractStatus parseValveHome(const InboundMessage& message,
                                       ValveHomeCommand& command) {
  if (message.type != MessageType::COMMAND ||
      strcmp(message.command, "VALVE_HOME") != 0)
    return ValveHomeContractStatus::UNSUPPORTED_COMMAND;
  if (message.argumentCount != 1 ||
      strcmp(message.arguments[0].key, "valve") != 0 ||
      message.arguments[0].type != ArgumentType::STRING)
    return ValveHomeContractStatus::INVALID_ARGUMENTS;
  const ValveId valve = parseValve(message.arguments[0].value.stringValue);
  if (valve == ValveId::NONE)
    return ValveHomeContractStatus::INVALID_ARGUMENTS;
  command = {valve};
  return ValveHomeContractStatus::VALID;
}

CommandSemanticIdentity semanticIdentity(const ValveHomeCommand& command) {
  return {CommandKind::VALVE_HOME, PumpId::NONE, 0, command.valve, 0};
}

}  // namespace labforge
