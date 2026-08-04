#include <Arduino.h>

#include <string.h>

#include "commissioning/PinDiscoveryController.h"

namespace {

constexpr unsigned long kSerialBaud = 115200;
constexpr unsigned long kArmTimeoutMs = 10000;
constexpr unsigned int kPulseHighUs = 20;
constexpr unsigned long kPulseSpacingMs = 50;
constexpr size_t kInputCapacity = 24;

labforge::PinDiscoveryController controller;
char input[kInputCapacity];
size_t inputLength = 0;
unsigned long armedAtMs = 0;
bool discardingInput = false;

void releasePins(const labforge::PinDiscoveryPins& pins) {
  digitalWrite(pins.step, LOW);
  digitalWrite(pins.direction, LOW);
  pinMode(pins.step, INPUT);
  pinMode(pins.direction, INPUT);
}

void emitPulses(const labforge::PinDiscoveryResult& result) {
  pinMode(result.pins.direction, OUTPUT);
  digitalWrite(result.pins.direction,
               result.direction == labforge::PinDiscoveryDirection::LOGIC_HIGH
                   ? HIGH
                   : LOW);
  delay(5);
  pinMode(result.pins.step, OUTPUT);
  digitalWrite(result.pins.step, LOW);
  for (uint8_t pulse = 0; pulse < result.pulseCount; ++pulse) {
    digitalWrite(result.pins.step, HIGH);
    delayMicroseconds(kPulseHighUs);
    digitalWrite(result.pins.step, LOW);
    if (pulse + 1 < result.pulseCount) delay(kPulseSpacingMs);
  }
  releasePins(result.pins);
}

void printStatus(labforge::PinDiscoveryStatus status) {
  Serial.print(F("STATUS "));
  switch (status) {
    case labforge::PinDiscoveryStatus::OK:
      Serial.println(F("OK"));
      return;
    case labforge::PinDiscoveryStatus::INVALID_COMMAND:
      Serial.println(F("INVALID_COMMAND"));
      return;
    case labforge::PinDiscoveryStatus::SELECTION_REQUIRED:
      Serial.println(F("SELECTION_REQUIRED"));
      return;
    case labforge::PinDiscoveryStatus::DIRECTION_REQUIRED:
      Serial.println(F("DIRECTION_REQUIRED"));
      return;
    case labforge::PinDiscoveryStatus::NOT_ARMED:
      Serial.println(F("NOT_ARMED"));
      return;
    case labforge::PinDiscoveryStatus::INVALID_PULSE_COUNT:
      Serial.println(F("INVALID_PULSE_COUNT"));
      return;
  }
  Serial.println(F("INTERNAL_ERROR"));
}

void handleCommand() {
  input[inputLength] = '\0';
  const labforge::PinDiscoveryResult result = controller.process(input);
  if (strcmp(input, "ARM") == 0 &&
      result.status == labforge::PinDiscoveryStatus::OK)
    armedAtMs = millis();
  if (result.action == labforge::PinDiscoveryAction::EMIT_PULSES)
    emitPulses(result);
  printStatus(result.status);
  inputLength = 0;
}

}  // namespace

void setup() {
  Serial.begin(kSerialBaud);
  Serial.println(F("LABFORGE PIN DISCOVERY; OUTPUTS INACTIVE"));
  Serial.println(F("SELECT A|B, DIR LOW|HIGH, ARM, PULSE 1..5, DISARM"));
}

void loop() {
  if (controller.armed() && millis() - armedAtMs >= kArmTimeoutMs) {
    controller.disarm();
    Serial.println(F("DISARMED TIMEOUT"));
  }
  while (Serial.available() > 0) {
    const char value = static_cast<char>(Serial.read());
    if (value == '\r') continue;
    if (discardingInput) {
      if (value == '\n') discardingInput = false;
      continue;
    }
    if (value == '\n') {
      handleCommand();
    } else if (inputLength + 1 < sizeof(input)) {
      input[inputLength++] = value;
    } else {
      inputLength = 0;
      discardingInput = true;
      controller.disarm();
      Serial.println(F("STATUS INVALID_COMMAND"));
    }
  }
}
