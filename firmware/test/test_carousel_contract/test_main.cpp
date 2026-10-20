#include <unity.h>

#include <string.h>

#include "protocol/CarouselContract.h"
#include "protocol/CommandStatusCache.h"

using namespace labforge;

namespace {
InboundMessage message(const char* command, int64_t position) {
  InboundMessage value{};
  value.type = MessageType::COMMAND;
  strcpy(value.command, command);
  value.argumentCount = 1;
  strcpy(value.arguments[0].key, "position");
  value.arguments[0].type = ArgumentType::INTEGER;
  value.arguments[0].value.integerValue = position;
  return value;
}

void test_accepts_exact_commands_and_bounds() {
  CarouselCommand parsed{};
  TEST_ASSERT_EQUAL_INT(
      static_cast<int>(CarouselContractStatus::VALID),
      static_cast<int>(parseCarousel(message("CAROUSEL_SET_REFERENCE", 1), parsed)));
  TEST_ASSERT_EQUAL_UINT8(1, parsed.position);
  TEST_ASSERT_EQUAL_INT(
      static_cast<int>(CommandKind::CAROUSEL_SET_REFERENCE),
      static_cast<int>(parsed.kind));
  TEST_ASSERT_EQUAL_INT(
      static_cast<int>(CarouselContractStatus::VALID),
      static_cast<int>(parseCarousel(message("CAROUSEL_MOVE_TO_POSITION", 40), parsed)));
}

void test_rejects_invalid_schema_and_values() {
  CarouselCommand parsed{};
  InboundMessage value = message("CAROUSEL_MOVE_TO_POSITION", 0);
  TEST_ASSERT_EQUAL_INT(static_cast<int>(CarouselContractStatus::INVALID_ARGUMENTS),
                        static_cast<int>(parseCarousel(value, parsed)));
  value = message("CAROUSEL_MOVE_TO_POSITION", 41);
  TEST_ASSERT_EQUAL_INT(static_cast<int>(CarouselContractStatus::INVALID_ARGUMENTS),
                        static_cast<int>(parseCarousel(value, parsed)));
  value = message("CAROUSEL_MOVE_TO_POSITION", 2);
  value.arguments[0].type = ArgumentType::STRING;
  TEST_ASSERT_EQUAL_INT(static_cast<int>(CarouselContractStatus::INVALID_ARGUMENTS),
                        static_cast<int>(parseCarousel(value, parsed)));
  value = message("CAROUSEL_MOVE_TO_POSITION", 2);
  value.argumentCount = 0;
  TEST_ASSERT_EQUAL_INT(static_cast<int>(CarouselContractStatus::INVALID_ARGUMENTS),
                        static_cast<int>(parseCarousel(value, parsed)));
  value = message("CAROUSEL_MOVE_TO_POSITION", 2);
  value.argumentCount = 2;
  TEST_ASSERT_EQUAL_INT(static_cast<int>(CarouselContractStatus::INVALID_ARGUMENTS),
                        static_cast<int>(parseCarousel(value, parsed)));
}

CommandStatusRecord recordWith(const CommandSemanticIdentity& semantic) {
  CommandStatusRecord record{};
  strcpy(record.operationCommandId,
         "323e4567-e89b-12d3-a456-426614174002");
  strcpy(record.phaseExecutionId, "phase-1");
  record.phaseExecutionIdKnown = true;
  record.semanticIdentityKnown = true;
  record.semanticIdentity = semantic;
  record.state = CommandState::ACCEPTED;
  record.errorCode = CommandErrorCode::NONE;
  return record;
}

void test_cache_semantic_identity_uses_exact_position_bounds() {
  CommandStatusCache cache;
  TEST_ASSERT_EQUAL(
      CommandStatusStoreResult::STORED,
      cache.storeDetailed(recordWith(CommandSemanticIdentity(
          CommandKind::CAROUSEL_SET_REFERENCE, PumpId::NONE, 0,
          ValveId::NONE, 0, 1))));

  CommandStatusCache invalidLow;
  TEST_ASSERT_EQUAL(
      CommandStatusStoreResult::INVALID_RECORD,
      invalidLow.storeDetailed(recordWith(CommandSemanticIdentity(
          CommandKind::CAROUSEL_MOVE_TO_POSITION, PumpId::NONE, 0,
          ValveId::NONE, 0, 0))));

  CommandStatusCache invalidHigh;
  TEST_ASSERT_EQUAL(
      CommandStatusStoreResult::INVALID_RECORD,
      invalidHigh.storeDetailed(recordWith(CommandSemanticIdentity(
          CommandKind::CAROUSEL_MOVE_TO_POSITION, PumpId::NONE, 0,
          ValveId::NONE, 0, 41))));
}
}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_accepts_exact_commands_and_bounds);
  RUN_TEST(test_rejects_invalid_schema_and_values);
  RUN_TEST(test_cache_semantic_identity_uses_exact_position_bounds);
  return UNITY_END();
}
