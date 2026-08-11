#include <unity.h>

#include <stdio.h>
#include <string.h>

#include "protocol/CommandStatusCache.h"
#include "protocol/CommandStatusWriter.h"
#include "protocol/NoMotionDispatcher.h"

using namespace labforge;

namespace {

constexpr char NONCE[] = "123e4567-e89b-12d3-a456-426614174000";
constexpr char REQUEST_ID[] = "423e4567-e89b-12d3-a456-426614174003";
constexpr char OPERATION_1[] = "323e4567-e89b-12d3-a456-426614174001";
constexpr char OPERATION_2[] = "323e4567-e89b-12d3-a456-426614174002";
constexpr char OPERATION_3[] = "323e4567-e89b-12d3-a456-426614174003";
constexpr BootIdentityResult TRUSTED{true, UINT32_MAX, IdentityFailureReason::NONE};

CommandStatusRecord record(const char* operationId, CommandState state,
                           const char* phase = "phase-1") {
  CommandStatusRecord value{};
  strcpy(value.operationCommandId, operationId);
  strcpy(value.phaseExecutionId, phase);
  value.phaseExecutionIdKnown = true;
  value.state = state;
  value.errorCode = CommandErrorCode::NONE;
  value.executionStarted = false;
  if (state == CommandState::REJECTED || state == CommandState::FAILED) {
    value.errorCode = CommandErrorCode::CONTROLLER_IDENTITY_UNTRUSTED;
  }
  return value;
}

void test_memory_bounds_and_empty_lookup() {
  CommandStatusCache cache;
  printf("COMMAND_STATUS_ENTRY_BYTES=%u COMMAND_STATUS_CACHE_BYTES=%u\n",
         static_cast<unsigned>(sizeof(CommandStatusEntry)),
         static_cast<unsigned>(sizeof(CommandStatusCache)));
  TEST_ASSERT_LESS_OR_EQUAL_UINT32(128, sizeof(CommandStatusEntry));
  TEST_ASSERT_LESS_OR_EQUAL_UINT32(256, sizeof(CommandStatusCache));
  TEST_ASSERT_EQUAL_UINT32(0, cache.occupiedCount());
  TEST_ASSERT_NULL(cache.find(OPERATION_1));
}

void test_two_entries_and_deterministic_terminal_eviction() {
  CommandStatusCache cache;
  TEST_ASSERT_TRUE(cache.store(record(OPERATION_1, CommandState::REJECTED)));
  TEST_ASSERT_TRUE(cache.store(record(OPERATION_2, CommandState::REJECTED)));
  TEST_ASSERT_EQUAL_UINT32(2, cache.occupiedCount());
  TEST_ASSERT_TRUE(cache.store(record(OPERATION_3, CommandState::REJECTED)));
  TEST_ASSERT_NULL(cache.find(OPERATION_1));
  TEST_ASSERT_NOT_NULL(cache.find(OPERATION_2));
  TEST_ASSERT_NOT_NULL(cache.find(OPERATION_3));
}

void test_nonterminal_is_preserved_and_only_one_is_allowed() {
  CommandStatusCache cache;
  TEST_ASSERT_TRUE(cache.store(record(OPERATION_1, CommandState::ACCEPTED)));
  TEST_ASSERT_FALSE(cache.store(record(OPERATION_2, CommandState::ACCEPTED)));
  TEST_ASSERT_TRUE(cache.store(record(OPERATION_2, CommandState::REJECTED)));
  TEST_ASSERT_TRUE(cache.store(record(OPERATION_3, CommandState::REJECTED)));
  TEST_ASSERT_NOT_NULL(cache.find(OPERATION_1));
  TEST_ASSERT_NULL(cache.find(OPERATION_2));
  TEST_ASSERT_NOT_NULL(cache.find(OPERATION_3));

  TEST_ASSERT_TRUE(cache.store(record(OPERATION_1, CommandState::STARTED)));
  TEST_ASSERT_TRUE(cache.store(record(OPERATION_1, CommandState::COMPLETED)));
  TEST_ASSERT_EQUAL(CommandState::COMPLETED,
                    cache.find(OPERATION_1)->record.state);
}

void test_invalid_record_combinations_are_rejected() {
  CommandStatusCache cache;
  CommandStatusRecord invalid = record(OPERATION_1, CommandState::STARTED);
  invalid.errorCode = CommandErrorCode::CONTROLLER_BUSY;
  TEST_ASSERT_FALSE(cache.store(invalid));
  invalid = record(OPERATION_1, CommandState::COMPLETED);
  invalid.executionStarted = true;
  TEST_ASSERT_FALSE(cache.store(invalid));
  invalid = record(OPERATION_1, CommandState::FAILED);
  TEST_ASSERT_FALSE(cache.store(invalid));
  TEST_ASSERT_EQUAL_UINT32(0, cache.occupiedCount());
}

void test_rejection_and_execution_error_categories_do_not_cross() {
  CommandStatusCache cache;
  CommandStatusRecord value = record(OPERATION_1, CommandState::REJECTED);
  value.errorCode = CommandErrorCode::PUMP_MOTION_TIMEOUT;
  TEST_ASSERT_EQUAL(CommandStatusStoreResult::INVALID_RECORD,
                    cache.storeDetailed(value));
  value.errorCode = CommandErrorCode::PUMP_HOME_SWITCH_UNEXPECTED;
  TEST_ASSERT_EQUAL(CommandStatusStoreResult::INVALID_RECORD,
                    cache.storeDetailed(value));
  value.errorCode = CommandErrorCode::PUMP_HOME_SWITCH_STUCK;
  TEST_ASSERT_EQUAL(CommandStatusStoreResult::INVALID_RECORD,
                    cache.storeDetailed(value));
  value.errorCode = CommandErrorCode::COMMAND_ABORTED;
  TEST_ASSERT_EQUAL(CommandStatusStoreResult::INVALID_RECORD,
                    cache.storeDetailed(value));

  value = record(OPERATION_1, CommandState::REJECTED);
  value.errorCode = CommandErrorCode::CONTROLLER_BUSY;
  TEST_ASSERT_EQUAL(CommandStatusStoreResult::STORED,
                    cache.storeDetailed(value));

  CommandStatusCache failedCache;
  value = record(OPERATION_2, CommandState::ACCEPTED);
  value.semanticIdentityKnown = true;
  value.semanticIdentity = {CommandKind::PUMP_MOVE_ABSOLUTE_STEPS, PumpId::P1,
                            5000};
  TEST_ASSERT_TRUE(failedCache.store(value));
  value.state = CommandState::STARTED;
  TEST_ASSERT_TRUE(failedCache.store(value));
  value.state = CommandState::FAILED;
  value.executionStarted = true;
  value.errorCode = CommandErrorCode::CONTROLLER_BUSY;
  TEST_ASSERT_EQUAL(CommandStatusStoreResult::INVALID_RECORD,
                    failedCache.storeDetailed(value));
  value.errorCode = CommandErrorCode::PUMP_MOTION_TIMEOUT;
  TEST_ASSERT_EQUAL(CommandStatusStoreResult::STORED,
                    failedCache.storeDetailed(value));

  CommandStatusCache homeFailedCache;
  value = record(OPERATION_3, CommandState::ACCEPTED);
  value.semanticIdentityKnown = true;
  value.semanticIdentity = {CommandKind::PUMP_HOME, PumpId::P1, 0};
  TEST_ASSERT_TRUE(homeFailedCache.store(value));
  value.state = CommandState::STARTED;
  TEST_ASSERT_TRUE(homeFailedCache.store(value));
  value.state = CommandState::FAILED;
  value.executionStarted = true;
  value.errorCode = CommandErrorCode::PUMP_HOME_SWITCH_STUCK;
  TEST_ASSERT_EQUAL(CommandStatusStoreResult::STORED,
                    homeFailedCache.storeDetailed(value));

  uint8_t output[kCommandStatusFrameCapacity]{};
  size_t length = 0;
  TEST_ASSERT_TRUE(writeCommandStatus(
      NONCE, REQUEST_ID, OPERATION_3, TRUSTED,
      homeFailedCache.find(OPERATION_3), output, sizeof(output), length));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"error_code\":\"PUMP_HOME_SWITCH_STUCK\""));
}

void test_semantic_identity_rejects_absolute_zero_but_accepts_home_zero() {
  CommandStatusCache moveCache;
  CommandStatusRecord value = record(OPERATION_1, CommandState::ACCEPTED);
  value.semanticIdentityKnown = true;
  value.semanticIdentity = {CommandKind::PUMP_MOVE_ABSOLUTE_STEPS, PumpId::P1,
                            0};
  TEST_ASSERT_EQUAL(CommandStatusStoreResult::INVALID_RECORD,
                    moveCache.storeDetailed(value));
  TEST_ASSERT_EQUAL_UINT32(0, moveCache.occupiedCount());

  CommandStatusCache homeCache;
  value.semanticIdentity = {CommandKind::PUMP_HOME, PumpId::P1, 0};
  TEST_ASSERT_EQUAL(CommandStatusStoreResult::STORED,
                    homeCache.storeDetailed(value));

  CommandStatusCache positiveMoveCache;
  value.semanticIdentity = {CommandKind::PUMP_MOVE_ABSOLUTE_STEPS, PumpId::P1,
                            1};
  TEST_ASSERT_EQUAL(CommandStatusStoreResult::STORED,
                    positiveMoveCache.storeDetailed(value));
}

void test_semantic_identity_accepts_p2_and_detects_pump_change() {
  CommandStatusCache cache;
  CommandStatusRecord value = record(OPERATION_1, CommandState::ACCEPTED);
  value.semanticIdentityKnown = true;
  value.semanticIdentity = {CommandKind::PUMP_MOVE_ABSOLUTE_STEPS, PumpId::P2,
                            5000};
  TEST_ASSERT_EQUAL(CommandStatusStoreResult::STORED,
                    cache.storeDetailed(value));

  value.semanticIdentity.pump = PumpId::P1;
  TEST_ASSERT_EQUAL(CommandStatusStoreResult::IDENTITY_CONFLICT,
                    cache.storeDetailed(value));

  CommandStatusCache homeCache;
  value.semanticIdentity = {CommandKind::PUMP_HOME, PumpId::P2, 0};
  TEST_ASSERT_EQUAL(CommandStatusStoreResult::STORED,
                    homeCache.storeDetailed(value));
}

void test_started_abort_is_precise_cached_execution_failure() {
  CommandStatusCache cache;
  CommandStatusRecord value = record(OPERATION_1, CommandState::ACCEPTED);
  value.semanticIdentityKnown = true;
  value.semanticIdentity = {CommandKind::PUMP_HOME, PumpId::P1, 0};
  TEST_ASSERT_TRUE(cache.store(value));
  value.state = CommandState::STARTED;
  TEST_ASSERT_TRUE(cache.store(value));
  value.state = CommandState::FAILED;
  value.errorCode = CommandErrorCode::COMMAND_ABORTED;
  value.executionStarted = true;
  TEST_ASSERT_TRUE(cache.store(value));
  TEST_ASSERT_EQUAL(CommandErrorCategory::EXECUTION_FAILURE,
                    commandErrorCategory(value.errorCode));

  uint8_t output[kCommandStatusFrameCapacity]{};
  size_t length = 0;
  TEST_ASSERT_TRUE(writeCommandStatus(
      NONCE, REQUEST_ID, OPERATION_1, TRUSTED, cache.find(OPERATION_1), output,
      sizeof(output), length));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"command_state\":\"FAILED\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"error_code\":\"COMMAND_ABORTED\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"execution_started\":true"));
}

void test_exact_unknown_and_completed_frames() {
  uint8_t output[kCommandStatusFrameCapacity]{};
  size_t length = 0;
  TEST_ASSERT_TRUE(writeCommandStatus(NONCE, REQUEST_ID, OPERATION_1, TRUSTED,
                                      nullptr, output, sizeof(output), length));
  TEST_ASSERT_EQUAL_STRING(
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND_STATUS\",\"backend_session_nonce\":\"123e4567-e89b-12d3-a456-426614174000\",\"controller_boot_id\":4294967295,\"request_id\":\"423e4567-e89b-12d3-a456-426614174003\",\"operation_command_id\":\"323e4567-e89b-12d3-a456-426614174001\",\"command_state\":\"UNKNOWN\"}\n",
      reinterpret_cast<char*>(output));

  CommandStatusCache cache;
  TEST_ASSERT_TRUE(cache.store(record(OPERATION_1, CommandState::ACCEPTED)));
  TEST_ASSERT_TRUE(cache.store(record(OPERATION_1, CommandState::STARTED)));
  TEST_ASSERT_TRUE(cache.store(record(OPERATION_1, CommandState::COMPLETED)));
  memset(output, 0, sizeof(output));
  TEST_ASSERT_TRUE(writeCommandStatus(
      NONCE, REQUEST_ID, OPERATION_1, TRUSTED, cache.find(OPERATION_1),
      output, sizeof(output), length));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"phase_execution_id\":\"phase-1\""));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"command_state\":\"COMPLETED\",\"result\":{}"));
}

void test_all_states_maximum_frame_and_transactional_failure() {
  char maximumPhase[kPhaseExecutionIdCapacity];
  memset(maximumPhase, 'p', sizeof(maximumPhase) - 1);
  maximumPhase[sizeof(maximumPhase) - 1] = '\0';
  const CommandState states[] = {
      CommandState::REJECTED, CommandState::ACCEPTED, CommandState::STARTED,
      CommandState::COMPLETED, CommandState::FAILED,
  };
  uint8_t output[kCommandStatusFrameCapacity];
  size_t maximumLength = 0;
  for (CommandState state : states) {
    CommandStatusRecord value = record(OPERATION_1, state, maximumPhase);
    value.executionStarted = state == CommandState::FAILED;
    CommandStatusEntry entry{};
    entry.occupied = true;
    entry.record = value;
    size_t length = 0;
    TEST_ASSERT_TRUE(writeCommandStatus(
        NONCE, REQUEST_ID, OPERATION_1, TRUSTED, &entry,
        output, sizeof(output), length));
    TEST_ASSERT_EQUAL_UINT8('\n', output[length - 1]);
    if (length > maximumLength) maximumLength = length;
  }
  CommandStatusRecord failedBeforeStart =
      record(OPERATION_1, CommandState::FAILED, maximumPhase);
  failedBeforeStart.executionStarted = false;
  CommandStatusEntry failedEntry{};
  failedEntry.occupied = true;
  failedEntry.record = failedBeforeStart;
  size_t failedLength = 0;
  TEST_ASSERT_TRUE(writeCommandStatus(
      NONCE, REQUEST_ID, OPERATION_1, TRUSTED, &failedEntry,
      output, sizeof(output), failedLength));
  if (failedLength > maximumLength) maximumLength = failedLength;
  printf("MAX_COMMAND_STATUS_FRAME_BYTES=%u\n",
         static_cast<unsigned>(maximumLength));
  TEST_ASSERT_LESS_THAN_UINT32(kCommandStatusFrameCapacity, maximumLength);

  memset(output, 0xA7, sizeof(output));
  size_t length = 123;
  TEST_ASSERT_FALSE(writeCommandStatus(
      NONCE, REQUEST_ID, OPERATION_1, TRUSTED, &failedEntry,
      output, maximumLength - 1, length));
  TEST_ASSERT_EQUAL_UINT32(0, length);
  for (size_t i = 0; i < sizeof(output); ++i) {
    TEST_ASSERT_EQUAL_UINT8(0xA7, output[i]);
  }
}

void test_normative_transition_model_and_idempotent_replay() {
  TEST_ASSERT_TRUE(commandLifecycleTransitionAllowed(
      CommandState::ACCEPTED, CommandState::STARTED, false));
  TEST_ASSERT_TRUE(commandLifecycleTransitionAllowed(
      CommandState::ACCEPTED, CommandState::FAILED, false));
  TEST_ASSERT_TRUE(commandLifecycleTransitionAllowed(
      CommandState::STARTED, CommandState::COMPLETED, false));
  TEST_ASSERT_TRUE(commandLifecycleTransitionAllowed(
      CommandState::STARTED, CommandState::FAILED, true));
  TEST_ASSERT_FALSE(commandLifecycleTransitionAllowed(
      CommandState::STARTED, CommandState::ACCEPTED, false));
  TEST_ASSERT_FALSE(commandLifecycleTransitionAllowed(
      CommandState::ACCEPTED, CommandState::COMPLETED, false));

  CommandStatusCache failedBeforeStartCache;
  TEST_ASSERT_TRUE(failedBeforeStartCache.store(
      record(OPERATION_2, CommandState::ACCEPTED)));
  CommandStatusEntry failedBeforeStartOriginal =
      *failedBeforeStartCache.find(OPERATION_2);
  CommandStatusRecord failedBeforeStart =
      record(OPERATION_2, CommandState::FAILED);
  failedBeforeStart.executionStarted = false;
  TEST_ASSERT_FALSE(failedBeforeStartCache.store(failedBeforeStart));
  TEST_ASSERT_EQUAL_MEMORY(&failedBeforeStartOriginal,
                           failedBeforeStartCache.find(OPERATION_2),
                           sizeof(failedBeforeStartOriginal));

  CommandStatusCache failedAfterStartCache;
  TEST_ASSERT_TRUE(failedAfterStartCache.store(
      record(OPERATION_3, CommandState::ACCEPTED)));
  TEST_ASSERT_TRUE(failedAfterStartCache.store(
      record(OPERATION_3, CommandState::STARTED)));
  CommandStatusEntry failedAfterStartOriginal =
      *failedAfterStartCache.find(OPERATION_3);
  CommandStatusRecord failedAfterStart =
      record(OPERATION_3, CommandState::FAILED);
  failedAfterStart.executionStarted = true;
  TEST_ASSERT_FALSE(failedAfterStartCache.store(failedAfterStart));
  TEST_ASSERT_EQUAL_MEMORY(&failedAfterStartOriginal,
                           failedAfterStartCache.find(OPERATION_3),
                           sizeof(failedAfterStartOriginal));

  CommandStatusCache cache;
  CommandStatusRecord accepted = record(OPERATION_1, CommandState::ACCEPTED);
  TEST_ASSERT_TRUE(cache.store(accepted));
  const uint32_t sequence = cache.find(OPERATION_1)->insertionSequence;
  TEST_ASSERT_TRUE(cache.store(accepted));
  TEST_ASSERT_EQUAL_UINT32(sequence,
                           cache.find(OPERATION_1)->insertionSequence);
  TEST_ASSERT_TRUE(cache.store(record(OPERATION_1, CommandState::STARTED)));
  CommandStatusRecord started = record(OPERATION_1, CommandState::STARTED);
  TEST_ASSERT_TRUE(cache.store(started));
  TEST_ASSERT_EQUAL_UINT32(sequence,
                           cache.find(OPERATION_1)->insertionSequence);
  TEST_ASSERT_TRUE(cache.store(record(OPERATION_1, CommandState::COMPLETED)));
  CommandStatusRecord completed =
      record(OPERATION_1, CommandState::COMPLETED);
  TEST_ASSERT_TRUE(cache.store(completed));
  TEST_ASSERT_EQUAL_UINT32(sequence,
                           cache.find(OPERATION_1)->insertionSequence);
}

void test_regressions_terminal_changes_and_phase_mutation_are_rejected() {
  CommandStatusCache cache;
  TEST_ASSERT_TRUE(cache.store(record(OPERATION_1, CommandState::ACCEPTED)));
  TEST_ASSERT_TRUE(cache.store(record(OPERATION_1, CommandState::STARTED)));
  CommandStatusEntry before = *cache.find(OPERATION_1);
  TEST_ASSERT_FALSE(cache.store(record(OPERATION_1, CommandState::ACCEPTED)));
  TEST_ASSERT_EQUAL_MEMORY(&before, cache.find(OPERATION_1), sizeof(before));
  CommandStatusRecord changedPhase =
      record(OPERATION_1, CommandState::COMPLETED, "different-phase");
  TEST_ASSERT_FALSE(cache.store(changedPhase));
  TEST_ASSERT_EQUAL_MEMORY(&before, cache.find(OPERATION_1), sizeof(before));
  TEST_ASSERT_TRUE(cache.store(record(OPERATION_1, CommandState::COMPLETED)));
  before = *cache.find(OPERATION_1);
  TEST_ASSERT_FALSE(cache.store(record(OPERATION_1, CommandState::STARTED)));
  TEST_ASSERT_FALSE(cache.store(record(OPERATION_1, CommandState::FAILED)));
  TEST_ASSERT_EQUAL_MEMORY(&before, cache.find(OPERATION_1), sizeof(before));

  CommandStatusCache rejectedCache;
  TEST_ASSERT_TRUE(
      rejectedCache.store(record(OPERATION_2, CommandState::REJECTED)));
  before = *rejectedCache.find(OPERATION_2);
  TEST_ASSERT_FALSE(
      rejectedCache.store(record(OPERATION_2, CommandState::ACCEPTED)));
  TEST_ASSERT_EQUAL_MEMORY(&before, rejectedCache.find(OPERATION_2),
                           sizeof(before));

  CommandStatusCache directCompletion;
  TEST_ASSERT_TRUE(directCompletion.store(
      record(OPERATION_3, CommandState::ACCEPTED)));
  before = *directCompletion.find(OPERATION_3);
  TEST_ASSERT_FALSE(directCompletion.store(
      record(OPERATION_3, CommandState::COMPLETED)));
  TEST_ASSERT_EQUAL_MEMORY(&before, directCompletion.find(OPERATION_3),
                           sizeof(before));
}

void test_invalid_identifiers_and_enum_values_do_not_mutate_cache() {
  CommandStatusCache cache;
  CommandStatusRecord invalid = record(OPERATION_1, CommandState::ACCEPTED);
  strcpy(invalid.operationCommandId, "gggggggg-gggg-gggg-gggg-gggggggggggg");
  TEST_ASSERT_FALSE(cache.store(invalid));
  invalid = record(OPERATION_1, CommandState::ACCEPTED);
  invalid.operationCommandId[0] = 'A';
  TEST_ASSERT_FALSE(cache.store(invalid));
  invalid = record(OPERATION_1, CommandState::ACCEPTED, "bad\"phase");
  TEST_ASSERT_FALSE(cache.store(invalid));
  invalid = record(OPERATION_1, CommandState::ACCEPTED, "bad phase");
  TEST_ASSERT_FALSE(cache.store(invalid));
  invalid = record(OPERATION_1, CommandState::ACCEPTED);
  memset(invalid.operationCommandId, 'a', sizeof(invalid.operationCommandId));
  TEST_ASSERT_FALSE(cache.store(invalid));
  invalid = record(OPERATION_1, CommandState::ACCEPTED);
  memset(invalid.phaseExecutionId, 'p', sizeof(invalid.phaseExecutionId));
  TEST_ASSERT_FALSE(cache.store(invalid));
  invalid = record(OPERATION_1, CommandState::ACCEPTED);
  invalid.state = static_cast<CommandState>(255);
  TEST_ASSERT_FALSE(cache.store(invalid));
  invalid = record(OPERATION_1, CommandState::ACCEPTED);
  invalid.errorCode = static_cast<CommandErrorCode>(255);
  TEST_ASSERT_FALSE(cache.store(invalid));
  TEST_ASSERT_EQUAL_UINT32(0, cache.occupiedCount());
}

void test_dispatch_query_is_read_only_and_survives_session_replacement() {
  NoMotionDispatcher dispatcher;
  SessionState session;
  CommandStatusCache cache;
  TEST_ASSERT_TRUE(cache.store(record(OPERATION_1, CommandState::ACCEPTED)));
  TEST_ASSERT_TRUE(cache.store(record(OPERATION_1, CommandState::STARTED)));
  session.establish(NONCE);
  char query[300];
  snprintf(query, sizeof(query),
           "{\"protocol\":\"LABFORGE/1\",\"type\":\"QUERY_COMMAND\","
           "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":4294967295,"
           "\"request_id\":\"%s\",\"operation_command_id\":\"%s\"}",
           NONCE, REQUEST_ID, OPERATION_1);
  uint8_t output[kCommandStatusFrameCapacity]{};
  const DispatchResult result = dispatcher.dispatch(
      reinterpret_cast<const uint8_t*>(query), strlen(query), TRUSTED,
      session, cache, output, sizeof(output));
  TEST_ASSERT_GREATER_THAN_UINT32(0, result.outputLength);
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"command_state\":\"STARTED\""));
  TEST_ASSERT_EQUAL_UINT32(1, cache.occupiedCount());

  session.establish("223e4567-e89b-12d3-a456-426614174000");
  TEST_ASSERT_NOT_NULL(cache.find(OPERATION_1));
}

void test_untrusted_session_can_query_unknown_without_cache_mutation() {
  NoMotionDispatcher dispatcher;
  SessionState session;
  CommandStatusCache cache;
  session.establish(NONCE);
  const BootIdentityResult untrusted{
      false, 0, IdentityFailureReason::VERIFY_FAILED};
  char query[300];
  snprintf(query, sizeof(query),
           "{\"protocol\":\"LABFORGE/1\",\"type\":\"QUERY_COMMAND\","
           "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":null,"
           "\"request_id\":\"%s\",\"operation_command_id\":\"%s\"}",
           NONCE, REQUEST_ID, OPERATION_1);
  uint8_t output[kCommandStatusFrameCapacity]{};
  const DispatchResult result = dispatcher.dispatch(
      reinterpret_cast<const uint8_t*>(query), strlen(query), untrusted,
      session, cache, output, sizeof(output));
  TEST_ASSERT_GREATER_THAN_UINT32(0, result.outputLength);
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"controller_boot_id\":null"));
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<char*>(output),
                              "\"command_state\":\"UNKNOWN\""));
  TEST_ASSERT_EQUAL_UINT32(0, cache.occupiedCount());
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_memory_bounds_and_empty_lookup);
  RUN_TEST(test_two_entries_and_deterministic_terminal_eviction);
  RUN_TEST(test_nonterminal_is_preserved_and_only_one_is_allowed);
  RUN_TEST(test_invalid_record_combinations_are_rejected);
  RUN_TEST(test_rejection_and_execution_error_categories_do_not_cross);
  RUN_TEST(test_semantic_identity_rejects_absolute_zero_but_accepts_home_zero);
  RUN_TEST(test_semantic_identity_accepts_p2_and_detects_pump_change);
  RUN_TEST(test_started_abort_is_precise_cached_execution_failure);
  RUN_TEST(test_exact_unknown_and_completed_frames);
  RUN_TEST(test_all_states_maximum_frame_and_transactional_failure);
  RUN_TEST(test_normative_transition_model_and_idempotent_replay);
  RUN_TEST(test_regressions_terminal_changes_and_phase_mutation_are_rejected);
  RUN_TEST(test_invalid_identifiers_and_enum_values_do_not_mutate_cache);
  RUN_TEST(test_dispatch_query_is_read_only_and_survives_session_replacement);
  RUN_TEST(test_untrusted_session_can_query_unknown_without_cache_mutation);
  return UNITY_END();
}
