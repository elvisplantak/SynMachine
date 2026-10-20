#pragma once

#include <stddef.h>
#include <stdint.h>

namespace labforge {

constexpr size_t kBootIdentitySlotSize = 16;
constexpr size_t kBootIdentitySlotCount = 2;
constexpr size_t kBootIdentityStorageSize = kBootIdentitySlotSize * kBootIdentitySlotCount;

class ByteStorage {
 public:
  virtual ~ByteStorage() {}
  virtual size_t capacity() const = 0;
  virtual bool read(size_t address, uint8_t& value) const = 0;
  virtual bool write(size_t address, uint8_t value) = 0;
};

struct BootIdentityRecord {
  uint32_t controllerBootId;
};

enum class IdentityFailureReason : uint8_t {
  NONE,
  STORAGE_TOO_SMALL,
  READ_FAILED,
  WRITE_FAILED,
  VERIFY_FAILED,
  NO_VALID_RECORD,
  AMBIGUOUS_RECORDS,
  COUNTER_EXHAUSTED,
};

struct BootIdentityResult {
  bool trusted;
  uint32_t controllerBootId;
  IdentityFailureReason reason;
};

uint16_t crc16CcittFalse(const uint8_t* data, size_t length);
void encodeBootIdentityRecord(const BootIdentityRecord& record,
                              uint8_t encoded[kBootIdentitySlotSize]);
bool decodeBootIdentityRecord(const uint8_t encoded[kBootIdentitySlotSize],
                              BootIdentityRecord& record);

class BootIdentityStore {
 public:
  explicit BootIdentityStore(ByteStorage& storage) : storage_(storage) {}
  BootIdentityResult initialize();

 private:
  ByteStorage& storage_;
};

}  // namespace labforge
