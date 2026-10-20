#include <Arduino.h>

// Standalone read-only commissioning firmware, not LABFORGE/1.
// No STEP/DIR configuration, motion commands, or EEPROM access.
void setup() {
  pinMode(2, INPUT_PULLUP);
  pinMode(3, INPUT_PULLUP);
  Serial.begin(115200);
  Serial.println(F("LABFORGE HOME INPUT PROBE; NO MOTION CAPABILITY"));
}

void loop() {
  Serial.print(F("HOME_INPUTS D2="));
  Serial.print(digitalRead(2) == HIGH ? F("HIGH") : F("LOW"));
  Serial.print(F(" D3="));
  Serial.println(digitalRead(3) == HIGH ? F("HIGH") : F("LOW"));
  delay(100);
}
