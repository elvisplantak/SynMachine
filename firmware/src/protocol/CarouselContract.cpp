#include "protocol/CarouselContract.h"

#include <string.h>

namespace labforge {

CarouselContractStatus parseCarousel(const InboundMessage& message,
                                     CarouselCommand& command) {
  if (message.type != MessageType::COMMAND)
    return CarouselContractStatus::UNSUPPORTED_COMMAND;
  CommandKind kind = CommandKind::NONE;
  if (strcmp(message.command, "CAROUSEL_SET_REFERENCE") == 0) {
    kind = CommandKind::CAROUSEL_SET_REFERENCE;
  } else if (strcmp(message.command, "CAROUSEL_MOVE_TO_POSITION") == 0) {
    kind = CommandKind::CAROUSEL_MOVE_TO_POSITION;
  } else {
    return CarouselContractStatus::UNSUPPORTED_COMMAND;
  }
  if (message.argumentCount != 1 ||
      strcmp(message.arguments[0].key, "position") != 0 ||
      message.arguments[0].type != ArgumentType::INTEGER)
    return CarouselContractStatus::INVALID_ARGUMENTS;
  const int64_t position = message.arguments[0].value.integerValue;
  if (position < 1 || position > kCarouselPositionCount)
    return CarouselContractStatus::INVALID_ARGUMENTS;
  command = {kind, static_cast<uint8_t>(position)};
  return CarouselContractStatus::VALID;
}

CommandSemanticIdentity semanticIdentity(const CarouselCommand& command) {
  return {command.kind, PumpId::NONE, 0, ValveId::NONE, 0,
          command.position};
}

}  // namespace labforge
