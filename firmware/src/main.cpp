#include <Arduino.h>

#include "identity/ArduinoEepromStorage.h"
#include "identity/BootIdentityStore.h"
#include "protocol/LineReceiver.h"
#include "protocol/HelloOkWriter.h"
#include "protocol/MessageParser.h"
#include "protocol/ProtocolTypes.h"
#include "protocol/SessionState.h"
#include "protocol/StatusWriter.h"

namespace {
labforge::ArduinoEepromStorage bootIdentityStorage;
labforge::BootIdentityStore bootIdentityStore(bootIdentityStorage);
labforge::BootIdentityResult bootIdentityResult{
    false, 0, labforge::IdentityFailureReason::NO_VALID_RECORD};
labforge::LineReceiver lineReceiver;
labforge::MessageParser messageParser;
labforge::SessionState sessionState;
uint8_t protocolOutputFrame[labforge::kStatusFrameCapacity];
volatile labforge::ParseStatus lastParseStatus = labforge::ParseStatus::NO_FRAME;
}  // namespace

void setup() {
  // This protocol-foundation slice intentionally has no actuator side effects.
  Serial.begin(labforge::kSerialBaud);
  bootIdentityResult = bootIdentityStore.initialize();
}

void loop() {
  while (Serial.available() > 0) {
    labforge::FrameView frame{};
    const labforge::LineEvent event = lineReceiver.feed(static_cast<uint8_t>(Serial.read()), frame);
    if (event == labforge::LineEvent::LINE_TOO_LONG) {
      lastParseStatus = labforge::ParseStatus::OVERSIZED_FRAME;
    } else if (event == labforge::LineEvent::FRAME_READY) {
      const labforge::ParseResult result = messageParser.parse(frame.data, frame.length);
      lastParseStatus = result.status;
      if (result.status == labforge::ParseStatus::VALID_MESSAGE &&
          result.message.type == labforge::MessageType::HELLO) {
        size_t outputLength = 0;
        if (labforge::writeHelloOk(result.message.backendSessionNonce, bootIdentityResult,
                                   protocolOutputFrame, sizeof(protocolOutputFrame), outputLength)) {
          sessionState.establish(result.message.backendSessionNonce);
          Serial.write(protocolOutputFrame, outputLength);
        }
      } else if (result.status == labforge::ParseStatus::VALID_MESSAGE &&
                 result.message.type == labforge::MessageType::QUERY_STATUS &&
                 sessionState.validate(result.message.backendSessionNonce,
                                       result.message.controllerBootIdPresence,
                                       result.message.controllerBootId,
                                       bootIdentityResult) ==
                     labforge::SessionValidationResult::VALID) {
        size_t outputLength = 0;
        if (labforge::writeStatus(result.message.backendSessionNonce,
                                  result.message.requestId, bootIdentityResult,
                                  protocolOutputFrame, sizeof(protocolOutputFrame),
                                  outputLength)) {
          Serial.write(protocolOutputFrame, outputLength);
        }
      }
    }
  }
}
