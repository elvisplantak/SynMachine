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
         error == CommandErrorCode::UNSUPPORTED_COMMAND ||
         error == CommandErrorCode::COMMAND_ID_CONFLICT ||
         error == CommandErrorCode::CONTROLLER_BUSY ||
         error == CommandErrorCode::CONTROLLER_IDENTITY_UNTRUSTED;
}

}  // namespace

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
  if (record.state == CommandState::FAILED) return false;
  if (record.state == CommandState::REJECTED)
    return record.errorCode != CommandErrorCode::NONE &&
           !record.executionStarted;
  return record.errorCode == CommandErrorCode::NONE &&
         !record.executionStarted;
}

bool CommandStatusCache::sameIdentity(const CommandStatusRecord& left,
                                      const CommandStatusRecord& right) {
  if (left.phaseExecutionIdKnown != right.phaseExecutionIdKnown) return false;
  return !left.phaseExecutionIdKnown ||
         strcmp(left.phaseExecutionId, right.phaseExecutionId) == 0;
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

bool CommandStatusCache::store(const CommandStatusRecord& record) {
  if (!valid(record)) return false;
  for (CommandStatusEntry& entry : entries_) {
    if (entry.occupied &&
        strcmp(entry.record.operationCommandId, record.operationCommandId) == 0) {
      if (!sameIdentity(entry.record, record)) return false;
      if (semanticallyEqual(entry.record, record)) return true;
      if (terminal(entry.record.state) ||
          !commandLifecycleTransitionAllowed(entry.record.state, record.state,
                                             record.executionStarted))
        return false;
      entry.record = record;
      return true;
    }
  }

  if (record.state != CommandState::REJECTED &&
      record.state != CommandState::ACCEPTED)
    return false;
  if (!terminal(record.state)) {
    for (const CommandStatusEntry& entry : entries_) {
      if (entry.occupied && !terminal(entry.record.state)) return false;
    }
  }
  if (nextInsertionSequence_ == UINT32_MAX) return false;

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
  if (target == nullptr) return false;

  target->occupied = true;
  target->record = record;
  target->insertionSequence = ++nextInsertionSequence_;
  return true;
}

size_t CommandStatusCache::occupiedCount() const {
  size_t count = 0;
  for (const CommandStatusEntry& entry : entries_) {
    if (entry.occupied) ++count;
  }
  return count;
}

}  // namespace labforge
