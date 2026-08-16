#include <Arduino.h>

#include "actuator/P1MotionController.h"
#include "actuator/CarouselMotionController.h"
#include "actuator/ColumnBottomValveMotionController.h"
#include "arduino/ArduinoCarouselMotionIo.h"
#include "arduino/ArduinoP1MotionIo.h"
#include "arduino/ArduinoP2MotionIo.h"
#include "arduino/ArduinoSfMixerMotionIo.h"
#include "arduino/ArduinoValveMotionIo.h"
#include "identity/ArduinoEepromStorage.h"
#include "identity/BootIdentityStore.h"
#include "protocol/CommandLifecycleWriter.h"
#include "protocol/CommandStatusCache.h"
#include "protocol/CommandStatusWriter.h"
#include "protocol/CooperativeFrameTransport.h"
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
labforge::ArduinoP2MotionIo p2MotionIo;
labforge::P1MotionController p2MotionController(p2MotionIo);
labforge::ArduinoValveMotionIo valveMotionIo[] = {
    {22, 23, 39}, {24, 25, 38}, {26, 27, 43}, {28, 29, 40},
    {30, 31, 41}, {32, 33, 42}, {36, 37, 3},  {34, 35, 2},
};
labforge::ValveMotionController valveMotionControllers[] = {
    {valveMotionIo[0], true}, {valveMotionIo[1], false},
    {valveMotionIo[2], true}, {valveMotionIo[3], true},
    {valveMotionIo[4], true}, {valveMotionIo[5], false},
    {valveMotionIo[6], true}, {valveMotionIo[7], true},
};
labforge::ValveMotionController* valveControllerPointers[] = {
    &valveMotionControllers[0], &valveMotionControllers[1],
    &valveMotionControllers[2], &valveMotionControllers[3],
    &valveMotionControllers[4], &valveMotionControllers[5],
    &valveMotionControllers[6], &valveMotionControllers[7],
};
labforge::ArduinoValveMotionIo columnValveMotionIo(12, 13, 10);
labforge::ColumnBottomValveMotionController columnValveMotionController(
    columnValveMotionIo);
labforge::ArduinoCarouselMotionIo carouselMotionIo;
labforge::CarouselMotionController carouselMotionController(carouselMotionIo);
labforge::ArduinoSfMixerMotionIo sfMixerMotionIo;
labforge::SfMixerMotionController sfMixerMotionController(sfMixerMotionIo);
labforge::P1CommandRuntime p1CommandRuntime(
    p1MotionController, p2MotionController, valveControllerPointers, 8,
    columnValveMotionController, carouselMotionController,
    sfMixerMotionController);
uint8_t protocolOutputFrame[labforge::kCommandStatusFrameCapacity];
labforge::CooperativeFrameTransport frameTransport;
volatile labforge::ParseStatus lastParseStatus = labforge::ParseStatus::NO_FRAME;

bool queueFrame(size_t outputLength, bool startsMotion = false) {
  if (outputLength == 0) return true;
  return frameTransport.begin(outputLength, startsMotion);
}

void queuePendingLifecycleFrame() {
  if (frameTransport.pending()) return;
  size_t outputLength = 0;
  bool startsMotion = false;
  if (p1CommandRuntime.nextLifecycleFrame(
          bootIdentityResult, commandStatusCache, protocolOutputFrame,
          sizeof(protocolOutputFrame), outputLength, startsMotion) &&
      !queueFrame(outputLength, startsMotion) && startsMotion) {
    p1CommandRuntime.startedFrameTransportFailed();
  }
}

void serviceFrameTransport() {
  if (!frameTransport.pending()) return;
  const size_t available = static_cast<size_t>(Serial.availableForWrite());
  const labforge::FrameTxSlice slice = frameTransport.nextSlice(available);
  if (slice.length == 0) return;
  const size_t written =
      Serial.write(protocolOutputFrame + slice.offset, slice.length);
  const labforge::FrameTxCompletion completion =
      frameTransport.commit(slice.length, written);
  if (completion == labforge::FrameTxCompletion::STARTED_FRAME_COMPLETE)
    p1CommandRuntime.confirmStartedFrameWritten(micros(), commandStatusCache);
}
}  // namespace

void setup() {
  // Pin setup is motion-inactive. Commands remain gated by HELLO/session checks.
  p1MotionIo.begin();
  p2MotionIo.begin();
  for (labforge::ArduinoValveMotionIo& io : valveMotionIo) io.begin();
  columnValveMotionIo.begin();
  carouselMotionIo.begin();
  sfMixerMotionIo.begin();
  Serial.begin(labforge::kSerialBaud);
  bootIdentityResult = bootIdentityStore.initialize();
}

void loop() {
  p1CommandRuntime.update(micros(), commandStatusCache);
  queuePendingLifecycleFrame();
  serviceFrameTransport();

  constexpr uint8_t kMaxSerialBytesPerLoop = 32;
  for (uint8_t processed = 0;
       !frameTransport.pending() && processed < kMaxSerialBytesPerLoop &&
       Serial.available() > 0;
       ++processed) {
    labforge::FrameView frame{};
    const labforge::LineEvent event = lineReceiver.feed(static_cast<uint8_t>(Serial.read()), frame);
    if (event == labforge::LineEvent::LINE_TOO_LONG) {
      const labforge::DispatchResult result = framingErrorDispatcher.lineTooLong(
          bootIdentityResult, protocolOutputFrame, sizeof(protocolOutputFrame));
      lastParseStatus = result.parseStatus;
      queueFrame(result.outputLength);
    } else if (event == labforge::LineEvent::FRAME_READY) {
      const labforge::DispatchResult result = p1CommandRuntime.dispatch(
          frame.data, frame.length, bootIdentityResult, sessionState,
          commandStatusCache, protocolOutputFrame, sizeof(protocolOutputFrame));
      lastParseStatus = result.parseStatus;
      queueFrame(result.outputLength);
    }
  }

  p1CommandRuntime.update(micros(), commandStatusCache);
  queuePendingLifecycleFrame();
  serviceFrameTransport();
}
