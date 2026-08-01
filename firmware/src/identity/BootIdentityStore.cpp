#include "identity/BootIdentityStore.h"

#include <limits.h>

namespace labforge {
namespace {

constexpr uint8_t kMagic[4] = {'L', 'F', 'B', 'I'};
constexpr uint8_t kFormatVersion = 1;
constexpr uint8_t kCommitMarkerA = 0xA5;
constexpr uint8_t kCommitMarkerB = 0x5A;
constexpr size_t kCrcOffset = 12;
constexpr size_t kCommitAOffset = 14;
constexpr size_t kCommitBOffset = 15;

struct SlotState {
  bool valid;
  bool erased;
  uint32_t id;
};

BootIdentityResult failure(IdentityFailureReason reason) {
  return {false, 0, reason};
}

bool readSlot(const ByteStorage& storage, size_t slot, uint8_t* bytes) {
  const size_t base = slot * kBootIdentitySlotSize;
  for (size_t i = 0; i < kBootIdentitySlotSize; ++i) {
    if (!storage.read(base + i, bytes[i])) return false;
  }
  return true;
}

SlotState classify(const uint8_t* bytes) {
  bool erased = true;
  for (size_t i = 0; i < kBootIdentitySlotSize; ++i) erased = erased && bytes[i] == 0xFF;
  BootIdentityRecord record{};
  const bool valid = decodeBootIdentityRecord(bytes, record);
  return {valid, erased, valid ? record.controllerBootId : 0};
}

BootIdentityResult writeAndVerify(ByteStorage& storage, size_t slot, uint32_t id) {
  uint8_t bytes[kBootIdentitySlotSize]{};
  encodeBootIdentityRecord({id}, bytes);
  const size_t base = slot * kBootIdentitySlotSize;

  if (!storage.write(base + kCommitBOffset, 0x00)) return failure(IdentityFailureReason::WRITE_FAILED);
  for (size_t i = 0; i <= kCrcOffset + 1; ++i) {
    if (!storage.write(base + i, bytes[i])) return failure(IdentityFailureReason::WRITE_FAILED);
  }
  if (!storage.write(base + kCommitAOffset, kCommitMarkerA)) {
    return failure(IdentityFailureReason::WRITE_FAILED);
  }
  if (!storage.write(base + kCommitBOffset, kCommitMarkerB)) {
    return failure(IdentityFailureReason::WRITE_FAILED);
  }

  uint8_t readBack[kBootIdentitySlotSize]{};
  if (!readSlot(storage, slot, readBack)) return failure(IdentityFailureReason::READ_FAILED);
  BootIdentityRecord verified{};
  if (!decodeBootIdentityRecord(readBack, verified) || verified.controllerBootId != id) {
    return failure(IdentityFailureReason::VERIFY_FAILED);
  }
  return {true, id, IdentityFailureReason::NONE};
}

}  // namespace

uint16_t crc16CcittFalse(const uint8_t* data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < length; ++i) {
    crc ^= static_cast<uint16_t>(data[i]) << 8;
    for (uint8_t bit = 0; bit < 8; ++bit) {
      crc = (crc & 0x8000) != 0 ? static_cast<uint16_t>((crc << 1) ^ 0x1021)
                               : static_cast<uint16_t>(crc << 1);
    }
  }
  return crc;
}

void encodeBootIdentityRecord(const BootIdentityRecord& record, uint8_t* encoded) {
  encoded[0] = kMagic[0];
  encoded[1] = kMagic[1];
  encoded[2] = kMagic[2];
  encoded[3] = kMagic[3];
  encoded[4] = kFormatVersion;
  encoded[5] = 0;
  encoded[6] = 0;
  encoded[7] = 0;
  encoded[8] = static_cast<uint8_t>(record.controllerBootId);
  encoded[9] = static_cast<uint8_t>(record.controllerBootId >> 8);
  encoded[10] = static_cast<uint8_t>(record.controllerBootId >> 16);
  encoded[11] = static_cast<uint8_t>(record.controllerBootId >> 24);
  const uint16_t crc = crc16CcittFalse(encoded, 12);
  encoded[12] = static_cast<uint8_t>(crc);
  encoded[13] = static_cast<uint8_t>(crc >> 8);
  encoded[14] = kCommitMarkerA;
  encoded[15] = kCommitMarkerB;
}

bool decodeBootIdentityRecord(const uint8_t* encoded, BootIdentityRecord& record) {
  if (encoded[14] != kCommitMarkerA || encoded[15] != kCommitMarkerB) return false;
  for (size_t i = 0; i < 4; ++i) {
    if (encoded[i] != kMagic[i]) return false;
  }
  if (encoded[4] != kFormatVersion || encoded[5] != 0 || encoded[6] != 0 || encoded[7] != 0) {
    return false;
  }
  const uint16_t storedCrc = static_cast<uint16_t>(encoded[12]) |
                             (static_cast<uint16_t>(encoded[13]) << 8);
  if (storedCrc != crc16CcittFalse(encoded, 12)) return false;
  const uint32_t id = static_cast<uint32_t>(encoded[8]) |
                      (static_cast<uint32_t>(encoded[9]) << 8) |
                      (static_cast<uint32_t>(encoded[10]) << 16) |
                      (static_cast<uint32_t>(encoded[11]) << 24);
  if (id == 0) return false;
  record.controllerBootId = id;
  return true;
}

BootIdentityResult BootIdentityStore::initialize() {
  if (storage_.capacity() < kBootIdentityStorageSize) {
    return failure(IdentityFailureReason::STORAGE_TOO_SMALL);
  }

  uint8_t bytes[2][kBootIdentitySlotSize]{};
  if (!readSlot(storage_, 0, bytes[0]) || !readSlot(storage_, 1, bytes[1])) {
    return failure(IdentityFailureReason::READ_FAILED);
  }
  const SlotState slots[2] = {classify(bytes[0]), classify(bytes[1])};

  if (!slots[0].valid && !slots[1].valid) {
    if (slots[0].erased && slots[1].erased) return writeAndVerify(storage_, 0, 1);
    return failure(IdentityFailureReason::NO_VALID_RECORD);
  }

  size_t newest = 0;
  size_t target = 1;
  if (slots[0].valid && slots[1].valid) {
    if (slots[0].id == slots[1].id) return failure(IdentityFailureReason::AMBIGUOUS_RECORDS);
    newest = slots[0].id > slots[1].id ? 0 : 1;
    target = 1 - newest;
    if (slots[newest].id - slots[target].id != 1) {
      return failure(IdentityFailureReason::AMBIGUOUS_RECORDS);
    }
  } else {
    newest = slots[0].valid ? 0 : 1;
    target = 1 - newest;
  }

  if (slots[newest].id == UINT32_MAX) return failure(IdentityFailureReason::COUNTER_EXHAUSTED);
  return writeAndVerify(storage_, target, slots[newest].id + 1);
}

}  // namespace labforge
