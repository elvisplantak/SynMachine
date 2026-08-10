#pragma once

#include <stddef.h>
#include <stdint.h>

#include "identity/BootIdentityStore.h"

namespace labforge {

constexpr size_t kHelloOkFrameCapacity = 320;

bool writeHelloOk(const char* nonce, const BootIdentityResult& identity,
                  uint8_t* output, size_t capacity, size_t& outputLength,
                  bool p1MotionEnabled = false);

}  // namespace labforge
