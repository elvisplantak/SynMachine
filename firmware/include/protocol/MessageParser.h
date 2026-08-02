#pragma once

#include "protocol/ProtocolTypes.h"

namespace labforge {

class MessageParser {
 public:
  ParseResult parse(const uint8_t* payload, size_t length) const;
  ErrorCorrelation recoverErrorCorrelation(const uint8_t* payload, size_t length) const;
};

}  // namespace labforge
