#include <unity.h>

#include <limits.h>
#include <initializer_list>
#include <string.h>

#include "identity/BootIdentityStore.h"

using namespace labforge;

namespace {

class FakeStorage : public ByteStorage {
 public:
  explicit FakeStorage(size_t capacity = kBootIdentityStorageSize) : capacity_(capacity) {
    memset(data, 0xFF, sizeof(data));
  }

  size_t capacity() const override { return capacity_; }
  bool read(size_t address, uint8_t& value) const override {
    if (address >= capacity_ || reads++ == failReadAt) return false;
    value = data[address];
    if (corruptReadBack && writes >= 17 && address == corruptAddress) value ^= 0x01;
    return true;
  }
  bool write(size_t address, uint8_t value) override {
    if (address >= capacity_ || writes++ == failWriteAt) return false;
    data[address] = value;
    return true;
  }

  uint8_t data[kBootIdentityStorageSize];
  size_t capacity_;
  mutable size_t reads = 0;
  size_t writes = 0;
  mutable size_t failReadAt = SIZE_MAX;
  size_t failWriteAt = SIZE_MAX;
  bool corruptReadBack = false;
  size_t corruptAddress = 0;
};

void placeRecord(FakeStorage& storage, size_t slot, uint32_t id) {
  encodeBootIdentityRecord({id}, &storage.data[slot * kBootIdentitySlotSize]);
}

void assertTrusted(const BootIdentityResult& result, uint32_t id) {
  TEST_ASSERT_TRUE(result.trusted);
  TEST_ASSERT_EQUAL_UINT32(id, result.controllerBootId);
  TEST_ASSERT_EQUAL(IdentityFailureReason::NONE, result.reason);
}

void assertUntrusted(const BootIdentityResult& result, IdentityFailureReason reason) {
  TEST_ASSERT_FALSE(result.trusted);
  TEST_ASSERT_EQUAL_UINT32(0, result.controllerBootId);
  TEST_ASSERT_EQUAL(reason, result.reason);
}

void test_crc_known_vector() {
  const uint8_t vector[] = "123456789";
  TEST_ASSERT_EQUAL_HEX16(0x29B1, crc16CcittFalse(vector, 9));
}

void test_encode_decode_round_trip_and_little_endian() {
  uint8_t bytes[kBootIdentitySlotSize]{};
  encodeBootIdentityRecord({0x12345678}, bytes);
  TEST_ASSERT_EQUAL_UINT8('L', bytes[0]);
  TEST_ASSERT_EQUAL_HEX8(0x78, bytes[8]);
  TEST_ASSERT_EQUAL_HEX8(0x12, bytes[11]);
  BootIdentityRecord decoded{};
  TEST_ASSERT_TRUE(decodeBootIdentityRecord(bytes, decoded));
  TEST_ASSERT_EQUAL_HEX32(0x12345678, decoded.controllerBootId);
}

void test_first_and_successive_boots_alternate_slots() {
  FakeStorage storage;
  BootIdentityStore store(storage);
  assertTrusted(store.initialize(), 1);
  TEST_ASSERT_EQUAL_HEX8(0xA5, storage.data[14]);
  assertTrusted(store.initialize(), 2);
  TEST_ASSERT_EQUAL_HEX8(0xA5, storage.data[30]);
  assertTrusted(store.initialize(), 3);
  BootIdentityRecord slot0{}, slot1{};
  TEST_ASSERT_TRUE(decodeBootIdentityRecord(storage.data, slot0));
  TEST_ASSERT_TRUE(decodeBootIdentityRecord(storage.data + 16, slot1));
  TEST_ASSERT_EQUAL_UINT32(3, slot0.controllerBootId);
  TEST_ASSERT_EQUAL_UINT32(2, slot1.controllerBootId);
}

void test_one_valid_slot_plus_invalid_slot() {
  FakeStorage storage;
  placeRecord(storage, 1, 41);
  storage.data[0] = 0;
  assertTrusted(BootIdentityStore(storage).initialize(), 42);
}

void test_both_valid_consecutive_choose_larger() {
  FakeStorage storage;
  placeRecord(storage, 0, 9);
  placeRecord(storage, 1, 10);
  assertTrusted(BootIdentityStore(storage).initialize(), 11);
}

void test_ambiguous_valid_pairs_do_not_write() {
  for (uint32_t second : {7U, 9U}) {
    FakeStorage storage;
    placeRecord(storage, 0, 7);
    placeRecord(storage, 1, second);
    assertUntrusted(BootIdentityStore(storage).initialize(), IdentityFailureReason::AMBIGUOUS_RECORDS);
    TEST_ASSERT_EQUAL_UINT32(0, storage.writes);
  }
}

void test_each_record_validation_rule() {
  for (size_t mutation = 0; mutation < 6; ++mutation) {
    uint8_t bytes[kBootIdentitySlotSize]{};
    encodeBootIdentityRecord({12}, bytes);
    if (mutation == 0) bytes[0] ^= 1;             // magic
    if (mutation == 1) bytes[4] = 2;              // version
    if (mutation == 2) bytes[5] = 1;              // reserved
    if (mutation == 3) bytes[12] ^= 1;             // CRC
    if (mutation == 4) bytes[14] = 0;              // commit markers
    if (mutation == 5) {                           // zero ID with a matching CRC
      encodeBootIdentityRecord({0}, bytes);
    }
    BootIdentityRecord record{};
    TEST_ASSERT_FALSE(decodeBootIdentityRecord(bytes, record));
  }
}

void test_neither_valid_and_not_erased() {
  FakeStorage storage;
  storage.data[3] = 0;
  assertUntrusted(BootIdentityStore(storage).initialize(), IdentityFailureReason::NO_VALID_RECORD);
  TEST_ASSERT_EQUAL_UINT32(0, storage.writes);
}

void test_uint32_max_does_not_wrap() {
  FakeStorage storage;
  placeRecord(storage, 0, UINT32_MAX);
  assertUntrusted(BootIdentityStore(storage).initialize(), IdentityFailureReason::COUNTER_EXHAUSTED);
  TEST_ASSERT_EQUAL_UINT32(0, storage.writes);
}

void test_storage_and_io_failures() {
  FakeStorage small(kBootIdentityStorageSize - 1);
  assertUntrusted(BootIdentityStore(small).initialize(), IdentityFailureReason::STORAGE_TOO_SMALL);

  FakeStorage readFailure;
  readFailure.failReadAt = 5;
  assertUntrusted(BootIdentityStore(readFailure).initialize(), IdentityFailureReason::READ_FAILED);

  FakeStorage writeFailure;
  writeFailure.failWriteAt = 4;
  assertUntrusted(BootIdentityStore(writeFailure).initialize(), IdentityFailureReason::WRITE_FAILED);

  FakeStorage verifyFailure;
  verifyFailure.corruptReadBack = true;
  verifyFailure.corruptAddress = 8;
  assertUntrusted(BootIdentityStore(verifyFailure).initialize(), IdentityFailureReason::VERIFY_FAILED);
}

void test_failure_before_each_write_preserves_and_recovers_previous_record() {
  for (size_t failedWrite = 0; failedWrite < 17; ++failedWrite) {
    FakeStorage storage;
    placeRecord(storage, 0, 20);
    storage.failWriteAt = failedWrite;
    assertUntrusted(BootIdentityStore(storage).initialize(), IdentityFailureReason::WRITE_FAILED);

    BootIdentityRecord previous{};
    TEST_ASSERT_TRUE(decodeBootIdentityRecord(storage.data, previous));
    TEST_ASSERT_EQUAL_UINT32(20, previous.controllerBootId);

    storage.failWriteAt = SIZE_MAX;
    assertTrusted(BootIdentityStore(storage).initialize(), 21);
    TEST_ASSERT_TRUE(decodeBootIdentityRecord(storage.data, previous));
    TEST_ASSERT_EQUAL_UINT32(20, previous.controllerBootId);
  }
}

void test_restart_after_final_commit_advances_consecutive_records() {
  FakeStorage storage;
  placeRecord(storage, 0, 20);

  {
    BootIdentityStore firstBoot(storage);
    assertTrusted(firstBoot.initialize(), 21);
  }

  BootIdentityRecord slot0{};
  BootIdentityRecord slot1{};
  TEST_ASSERT_TRUE(decodeBootIdentityRecord(storage.data, slot0));
  TEST_ASSERT_TRUE(decodeBootIdentityRecord(storage.data + kBootIdentitySlotSize, slot1));
  TEST_ASSERT_EQUAL_UINT32(20, slot0.controllerBootId);
  TEST_ASSERT_EQUAL_UINT32(21, slot1.controllerBootId);

  BootIdentityStore restartedBoot(storage);
  assertTrusted(restartedBoot.initialize(), 22);

  BootIdentityRecord next{};
  TEST_ASSERT_TRUE(decodeBootIdentityRecord(storage.data, next));
  TEST_ASSERT_EQUAL_UINT32(22, next.controllerBootId);
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_crc_known_vector);
  RUN_TEST(test_encode_decode_round_trip_and_little_endian);
  RUN_TEST(test_first_and_successive_boots_alternate_slots);
  RUN_TEST(test_one_valid_slot_plus_invalid_slot);
  RUN_TEST(test_both_valid_consecutive_choose_larger);
  RUN_TEST(test_ambiguous_valid_pairs_do_not_write);
  RUN_TEST(test_each_record_validation_rule);
  RUN_TEST(test_neither_valid_and_not_erased);
  RUN_TEST(test_uint32_max_does_not_wrap);
  RUN_TEST(test_storage_and_io_failures);
  RUN_TEST(test_failure_before_each_write_preserves_and_recovers_previous_record);
  RUN_TEST(test_restart_after_final_commit_advances_consecutive_records);
  return UNITY_END();
}
