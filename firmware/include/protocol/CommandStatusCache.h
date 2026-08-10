#pragma once

#include <stddef.h>
#include <stdint.h>

#include "protocol/ProtocolTypes.h"

namespace labforge {

constexpr size_t kCommandStatusCacheCapacity = 2;
constexpr uint16_t kP1MaximumAbsoluteSteps = 20500;

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
  PUMP_MOTION_TIMEOUT,
  PUMP_HOME_SWITCH_UNEXPECTED,
  PUMP_HOME_SWITCH_STUCK,
};

enum class CommandErrorCategory : uint8_t {
  NONE,
  REQUEST_REJECTION,
  EXECUTION_FAILURE,
  INVALID,
};

enum class CommandStatusStoreResult : uint8_t {
  STORED,
  REPLAYED,
  BUSY,
  SEQUENCE_EXHAUSTED,
  INVALID_RECORD,
  IDENTITY_CONFLICT,
  INVALID_TRANSITION,
};

enum class CommandKind : uint8_t {
  NONE,
  PUMP_HOME,
  PUMP_MOVE_ABSOLUTE_STEPS,
};
enum class PumpId : uint8_t { NONE, P1 };

struct CommandSemanticIdentity {
  CommandKind command;
  PumpId pump;
  uint16_t targetSteps;
};

struct CommandStatusRecord {
  char operationCommandId[kUuidTextCapacity];
  char phaseExecutionId[kPhaseExecutionIdCapacity];
  bool phaseExecutionIdKnown;
  bool semanticIdentityKnown;
  CommandSemanticIdentity semanticIdentity;
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
bool commandSemanticIdentityEqual(const CommandSemanticIdentity& left,
                                  const CommandSemanticIdentity& right);
CommandErrorCategory commandErrorCategory(CommandErrorCode error);

class CommandStatusCache {
 public:
  const CommandStatusEntry* find(const char* operationCommandId) const;
  bool store(const CommandStatusRecord& record);
  CommandStatusStoreResult storeDetailed(const CommandStatusRecord& record);
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
