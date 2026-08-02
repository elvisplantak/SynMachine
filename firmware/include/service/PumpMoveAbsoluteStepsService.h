#pragma once

#include <stdint.h>

#include "protocol/CommandStatusCache.h"
#include "protocol/PumpMoveAbsoluteStepsContract.h"
#include "protocol/ProtocolTypes.h"

namespace labforge {

enum class PumpMoveExecutionOutcome : uint8_t {
  COMPLETED,
  MOTION_TIMEOUT,
  HOME_SWITCH_UNEXPECTED,
};

enum class PumpMovePreflightOutcome : uint8_t { READY, NOT_READY };

class PumpMoveAbsoluteStepsExecutor {
 public:
  virtual ~PumpMoveAbsoluteStepsExecutor() = default;
  // Must be bounded and have no physical or driver-signal side effects.
  virtual PumpMovePreflightOutcome preflight(
      const PumpMoveAbsoluteStepsCommand& command) = 0;
  // A future physical implementation may cross its first side-effect boundary
  // immediately on entry. No validation or refusal belongs in this method.
  virtual PumpMoveExecutionOutcome execute(
      const PumpMoveAbsoluteStepsCommand& command) = 0;
};

enum class PumpMoveServiceStatus : uint8_t {
  COMPLETED,
  FAILED,
  REPLAYED,
  COMMAND_ID_CONFLICT,
  CONTROLLER_BUSY,
  UNSUPPORTED_COMMAND,
  INVALID_ARGUMENTS,
  PREFLIGHT_REJECTED,
  CACHE_ERROR,
};

class PumpMoveAbsoluteStepsService {
 public:
  PumpMoveServiceStatus execute(const InboundMessage& message,
                                CommandStatusCache& cache,
                                PumpMoveAbsoluteStepsExecutor& executor) const;
};

}  // namespace labforge
