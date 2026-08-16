#include <unity.h>

#include <string.h>

#include "protocol/SfMixerContract.h"

using namespace labforge;

namespace {

InboundMessage message(bool running) {
  InboundMessage value{};
  value.type = MessageType::COMMAND;
  strcpy(value.command, "SF_MIXER_SET_STATE");
  value.argumentCount = 1;
  strcpy(value.arguments[0].key, "running");
  value.arguments[0].type = ArgumentType::BOOLEAN;
  value.arguments[0].value.booleanValue = running;
  return value;
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
  return record;
}

void test_accepts_only_exact_boolean_state() {
  SfMixerCommand parsed{};
  TEST_ASSERT_EQUAL(SfMixerContractStatus::VALID,
                    parseSfMixer(message(true), parsed));
  TEST_ASSERT_TRUE(parsed.running);
  TEST_ASSERT_EQUAL(SfMixerContractStatus::VALID,
                    parseSfMixer(message(false), parsed));
  TEST_ASSERT_FALSE(parsed.running);

  InboundMessage invalid = message(true);
  invalid.arguments[0].type = ArgumentType::INTEGER;
  TEST_ASSERT_EQUAL(SfMixerContractStatus::INVALID_ARGUMENTS,
                    parseSfMixer(invalid, parsed));
  invalid = message(true);
  strcpy(invalid.arguments[0].key, "state");
  TEST_ASSERT_EQUAL(SfMixerContractStatus::INVALID_ARGUMENTS,
                    parseSfMixer(invalid, parsed));
  invalid = message(true);
  invalid.argumentCount = 0;
  TEST_ASSERT_EQUAL(SfMixerContractStatus::INVALID_ARGUMENTS,
                    parseSfMixer(invalid, parsed));
  invalid = message(true);
  invalid.argumentCount = 2;
  TEST_ASSERT_EQUAL(SfMixerContractStatus::INVALID_ARGUMENTS,
                    parseSfMixer(invalid, parsed));
  invalid = message(true);
  strcpy(invalid.command, "REACTOR_MIXER_SET_STATE");
  TEST_ASSERT_EQUAL(SfMixerContractStatus::UNSUPPORTED_COMMAND,
                    parseSfMixer(invalid, parsed));
}

void test_semantic_identity_distinguishes_start_and_stop() {
  const CommandSemanticIdentity start = semanticIdentity(SfMixerCommand{true});
  const CommandSemanticIdentity stop = semanticIdentity(SfMixerCommand{false});
  TEST_ASSERT_EQUAL(CommandKind::SF_MIXER_SET_STATE, start.command);
  TEST_ASSERT_TRUE(start.mixerRunning);
  TEST_ASSERT_FALSE(stop.mixerRunning);
  TEST_ASSERT_FALSE(commandSemanticIdentityEqual(start, stop));

  CommandStatusCache cache;
  TEST_ASSERT_EQUAL(CommandStatusStoreResult::STORED,
                    cache.storeDetailed(recordWith(start)));
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_accepts_only_exact_boolean_state);
  RUN_TEST(test_semantic_identity_distinguishes_start_and_stop);
  return UNITY_END();
}
