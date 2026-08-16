#include "protocol/SfMixerContract.h"

#include <string.h>

namespace labforge {

SfMixerContractStatus parseSfMixer(const InboundMessage& message,
                                   SfMixerCommand& command) {
  if (message.type != MessageType::COMMAND ||
      strcmp(message.command, "SF_MIXER_SET_STATE") != 0)
    return SfMixerContractStatus::UNSUPPORTED_COMMAND;
  if (message.argumentCount != 1 ||
      strcmp(message.arguments[0].key, "running") != 0 ||
      message.arguments[0].type != ArgumentType::BOOLEAN)
    return SfMixerContractStatus::INVALID_ARGUMENTS;
  command = {message.arguments[0].value.booleanValue};
  return SfMixerContractStatus::VALID;
}

CommandSemanticIdentity semanticIdentity(const SfMixerCommand& command) {
  return {CommandKind::SF_MIXER_SET_STATE, PumpId::NONE, 0, ValveId::NONE, 0,
          0, command.running};
}

}  // namespace labforge
