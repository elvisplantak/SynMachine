#pragma once

#include <stddef.h>
#include <stdint.h>

#include "identity/BootIdentityStore.h"
#include "protocol/ProtocolTypes.h"

namespace labforge {

constexpr size_t kProtocolErrorFrameCapacity = 384;

bool writeProtocolError(ProtocolErrorCode error,
                        const ErrorCorrelation& correlation,
                        const BootIdentityResult& identity, uint8_t* output,
                        size_t capacity, size_t& outputLength);

}  // namespace labforge
