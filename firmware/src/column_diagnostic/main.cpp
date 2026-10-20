#include <Arduino.h>

#include <string.h>

namespace {

constexpr unsigned long kSerialBaud = 115200;
constexpr uint8_t kHomePin = 10;
constexpr uint8_t kStepPin = 12;
constexpr uint8_t kDirectionPin = 13;
constexpr bool kAwayFromHomeHigh = true;
constexpr uint16_t kClosedPulses = 889;
constexpr uint16_t kClosedToOpenPulses = 20000;
constexpr uint16_t kOpenNudgePulses = 500;
constexpr uint16_t kFineOpenNudgePulses = 100;
constexpr uint16_t kHomeNudgePulses = 250;
constexpr uint16_t kStepHighUs = 20;
constexpr uint16_t kStepIntervalUs = 1000;
constexpr unsigned long kArmTimeoutMs = 10000;
constexpr size_t kInputCapacity = 24;

char input[kInputCapacity];
size_t inputLength = 0;
bool discardingInput = false;
bool armed = false;
unsigned long armedAtMs = 0;

void releaseOutputs() {
  digitalWrite(kStepPin, LOW);
  digitalWrite(kDirectionPin, LOW);
  pinMode(kStepPin, INPUT);
  pinMode(kDirectionPin, INPUT);
}

void printHome() {
  Serial.print(F("STATUS HOME "));
  Serial.println(digitalRead(kHomePin) == HIGH ? F("HIGH") : F("LOW"));
}

void move(uint16_t pulses, bool directionHigh,
          const __FlashStringHelper* label) {
  armed = false;
  pinMode(kDirectionPin, OUTPUT);
  digitalWrite(kDirectionPin, directionHigh ? HIGH : LOW);
  delayMicroseconds(5);
  pinMode(kStepPin, OUTPUT);
  digitalWrite(kStepPin, LOW);
  for (uint16_t pulse = 0; pulse < pulses; ++pulse) {
    digitalWrite(kStepPin, HIGH);
    delayMicroseconds(kStepHighUs);
    digitalWrite(kStepPin, LOW);
    delayMicroseconds(kStepIntervalUs - kStepHighUs);
  }
  releaseOutputs();
  Serial.print(F("STATUS "));
  Serial.print(label);
  Serial.print(F(" COMPLETE PULSES "));
  Serial.println(pulses);
  printHome();
}

void handleCommand() {
  input[inputLength] = '\0';
  if (strcmp(input, "STATUS") == 0) {
    armed = false;
    printHome();
  } else if (strcmp(input, "ARM") == 0) {
    armed = true;
    armedAtMs = millis();
    Serial.println(
        F("STATUS ARMED MOVE_CLOSED|MOVE_OPEN|NUDGE_OPEN_500|"
          "NUDGE_OPEN_100|NUDGE_HOME_250; EXPIRES 10S"));
  } else if (strcmp(input, "DISARM") == 0) {
    armed = false;
    Serial.println(F("STATUS DISARMED"));
  } else if (strcmp(input, "MOVE_CLOSED") == 0) {
    if (!armed) {
      Serial.println(F("STATUS NOT_ARMED"));
    } else {
      move(kClosedPulses, kAwayFromHomeHigh, F("MOVE_CLOSED"));
    }
  } else if (strcmp(input, "MOVE_OPEN") == 0) {
    if (!armed) {
      Serial.println(F("STATUS NOT_ARMED"));
    } else {
      move(kClosedToOpenPulses, kAwayFromHomeHigh, F("MOVE_OPEN"));
    }
  } else if (strcmp(input, "NUDGE_OPEN_500") == 0) {
    if (!armed) {
      Serial.println(F("STATUS NOT_ARMED"));
    } else {
      move(kOpenNudgePulses, kAwayFromHomeHigh, F("NUDGE_OPEN_500"));
    }
  } else if (strcmp(input, "NUDGE_HOME_250") == 0) {
    if (!armed) {
      Serial.println(F("STATUS NOT_ARMED"));
    } else {
      move(kHomeNudgePulses, !kAwayFromHomeHigh, F("NUDGE_HOME_250"));
    }
  } else if (strcmp(input, "NUDGE_OPEN_100") == 0) {
    if (!armed) {
      Serial.println(F("STATUS NOT_ARMED"));
    } else {
      move(kFineOpenNudgePulses, kAwayFromHomeHigh, F("NUDGE_OPEN_100"));
    }
  } else {
    armed = false;
    Serial.println(F("STATUS INVALID_COMMAND"));
  }
  inputLength = 0;
}

}  // namespace

void setup() {
  releaseOutputs();
  pinMode(kHomePin, INPUT_PULLUP);
  Serial.begin(kSerialBaud);
  Serial.println(F("LABFORGE COLUMN DIAGNOSTIC; OUTPUTS INACTIVE"));
  Serial.println(
      F("STATUS, ARM, MOVE_CLOSED, MOVE_OPEN, NUDGE_OPEN_500, "
        "NUDGE_OPEN_100, NUDGE_HOME_250, DISARM"));
  printHome();
}

void loop() {
  if (armed && millis() - armedAtMs >= kArmTimeoutMs) {
    armed = false;
    Serial.println(F("STATUS DISARMED TIMEOUT"));
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
      armed = false;
      Serial.println(F("STATUS INVALID_COMMAND"));
    }
  }
}
