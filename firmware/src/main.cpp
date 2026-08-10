#include <Arduino.h>

#include "actuator/P1MotionController.h"
#include "arduino/ArduinoP1MotionIo.h"
#include "identity/ArduinoEepromStorage.h"
#include "identity/BootIdentityStore.h"
#include "protocol/CommandLifecycleWriter.h"
#include "protocol/CommandStatusCache.h"
#include "protocol/CommandStatusWriter.h"
#include "protocol/LineReceiver.h"
#include "protocol/NoMotionDispatcher.h"
#include "protocol/ProtocolErrorWriter.h"
#include "protocol/ProtocolTypes.h"
#include "protocol/SessionState.h"
#include "service/P1CommandRuntime.h"

namespace {
labforge::ArduinoEepromStorage bootIdentityStorage;
labforge::BootIdentityStore bootIdentityStore(bootIdentityStorage);
labforge::BootIdentityResult bootIdentityResult{
    false, 0, labforge::IdentityFailureReason::NO_VALID_RECORD};
labforge::LineReceiver lineReceiver;
labforge::NoMotionDispatcher framingErrorDispatcher(true);
labforge::SessionState sessionState;
labforge::CommandStatusCache commandStatusCache;
labforge::ArduinoP1MotionIo p1MotionIo;
labforge::P1MotionController p1MotionController(p1MotionIo);
labforge::P1CommandRuntime p1CommandRuntime(p1MotionController);
uint8_t protocolOutputFrame[labforge::kCommandStatusFrameCapacity];
volatile labforge::ParseStatus lastParseStatus = labforge::ParseStatus::NO_FRAME;

void emitPendingLifecycleFrames() {
  size_t outputLength = 0;
  bool startsMotion = false;
  while (p1CommandRuntime.nextLifecycleFrame(
      bootIdentityResult, commandStatusCache, protocolOutputFrame,
      sizeof(protocolOutputFrame), outputLength, startsMotion)) {
    const size_t written = Serial.write(protocolOutputFrame, outputLength);
    if (startsMotion) {
      if (written == outputLength) {
        p1CommandRuntime.confirmStartedFrameWritten(micros());
      }
      break;
    }
  }
}
}  // namespace

void setup() {
  // Pin setup is motion-inactive. Commands remain gated by HELLO/session checks.
  Serial.begin(labforge::kSerialBaud);
  bootIdentityResult = bootIdentityStore.initialize();
  p1MotionIo.begin();
}

void loop() {
  p1CommandRuntime.update(micros(), commandStatusCache);
  emitPendingLifecycleFrames();

  while (Serial.available() > 0) {
    labforge::FrameView frame{};
    const labforge::LineEvent event = lineReceiver.feed(static_cast<uint8_t>(Serial.read()), frame);
    if (event == labforge::LineEvent::LINE_TOO_LONG) {
      const labforge::DispatchResult result = framingErrorDispatcher.lineTooLong(
          bootIdentityResult, protocolOutputFrame, sizeof(protocolOutputFrame));
      lastParseStatus = result.parseStatus;
      if (result.outputLength > 0) {
        Serial.write(protocolOutputFrame, result.outputLength);
      }
    } else if (event == labforge::LineEvent::FRAME_READY) {
      const labforge::DispatchResult result = p1CommandRuntime.dispatch(
          frame.data, frame.length, bootIdentityResult, sessionState,
          commandStatusCache, protocolOutputFrame, sizeof(protocolOutputFrame));
      lastParseStatus = result.parseStatus;
      if (result.outputLength > 0) {
        Serial.write(protocolOutputFrame, result.outputLength);
      }
      emitPendingLifecycleFrames();
    }
  }

  p1CommandRuntime.update(micros(), commandStatusCache);
  emitPendingLifecycleFrames();
}
