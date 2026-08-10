#pragma once

#include <stddef.h>
#include <stdint.h>

#include "identity/BootIdentityStore.h"
#include "protocol/CommandStatusCache.h"

namespace labforge {

constexpr size_t kStatusFrameCapacity = 320;

bool writeStatus(const char* nonce, const char* requestId,
                 const BootIdentityResult& identity, uint8_t* output,
                 size_t capacity, size_t& outputLength,
                 const CommandStatusCache* commandStatusCache = nullptr,
                 bool p1MotionEnabled = false);

}  // namespace labforge
