#pragma once

#include <stddef.h>
#include <stdint.h>

namespace labforge {

constexpr uint32_t kSerialBaud = 115200;
constexpr size_t kUuidTextCapacity = 37;
constexpr size_t kPhaseExecutionIdCapacity = 65;
constexpr size_t kCommandCapacity = 33;
constexpr size_t kArgumentKeyCapacity = 25;
constexpr size_t kArgumentStringCapacity = 65;
constexpr size_t kMaxArguments = 8;
constexpr size_t kJsonDocumentCapacity = 1024;

enum class MessageType : uint8_t { HELLO, COMMAND, QUERY_STATUS, QUERY_COMMAND };
enum class ArgumentType : uint8_t { STRING, INTEGER, BOOLEAN };
enum class BootIdPresence : uint8_t { ABSENT, NULL_VALUE, VALUE };

struct Argument {
  char key[kArgumentKeyCapacity];
  ArgumentType type;
  union {
    char stringValue[kArgumentStringCapacity];
    int64_t integerValue;
    bool booleanValue;
  } value;
};

struct InboundMessage {
  MessageType type;
  char backendSessionNonce[kUuidTextCapacity];
  BootIdPresence controllerBootIdPresence;
  uint32_t controllerBootId;
  char phaseExecutionId[kPhaseExecutionIdCapacity];
  char operationCommandId[kUuidTextCapacity];
  char requestId[kUuidTextCapacity];
  char command[kCommandCapacity];
  Argument arguments[kMaxArguments];
  uint8_t argumentCount;
};

enum class ParseStatus : uint8_t { NO_FRAME, VALID_MESSAGE, INVALID_MESSAGE, OVERSIZED_FRAME };
enum class ProtocolErrorCode : uint8_t {
  NONE,
  MALFORMED_MESSAGE,
  LINE_TOO_LONG,
  UNSUPPORTED_PROTOCOL_VERSION,
  MISSING_FIELD,
  INVALID_FIELD,
  UNSUPPORTED_MESSAGE_TYPE
};

struct ParseResult {
  ParseStatus status;
  ProtocolErrorCode error;
  InboundMessage message;
};

}  // namespace labforge
