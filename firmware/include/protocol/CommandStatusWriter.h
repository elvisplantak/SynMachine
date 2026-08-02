#pragma once

#include <stddef.h>
#include <stdint.h>

#include "identity/BootIdentityStore.h"
#include "protocol/CommandStatusCache.h"

namespace labforge {

constexpr size_t kCommandStatusFrameCapacity = 464;

bool writeCommandStatus(const char* nonce, const char* requestId,
                        const char* operationCommandId,
                        const BootIdentityResult& identity,
                        const CommandStatusEntry* entry, uint8_t* output,
                        size_t capacity, size_t& outputLength);

}  // namespace labforge
