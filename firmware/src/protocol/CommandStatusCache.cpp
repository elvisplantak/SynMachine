#include "protocol/CommandStatusCache.h"

#include <limits.h>
#include <string.h>

namespace labforge {
namespace {

bool validUuid(const char* value) {
  if (value[36] != '\0') return false;
  for (size_t i = 0; i < 36; ++i) {
    if (i == 8 || i == 13 || i == 18 || i == 23) {
      if (value[i] != '-') return false;
    } else if (!((value[i] >= '0' && value[i] <= '9') ||
                 (value[i] >= 'a' && value[i] <= 'f'))) {
      return false;
    }
  }
  return true;
}

bool validPhaseId(const char* value) {
  const char* end = static_cast<const char*>(
      memchr(value, '\0', kPhaseExecutionIdCapacity));
  if (end == nullptr || end == value) return false;
  for (const char* cursor = value; cursor != end; ++cursor) {
    const char c = *cursor;
    if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
          (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.' ||
          c == ':')) {
      return false;
    }
  }
  return true;
}

bool validState(CommandState state) {
  return state == CommandState::REJECTED || state == CommandState::ACCEPTED ||
         state == CommandState::STARTED || state == CommandState::COMPLETED ||
         state == CommandState::FAILED;
}

bool validError(CommandErrorCode error) {
  return error == CommandErrorCode::NONE ||
         error == CommandErrorCode::INVALID_FIELD ||
         error == CommandErrorCode::UNSUPPORTED_COMMAND ||
         error == CommandErrorCode::COMMAND_ID_CONFLICT ||
         error == CommandErrorCode::CONTROLLER_BUSY ||
         error == CommandErrorCode::CONTROLLER_IDENTITY_UNTRUSTED ||
         error == CommandErrorCode::PUMP_MOTION_TIMEOUT ||
         error == CommandErrorCode::PUMP_HOME_SWITCH_UNEXPECTED ||
         error == CommandErrorCode::PUMP_HOME_SWITCH_STUCK ||
         error == CommandErrorCode::VALVE_MOTION_TIMEOUT ||
         error == CommandErrorCode::VALVE_HOME_SWITCH_UNEXPECTED ||
         error == CommandErrorCode::VALVE_HOME_SWITCH_STUCK ||
         error == CommandErrorCode::COLUMN_VALVE_MOTION_TIMEOUT ||
         error == CommandErrorCode::COLUMN_VALVE_HOME_SWITCH_UNEXPECTED ||
         error == CommandErrorCode::COLUMN_VALVE_HOME_SWITCH_STUCK ||
         error == CommandErrorCode::COMMAND_ABORTED;
}

bool validSemanticIdentity(const CommandSemanticIdentity& identity) {
  if (identity.command == CommandKind::PUMP_HOME)
    return (identity.pump == PumpId::P1 || identity.pump == PumpId::P2) &&
           identity.targetSteps == 0 && identity.valve == ValveId::NONE &&
           identity.targetDegrees == 0;
  if (identity.command == CommandKind::PUMP_MOVE_ABSOLUTE_STEPS)
    return (identity.pump == PumpId::P1 || identity.pump == PumpId::P2) &&
           identity.targetSteps >= 1 &&
           identity.targetSteps <= kP1MaximumAbsoluteSteps &&
           identity.valve == ValveId::NONE && identity.targetDegrees == 0;
  const bool validValve = identity.valve >= ValveId::V1 &&
                          identity.valve <= ValveId::V8;
  if (identity.command == CommandKind::VALVE_HOME)
    return identity.pump == PumpId::NONE && identity.targetSteps == 0 &&
           validValve && identity.targetDegrees == 0;
  if (identity.command == CommandKind::VALVE_SET_POSITION)
    return identity.pump == PumpId::NONE && identity.targetSteps == 0 &&
           validValve && (identity.targetDegrees == 0 ||
                          identity.targetDegrees == 90 ||
                          identity.targetDegrees == 180);
  if (identity.command == CommandKind::COLUMN_BOTTOM_VALVE_HOME)
    return identity.pump == PumpId::NONE && identity.targetSteps == 0 &&
           identity.valve == ValveId::NONE && identity.targetDegrees == 0;
  return identity.command ==
             CommandKind::COLUMN_BOTTOM_VALVE_SET_POSITION &&
         identity.pump == PumpId::NONE && identity.targetSteps == 0 &&
         identity.valve == ValveId::NONE &&
         (identity.targetDegrees == 4 || identity.targetDegrees == 94);
}

}  // namespace

CommandErrorCategory commandErrorCategory(CommandErrorCode error) {
  if (error == CommandErrorCode::NONE) return CommandErrorCategory::NONE;
  if (error == CommandErrorCode::INVALID_FIELD ||
      error == CommandErrorCode::UNSUPPORTED_COMMAND ||
      error == CommandErrorCode::COMMAND_ID_CONFLICT ||
      error == CommandErrorCode::CONTROLLER_BUSY ||
      error == CommandErrorCode::CONTROLLER_IDENTITY_UNTRUSTED) {
    return CommandErrorCategory::REQUEST_REJECTION;
  }
  if (error == CommandErrorCode::PUMP_MOTION_TIMEOUT ||
      error == CommandErrorCode::PUMP_HOME_SWITCH_UNEXPECTED ||
      error == CommandErrorCode::PUMP_HOME_SWITCH_STUCK ||
      error == CommandErrorCode::VALVE_MOTION_TIMEOUT ||
      error == CommandErrorCode::VALVE_HOME_SWITCH_UNEXPECTED ||
      error == CommandErrorCode::VALVE_HOME_SWITCH_STUCK ||
      error == CommandErrorCode::COLUMN_VALVE_MOTION_TIMEOUT ||
      error == CommandErrorCode::COLUMN_VALVE_HOME_SWITCH_UNEXPECTED ||
      error == CommandErrorCode::COLUMN_VALVE_HOME_SWITCH_STUCK ||
      error == CommandErrorCode::COMMAND_ABORTED) {
    return CommandErrorCategory::EXECUTION_FAILURE;
  }
  return CommandErrorCategory::INVALID;
}

bool commandSemanticIdentityEqual(const CommandSemanticIdentity& left,
                                  const CommandSemanticIdentity& right) {
  return left.command == right.command && left.pump == right.pump &&
         left.targetSteps == right.targetSteps && left.valve == right.valve &&
         left.targetDegrees == right.targetDegrees;
}

bool commandLifecycleTransitionAllowed(CommandState from, CommandState to,
                                       bool executionStarted) {
  if (from == CommandState::ACCEPTED && to == CommandState::STARTED)
    return !executionStarted;
  if (from == CommandState::ACCEPTED && to == CommandState::FAILED)
    return !executionStarted;
  if (from == CommandState::STARTED && to == CommandState::COMPLETED)
    return !executionStarted;
  if (from == CommandState::STARTED && to == CommandState::FAILED)
    return executionStarted;
  return false;
}

bool CommandStatusCache::terminal(CommandState state) {
  return state == CommandState::REJECTED || state == CommandState::COMPLETED ||
         state == CommandState::FAILED;
}

bool CommandStatusCache::valid(const CommandStatusRecord& record) {
  if (!validUuid(record.operationCommandId) || !validState(record.state) ||
      !validError(record.errorCode)) {
    return false;
  }
  if (record.phaseExecutionIdKnown && !validPhaseId(record.phaseExecutionId))
    return false;
  if (record.semanticIdentityKnown &&
      !validSemanticIdentity(record.semanticIdentity))
    return false;
  if (record.state == CommandState::FAILED)
    return commandErrorCategory(record.errorCode) ==
               CommandErrorCategory::EXECUTION_FAILURE &&
           record.semanticIdentityKnown && record.executionStarted;
  if (record.state == CommandState::REJECTED)
    return commandErrorCategory(record.errorCode) ==
               CommandErrorCategory::REQUEST_REJECTION &&
           !record.executionStarted;
  return record.errorCode == CommandErrorCode::NONE &&
         !record.executionStarted;
}

bool CommandStatusCache::sameIdentity(const CommandStatusRecord& left,
                                      const CommandStatusRecord& right) {
  if (left.phaseExecutionIdKnown != right.phaseExecutionIdKnown) return false;
  if (left.phaseExecutionIdKnown &&
      strcmp(left.phaseExecutionId, right.phaseExecutionId) != 0)
    return false;
  if (left.semanticIdentityKnown != right.semanticIdentityKnown) return false;
  return !left.semanticIdentityKnown ||
         commandSemanticIdentityEqual(left.semanticIdentity,
                                      right.semanticIdentity);
}

bool CommandStatusCache::semanticallyEqual(const CommandStatusRecord& left,
                                           const CommandStatusRecord& right) {
  return sameIdentity(left, right) && left.state == right.state &&
         left.errorCode == right.errorCode &&
         left.executionStarted == right.executionStarted;
}

const CommandStatusEntry* CommandStatusCache::find(
    const char* operationCommandId) const {
  for (const CommandStatusEntry& entry : entries_) {
    if (entry.occupied &&
        strcmp(entry.record.operationCommandId, operationCommandId) == 0) {
      return &entry;
    }
  }
  return nullptr;
}

const CommandStatusEntry* CommandStatusCache::active() const {
  for (const CommandStatusEntry& entry : entries_) {
    if (entry.occupied && !terminal(entry.record.state)) return &entry;
  }
  return nullptr;
}

bool CommandStatusCache::store(const CommandStatusRecord& record) {
  const CommandStatusStoreResult result = storeDetailed(record);
  return result == CommandStatusStoreResult::STORED ||
         result == CommandStatusStoreResult::REPLAYED;
}

CommandStatusStoreResult CommandStatusCache::storeDetailed(
    const CommandStatusRecord& record) {
  if (!valid(record)) return CommandStatusStoreResult::INVALID_RECORD;
  for (CommandStatusEntry& entry : entries_) {
    if (entry.occupied &&
        strcmp(entry.record.operationCommandId, record.operationCommandId) == 0) {
      if (!sameIdentity(entry.record, record))
        return CommandStatusStoreResult::IDENTITY_CONFLICT;
      if (semanticallyEqual(entry.record, record))
        return CommandStatusStoreResult::REPLAYED;
      if (terminal(entry.record.state) ||
          !commandLifecycleTransitionAllowed(entry.record.state, record.state,
                                             record.executionStarted))
        return CommandStatusStoreResult::INVALID_TRANSITION;
      entry.record = record;
      return CommandStatusStoreResult::STORED;
    }
  }

  if (record.state != CommandState::REJECTED &&
      record.state != CommandState::ACCEPTED)
    return CommandStatusStoreResult::INVALID_TRANSITION;
  if (!terminal(record.state)) {
    for (const CommandStatusEntry& entry : entries_) {
      if (entry.occupied && !terminal(entry.record.state))
        return CommandStatusStoreResult::BUSY;
    }
  }
  if (nextInsertionSequence_ == UINT32_MAX)
    return CommandStatusStoreResult::SEQUENCE_EXHAUSTED;

  CommandStatusEntry* target = nullptr;
  for (CommandStatusEntry& entry : entries_) {
    if (!entry.occupied) {
      target = &entry;
      break;
    }
  }
  if (target == nullptr) {
    for (CommandStatusEntry& entry : entries_) {
      if (!terminal(entry.record.state)) continue;
      if (target == nullptr ||
          entry.insertionSequence < target->insertionSequence) {
        target = &entry;
      }
    }
  }
  if (target == nullptr) return CommandStatusStoreResult::BUSY;

  target->occupied = true;
  target->record = record;
  target->insertionSequence = ++nextInsertionSequence_;
  return CommandStatusStoreResult::STORED;
}

size_t CommandStatusCache::occupiedCount() const {
  size_t count = 0;
  for (const CommandStatusEntry& entry : entries_) {
    if (entry.occupied) ++count;
  }
  return count;
}

}  // namespace labforge
