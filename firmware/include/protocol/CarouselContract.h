#pragma once

#include "actuator/CarouselMotionController.h"
#include "protocol/CommandStatusCache.h"
#include "protocol/ProtocolTypes.h"

namespace labforge {

enum class CarouselContractStatus : uint8_t {
  VALID,
  UNSUPPORTED_COMMAND,
  INVALID_ARGUMENTS,
};

struct CarouselCommand {
  CommandKind kind;
  uint8_t position;
};

CarouselContractStatus parseCarousel(const InboundMessage& message,
                                     CarouselCommand& command);
CommandSemanticIdentity semanticIdentity(const CarouselCommand& command);

}  // namespace labforge
