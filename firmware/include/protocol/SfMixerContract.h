#pragma once

#include "protocol/CommandStatusCache.h"
#include "protocol/ProtocolTypes.h"

namespace labforge {

enum class SfMixerContractStatus : uint8_t {
  VALID,
  UNSUPPORTED_COMMAND,
  INVALID_ARGUMENTS,
};

struct SfMixerCommand {
  bool running;
};

SfMixerContractStatus parseSfMixer(const InboundMessage& message,
                                   SfMixerCommand& command);
CommandSemanticIdentity semanticIdentity(const SfMixerCommand& command);

}  // namespace labforge
