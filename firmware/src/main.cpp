#include <Arduino.h>

#include "identity/ArduinoEepromStorage.h"
#include "identity/BootIdentityStore.h"
#include "protocol/LineReceiver.h"
#include "protocol/NoMotionDispatcher.h"
#include "protocol/ProtocolErrorWriter.h"
#include "protocol/ProtocolTypes.h"
#include "protocol/SessionState.h"

namespace {
labforge::ArduinoEepromStorage bootIdentityStorage;
labforge::BootIdentityStore bootIdentityStore(bootIdentityStorage);
labforge::BootIdentityResult bootIdentityResult{
    false, 0, labforge::IdentityFailureReason::NO_VALID_RECORD};
labforge::LineReceiver lineReceiver;
labforge::NoMotionDispatcher dispatcher;
labforge::SessionState sessionState;
uint8_t protocolOutputFrame[labforge::kProtocolErrorFrameCapacity];
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
      const labforge::DispatchResult result = dispatcher.lineTooLong(
          bootIdentityResult, protocolOutputFrame, sizeof(protocolOutputFrame));
      lastParseStatus = result.parseStatus;
      if (result.outputLength > 0) {
        Serial.write(protocolOutputFrame, result.outputLength);
      }
    } else if (event == labforge::LineEvent::FRAME_READY) {
      const labforge::DispatchResult result = dispatcher.dispatch(
          frame.data, frame.length, bootIdentityResult, sessionState,
          protocolOutputFrame, sizeof(protocolOutputFrame));
      lastParseStatus = result.parseStatus;
      if (result.outputLength > 0) {
        Serial.write(protocolOutputFrame, result.outputLength);
      }
    }
  }
}
