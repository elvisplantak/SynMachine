#pragma once

#include "identity/BootIdentityStore.h"

namespace labforge {

class ArduinoEepromStorage : public ByteStorage {
 public:
  size_t capacity() const override;
  bool read(size_t address, uint8_t& value) const override;
  bool write(size_t address, uint8_t value) override;
};

}  // namespace labforge
