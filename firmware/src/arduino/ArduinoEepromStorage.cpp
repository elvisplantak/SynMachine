#include "identity/ArduinoEepromStorage.h"

#include <EEPROM.h>

namespace labforge {

size_t ArduinoEepromStorage::capacity() const {
  return static_cast<size_t>(EEPROM.length());
}

bool ArduinoEepromStorage::read(size_t address, uint8_t& value) const {
  if (address >= capacity()) return false;
  value = EEPROM.read(static_cast<int>(address));
  return true;
}

bool ArduinoEepromStorage::write(size_t address, uint8_t value) {
  if (address >= capacity()) return false;
  EEPROM.update(static_cast<int>(address), value);
  // EEPROM.update() has no physical-write status; BootIdentityStore establishes
  // trust only after its complete slot read-back validation succeeds.
  return true;
}

}  // namespace labforge
