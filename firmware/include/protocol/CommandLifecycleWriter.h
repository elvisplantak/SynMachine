#pragma once

#include <stddef.h>
#include <stdint.h>

#include "identity/BootIdentityStore.h"
#include "protocol/CommandStatusCache.h"

namespace labforge {

constexpr size_t kCommandLifecycleFrameCapacity = 384;

bool writeCommandLifecycle(const char* nonce,
                           const BootIdentityResult& identity,
                           const CommandStatusRecord& record, uint8_t* output,
                           size_t capacity, size_t& outputLength);

}  // namespace labforge
