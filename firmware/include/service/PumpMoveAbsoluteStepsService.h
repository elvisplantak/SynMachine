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

class PumpMoveAbsoluteStepsExecutor {
 public:
  virtual ~PumpMoveAbsoluteStepsExecutor() = default;
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
  CACHE_ERROR,
};

class PumpMoveAbsoluteStepsService {
 public:
  PumpMoveServiceStatus execute(const InboundMessage& message,
                                CommandStatusCache& cache,
                                PumpMoveAbsoluteStepsExecutor& executor) const;
};

}  // namespace labforge
