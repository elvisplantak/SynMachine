#include <Arduino.h>

#include "protocol/LineReceiver.h"
#include "protocol/MessageParser.h"
#include "protocol/ProtocolTypes.h"

namespace {
labforge::LineReceiver lineReceiver;
labforge::MessageParser messageParser;
volatile labforge::ParseStatus lastParseStatus = labforge::ParseStatus::NO_FRAME;
}  // namespace

void setup() {
  // This protocol-foundation slice intentionally has no actuator side effects.
  Serial.begin(labforge::kSerialBaud);
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
    }
  }
}
