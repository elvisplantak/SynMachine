#pragma once

#include <stddef.h>
#include <stdint.h>

#include "protocol/ProtocolTypes.h"

namespace labforge {

constexpr size_t kCommandStatusCacheCapacity = 2;

enum class CommandState : uint8_t {
  REJECTED,
  ACCEPTED,
  STARTED,
  COMPLETED,
  FAILED,
};

enum class CommandErrorCode : uint8_t {
  NONE,
  UNSUPPORTED_COMMAND,
  COMMAND_ID_CONFLICT,
  CONTROLLER_BUSY,
  CONTROLLER_IDENTITY_UNTRUSTED,
};

struct CommandStatusRecord {
  char operationCommandId[kUuidTextCapacity];
  char phaseExecutionId[kPhaseExecutionIdCapacity];
  bool phaseExecutionIdKnown;
  CommandState state;
  CommandErrorCode errorCode;
  bool executionStarted;
};

struct CommandStatusEntry {
  bool occupied;
  CommandStatusRecord record;
  uint32_t insertionSequence;
};

bool commandLifecycleTransitionAllowed(CommandState from, CommandState to,
                                       bool executionStarted);

class CommandStatusCache {
 public:
  const CommandStatusEntry* find(const char* operationCommandId) const;
  bool store(const CommandStatusRecord& record);
  size_t occupiedCount() const;

 private:
  static bool terminal(CommandState state);
  static bool valid(const CommandStatusRecord& record);
  static bool sameIdentity(const CommandStatusRecord& left,
                           const CommandStatusRecord& right);
  static bool semanticallyEqual(const CommandStatusRecord& left,
                                const CommandStatusRecord& right);
  CommandStatusEntry entries_[kCommandStatusCacheCapacity]{};
  uint32_t nextInsertionSequence_ = 0;
};

static_assert(sizeof(CommandStatusEntry) <= 128,
              "CommandStatusEntry exceeds its SRAM budget");
static_assert(sizeof(CommandStatusCache) <= 256,
              "CommandStatusCache exceeds its SRAM budget");

}  // namespace labforge
