#include "protocol/CommandStatusCache.h"

#include <limits.h>
#include <string.h>

namespace labforge {

bool CommandStatusCache::terminal(CommandState state) {
  return state == CommandState::REJECTED || state == CommandState::COMPLETED ||
         state == CommandState::FAILED;
}

bool CommandStatusCache::valid(const CommandStatusRecord& record) {
  const char* operationEnd = static_cast<const char*>(
      memchr(record.operationCommandId, '\0', sizeof(record.operationCommandId)));
  if (operationEnd == nullptr ||
      operationEnd - record.operationCommandId != 36) {
    return false;
  }
  if (record.phaseExecutionIdKnown) {
    const char* phaseEnd = static_cast<const char*>(
        memchr(record.phaseExecutionId, '\0', sizeof(record.phaseExecutionId)));
    if (phaseEnd == nullptr || phaseEnd == record.phaseExecutionId) return false;
  }
  const bool needsError = record.state == CommandState::REJECTED ||
                          record.state == CommandState::FAILED;
  if (needsError != (record.errorCode != CommandErrorCode::NONE)) return false;
  if (record.state != CommandState::FAILED && record.executionStarted) return false;
  return true;
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
      if (!terminal(record.state)) {
        for (const CommandStatusEntry& other : entries_) {
          if (&other != &entry && other.occupied &&
              !terminal(other.record.state)) {
            return false;
          }
        }
      }
      entry.record = record;
      return true;
    }
  }

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
