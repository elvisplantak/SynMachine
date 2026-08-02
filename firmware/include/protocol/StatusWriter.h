#pragma once

#include <stddef.h>
#include <stdint.h>

#include "identity/BootIdentityStore.h"

namespace labforge {

constexpr size_t kStatusFrameCapacity = 320;

bool writeStatus(const char* nonce, const char* requestId,
                 const BootIdentityResult& identity, uint8_t* output,
                 size_t capacity, size_t& outputLength);

}  // namespace labforge
