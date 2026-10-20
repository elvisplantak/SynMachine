#include "protocol/MessageParser.h"

#include <ArduinoJson.h>
#include <string.h>

#include "protocol/LineReceiver.h"
#include "protocol/StrictJsonValidator.h"

namespace labforge {
namespace {

ParseResult failure(ProtocolErrorCode error) {
  ParseResult result{};
  result.status = ParseStatus::INVALID_MESSAGE;
  result.error = error;
  return result;
}

bool asciiBytes(const char* value, size_t minimum, size_t maximum) {
  if (value == nullptr) return false;
  const size_t length = strlen(value);
  if (length < minimum || length > maximum) return false;
  for (size_t i = 0; i < length; ++i) {
    if (static_cast<unsigned char>(value[i]) > 0x7F) return false;
  }
  return true;
}

bool validUuid(const char* value) {
  if (!asciiBytes(value, 36, 36)) return false;
  for (size_t i = 0; i < 36; ++i) {
    if (i == 8 || i == 13 || i == 18 || i == 23) {
      if (value[i] != '-') return false;
    } else if (!((value[i] >= '0' && value[i] <= '9') || (value[i] >= 'a' && value[i] <= 'f'))) {
      return false;
    }
  }
  return true;
}

bool validPhaseId(const char* value) {
  if (!asciiBytes(value, 1, 64)) return false;
  for (const char* cursor = value; *cursor != '\0'; ++cursor) {
    const char c = *cursor;
    if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') ||
          c == '-' || c == '_' || c == '.' || c == ':')) return false;
  }
  return true;
}

bool validUpperIdentifier(const char* value, size_t maximum) {
  if (!asciiBytes(value, 1, maximum)) return false;
  for (const char* cursor = value; *cursor != '\0'; ++cursor) {
    if (!((*cursor >= 'A' && *cursor <= 'Z') || (*cursor >= '0' && *cursor <= '9') || *cursor == '_')) return false;
  }
  return true;
}

bool copyChecked(const char* source, char* destination, size_t capacity) {
  if (source == nullptr || strlen(source) >= capacity) return false;
  strcpy(destination, source);
  return true;
}

bool extractUuid(JsonObjectConst object, const char* name, char* output) {
  if (!object[name].is<const char*>()) return false;
  const char* value = object[name].as<const char*>();
  return validUuid(value) && copyChecked(value, output, kUuidTextCapacity);
}

bool extractBootId(JsonObjectConst object, BootIdPresence& presence, uint32_t& output) {
  JsonVariantConst value = object["controller_boot_id"];
  if (value.isNull()) {
    presence = BootIdPresence::NULL_VALUE;
    output = 0;
    return true;
  }
  if (value.is<bool>() || !value.is<uint64_t>()) return false;
  const uint64_t number = value.as<uint64_t>();
  if (number > UINT32_MAX) return false;
  presence = BootIdPresence::VALUE;
  output = static_cast<uint32_t>(number);
  return true;
}

bool allowedField(const char* key, MessageType type) {
  if (strcmp(key, "protocol") == 0 || strcmp(key, "type") == 0 || strcmp(key, "backend_session_nonce") == 0) return true;
  if (type == MessageType::HELLO) return false;
  if (strcmp(key, "controller_boot_id") == 0) return true;
  if (type == MessageType::COMMAND) {
    return strcmp(key, "phase_execution_id") == 0 || strcmp(key, "operation_command_id") == 0 ||
           strcmp(key, "command") == 0 || strcmp(key, "arguments") == 0;
  }
  if (strcmp(key, "request_id") == 0) return true;
  return type == MessageType::QUERY_COMMAND && strcmp(key, "operation_command_id") == 0;
}

bool hasRequiredFields(JsonObjectConst object, MessageType type) {
  if (!object.containsKey("protocol") || !object.containsKey("type") || !object.containsKey("backend_session_nonce")) return false;
  if (type == MessageType::HELLO) return true;
  if (!object.containsKey("controller_boot_id")) return false;
  if (type == MessageType::COMMAND) {
    return object.containsKey("phase_execution_id") && object.containsKey("operation_command_id") &&
           object.containsKey("command") && object.containsKey("arguments");
  }
  if (!object.containsKey("request_id")) return false;
  return type != MessageType::QUERY_COMMAND || object.containsKey("operation_command_id");
}

bool parseArguments(JsonVariantConst value, InboundMessage& message) {
  if (!value.is<JsonObjectConst>()) return false;
  JsonObjectConst arguments = value.as<JsonObjectConst>();
  if (arguments.size() > kMaxArguments) return false;
  message.argumentCount = 0;
  for (JsonPairConst pair : arguments) {
    const char* key = pair.key().c_str();
    if (!asciiBytes(key, 1, 24)) return false;
    Argument& argument = message.arguments[message.argumentCount];
    if (!copyChecked(key, argument.key, sizeof(argument.key))) return false;
    JsonVariantConst item = pair.value();
    if (item.is<bool>()) {
      argument.type = ArgumentType::BOOLEAN;
      argument.value.booleanValue = item.as<bool>();
    } else if (item.is<const char*>()) {
      const char* stringValue = item.as<const char*>();
      if (strlen(stringValue) > 64 || !copyChecked(stringValue, argument.value.stringValue,
                                                   sizeof(argument.value.stringValue))) return false;
      argument.type = ArgumentType::STRING;
    } else if (item.is<int64_t>()) {
      argument.type = ArgumentType::INTEGER;
      argument.value.integerValue = item.as<int64_t>();
    } else if (item.is<uint64_t>()) {
      const uint64_t integer = item.as<uint64_t>();
      if (integer > static_cast<uint64_t>(INT64_MAX)) return false;
      argument.type = ArgumentType::INTEGER;
      argument.value.integerValue = static_cast<int64_t>(integer);
    } else {
      return false;
    }
    ++message.argumentCount;
  }
  return true;
}

}  // namespace

ParseResult MessageParser::parse(const uint8_t* payload, size_t length) const {
  if (length > kMaxPayloadBytes) return failure(ProtocolErrorCode::LINE_TOO_LONG);
  const LexicalError lexical = StrictJsonValidator().validate(payload, length);
  if (lexical == LexicalError::NON_INTEGER_NUMBER) return failure(ProtocolErrorCode::INVALID_FIELD);
  if (lexical != LexicalError::NONE) return failure(ProtocolErrorCode::MALFORMED_MESSAGE);

  StaticJsonDocument<kJsonDocumentCapacity> document;
  const DeserializationError jsonError = deserializeJson(document, payload, length);
  if (jsonError || !document.is<JsonObject>()) return failure(ProtocolErrorCode::MALFORMED_MESSAGE);
  JsonObjectConst object = document.as<JsonObjectConst>();

  if (!object.containsKey("protocol") || !object.containsKey("type")) return failure(ProtocolErrorCode::MISSING_FIELD);
  if (!object["protocol"].is<const char*>()) return failure(ProtocolErrorCode::INVALID_FIELD);
  const char* protocol = object["protocol"].as<const char*>();
  if (strcmp(protocol, "LABFORGE/1") != 0) return failure(ProtocolErrorCode::UNSUPPORTED_PROTOCOL_VERSION);
  if (!object["type"].is<const char*>()) return failure(ProtocolErrorCode::INVALID_FIELD);
  const char* typeText = object["type"].as<const char*>();
  if (!asciiBytes(typeText, 1, 32)) return failure(ProtocolErrorCode::INVALID_FIELD);

  MessageType type;
  if (strcmp(typeText, "HELLO") == 0) type = MessageType::HELLO;
  else if (strcmp(typeText, "COMMAND") == 0) type = MessageType::COMMAND;
  else if (strcmp(typeText, "QUERY_STATUS") == 0) type = MessageType::QUERY_STATUS;
  else if (strcmp(typeText, "QUERY_COMMAND") == 0) type = MessageType::QUERY_COMMAND;
  else return failure(ProtocolErrorCode::UNSUPPORTED_MESSAGE_TYPE);

  if (!hasRequiredFields(object, type)) return failure(ProtocolErrorCode::MISSING_FIELD);
  for (JsonPairConst pair : object) {
    if (!allowedField(pair.key().c_str(), type)) return failure(ProtocolErrorCode::INVALID_FIELD);
  }

  ParseResult result{};
  result.status = ParseStatus::VALID_MESSAGE;
  result.error = ProtocolErrorCode::NONE;
  result.message.type = type;
  result.message.controllerBootIdPresence = BootIdPresence::ABSENT;
  if (!extractUuid(object, "backend_session_nonce", result.message.backendSessionNonce)) {
    return failure(ProtocolErrorCode::INVALID_FIELD);
  }
  if (type == MessageType::HELLO) return result;
  if (!extractBootId(object, result.message.controllerBootIdPresence,
                     result.message.controllerBootId)) {
    return failure(ProtocolErrorCode::INVALID_FIELD);
  }

  if (type == MessageType::COMMAND) {
    if (!object["phase_execution_id"].is<const char*>() ||
        !validPhaseId(object["phase_execution_id"].as<const char*>()) ||
        !copyChecked(object["phase_execution_id"].as<const char*>(), result.message.phaseExecutionId,
                     sizeof(result.message.phaseExecutionId)) ||
        !extractUuid(object, "operation_command_id", result.message.operationCommandId) ||
        !object["command"].is<const char*>() ||
        !validUpperIdentifier(object["command"].as<const char*>(), 32) ||
        !copyChecked(object["command"].as<const char*>(), result.message.command, sizeof(result.message.command)) ||
        !parseArguments(object["arguments"], result.message)) {
      return failure(ProtocolErrorCode::INVALID_FIELD);
    }
    return result;
  }

  if (!extractUuid(object, "request_id", result.message.requestId)) return failure(ProtocolErrorCode::INVALID_FIELD);
  if (type == MessageType::QUERY_COMMAND &&
      !extractUuid(object, "operation_command_id", result.message.operationCommandId)) {
    return failure(ProtocolErrorCode::INVALID_FIELD);
  }
  return result;
}

ErrorCorrelation MessageParser::recoverErrorCorrelation(const uint8_t* payload,
                                                        size_t length) const {
  ErrorCorrelation correlation{};
  correlation.kind = ErrorCorrelationKind::NONE;
  if (length > kMaxPayloadBytes) {
    return correlation;
  }
  const LexicalError lexical = StrictJsonValidator().validate(payload, length);
  if (lexical != LexicalError::NONE && lexical != LexicalError::NON_INTEGER_NUMBER) {
    return correlation;
  }

  StaticJsonDocument<kJsonDocumentCapacity> document;
  if (deserializeJson(document, payload, length) || !document.is<JsonObject>()) {
    return correlation;
  }
  JsonObjectConst object = document.as<JsonObjectConst>();
  if (!object["protocol"].is<const char*>() ||
      strcmp(object["protocol"].as<const char*>(), "LABFORGE/1") != 0 ||
      !object["type"].is<const char*>() ||
      !extractUuid(object, "backend_session_nonce", correlation.backendSessionNonce)) {
    return correlation;
  }

  const char* type = object["type"].as<const char*>();
  if ((strcmp(type, "QUERY_STATUS") == 0 || strcmp(type, "QUERY_COMMAND") == 0) &&
      extractUuid(object, "request_id", correlation.requestId)) {
    correlation.kind = ErrorCorrelationKind::QUERY;
  } else if (strcmp(type, "COMMAND") == 0 &&
             object["phase_execution_id"].is<const char*>() &&
             validPhaseId(object["phase_execution_id"].as<const char*>()) &&
             copyChecked(object["phase_execution_id"].as<const char*>(),
                         correlation.phaseExecutionId,
                         sizeof(correlation.phaseExecutionId)) &&
             extractUuid(object, "operation_command_id",
                         correlation.operationCommandId)) {
    correlation.kind = ErrorCorrelationKind::COMMAND;
  }
  return correlation;
}

}  // namespace labforge
