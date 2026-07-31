#pragma once

#include <stddef.h>
#include <stdint.h>

namespace labforge {

enum class LexicalError : uint8_t {
  NONE,
  INVALID_UTF8,
  EMBEDDED_NUL,
  MALFORMED_JSON,
  DUPLICATE_KEY,
  NON_INTEGER_NUMBER
};

class StrictJsonValidator {
 public:
  LexicalError validate(const uint8_t* data, size_t length) const;
};

}  // namespace labforge
