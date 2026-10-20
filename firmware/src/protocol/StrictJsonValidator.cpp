#include "protocol/StrictJsonValidator.h"

#include <string.h>

namespace labforge {
namespace {

bool validUtf8(const uint8_t* data, size_t length) {
  for (size_t i = 0; i < length;) {
    const uint8_t first = data[i++];
    if (first == 0) return false;
    if (first <= 0x7F) continue;
    uint32_t codePoint = 0;
    size_t continuationCount = 0;
    if (first >= 0xC2 && first <= 0xDF) {
      codePoint = first & 0x1F;
      continuationCount = 1;
    } else if (first >= 0xE0 && first <= 0xEF) {
      codePoint = first & 0x0F;
      continuationCount = 2;
    } else if (first >= 0xF0 && first <= 0xF4) {
      codePoint = first & 0x07;
      continuationCount = 3;
    } else {
      return false;
    }
    if (i + continuationCount > length) return false;
    for (size_t j = 0; j < continuationCount; ++j) {
      const uint8_t next = data[i++];
      if ((next & 0xC0) != 0x80) return false;
      codePoint = (codePoint << 6) | (next & 0x3F);
    }
    if ((continuationCount == 2 && codePoint < 0x800) ||
        (continuationCount == 3 && codePoint < 0x10000) ||
        (codePoint >= 0xD800 && codePoint <= 0xDFFF) || codePoint > 0x10FFFF) {
      return false;
    }
  }
  return true;
}

class Scanner {
 public:
  Scanner(const uint8_t* data, size_t length)
      : data_(data), length_(length), position_(0), duplicate_(false), nonInteger_(false) {}

  LexicalError run() {
    skipWhitespace();
    if (!parseValue(0)) {
      if (duplicate_) return LexicalError::DUPLICATE_KEY;
      if (nonInteger_) return LexicalError::NON_INTEGER_NUMBER;
      return LexicalError::MALFORMED_JSON;
    }
    skipWhitespace();
    return position_ == length_ ? LexicalError::NONE : LexicalError::MALFORMED_JSON;
  }

 private:
  // Protocol objects have at most eight members. One extra slot lets schema
  // validation classify the first out-of-bounds member.
  static constexpr size_t kMaxObjectKeys = 9;
  static constexpr size_t kDecodedKeyCapacity = 33;
  // The inbound subset needs only the top-level object and arguments object.
  static constexpr uint8_t kMaxDepth = 2;

  struct DecodedKey {
    char bytes[kDecodedKeyCapacity];
    size_t length;
  };

  void skipWhitespace() {
    while (position_ < length_ && (data_[position_] == ' ' || data_[position_] == '\t' ||
                                   data_[position_] == '\r' || data_[position_] == '\n')) {
      ++position_;
    }
  }

  bool consume(uint8_t expected) {
    if (position_ >= length_ || data_[position_] != expected) return false;
    ++position_;
    return true;
  }

  bool parseValue(uint8_t depth) {
    if (position_ >= length_) return false;
    switch (data_[position_]) {
      case '{':
        return depth < kMaxDepth && parseObject(depth + 1);
      case '[':
        return depth < kMaxDepth && parseArray(depth + 1);
      case '"': return parseString(nullptr, 0);
      case 't': return parseLiteral("true");
      case 'f': return parseLiteral("false");
      case 'n': return parseLiteral("null");
      default: return parseNumber();
    }
  }

  bool parseObject(uint8_t depth) {
    if (!consume('{')) return false;
    skipWhitespace();
    if (consume('}')) return true;
    DecodedKey keys[kMaxObjectKeys] = {};
    size_t keyCount = 0;
    while (true) {
      if (keyCount == kMaxObjectKeys || position_ >= length_ || data_[position_] != '"') return false;
      char key[kDecodedKeyCapacity] = {};
      size_t keyLength = 0;
      if (!parseString(key, sizeof(key), &keyLength)) return false;
      for (size_t i = 0; i < keyCount; ++i) {
        if (keys[i].length == keyLength && memcmp(keys[i].bytes, key, keyLength) == 0) {
          duplicate_ = true;
          return false;
        }
      }
      keys[keyCount].length = keyLength;
      memcpy(keys[keyCount].bytes, key, keyLength);
      ++keyCount;
      skipWhitespace();
      if (!consume(':')) return false;
      skipWhitespace();
      if (!parseValue(depth)) return false;
      skipWhitespace();
      if (consume('}')) return true;
      if (!consume(',')) return false;
      skipWhitespace();
    }
  }

  bool parseArray(uint8_t depth) {
    if (!consume('[')) return false;
    skipWhitespace();
    if (consume(']')) return true;
    size_t count = 0;
    while (true) {
      if (++count > 8 || !parseValue(depth)) return false;
      skipWhitespace();
      if (consume(']')) return true;
      if (!consume(',')) return false;
      skipWhitespace();
    }
  }

  static int hexValue(uint8_t value) {
    if (value >= '0' && value <= '9') return value - '0';
    if (value >= 'a' && value <= 'f') return value - 'a' + 10;
    if (value >= 'A' && value <= 'F') return value - 'A' + 10;
    return -1;
  }

  bool readHex4(uint32_t& value) {
    if (position_ + 4 > length_) return false;
    value = 0;
    for (uint8_t i = 0; i < 4; ++i) {
      const int digit = hexValue(data_[position_++]);
      if (digit < 0) return false;
      value = (value << 4) | static_cast<uint32_t>(digit);
    }
    return true;
  }

  bool appendCodePoint(uint32_t codePoint, char* output, size_t capacity, size_t& used) {
    uint8_t encoded[4];
    size_t count = 0;
    if (codePoint <= 0x7F) encoded[count++] = static_cast<uint8_t>(codePoint);
    else if (codePoint <= 0x7FF) {
      encoded[count++] = 0xC0 | (codePoint >> 6);
      encoded[count++] = 0x80 | (codePoint & 0x3F);
    } else if (codePoint <= 0xFFFF) {
      encoded[count++] = 0xE0 | (codePoint >> 12);
      encoded[count++] = 0x80 | ((codePoint >> 6) & 0x3F);
      encoded[count++] = 0x80 | (codePoint & 0x3F);
    } else {
      encoded[count++] = 0xF0 | (codePoint >> 18);
      encoded[count++] = 0x80 | ((codePoint >> 12) & 0x3F);
      encoded[count++] = 0x80 | ((codePoint >> 6) & 0x3F);
      encoded[count++] = 0x80 | (codePoint & 0x3F);
    }
    if (output != nullptr) {
      if (used + count >= capacity) return false;
      for (size_t i = 0; i < count; ++i) output[used++] = static_cast<char>(encoded[i]);
    }
    return true;
  }

  bool parseString(char* output, size_t capacity, size_t* decodedLength = nullptr) {
    if (!consume('"')) return false;
    size_t used = 0;
    while (position_ < length_) {
      uint8_t value = data_[position_++];
      if (value == '"') {
        if (output != nullptr) output[used] = '\0';
        if (decodedLength != nullptr) *decodedLength = used;
        return true;
      }
      if (value < 0x20) return false;
      if (value == '\\') {
        if (position_ >= length_) return false;
        value = data_[position_++];
        if (value == 'u') {
          uint32_t codePoint;
          if (!readHex4(codePoint)) return false;
          if (codePoint >= 0xD800 && codePoint <= 0xDBFF) {
            if (position_ + 2 > length_ || data_[position_] != '\\' || data_[position_ + 1] != 'u') return false;
            position_ += 2;
            uint32_t low;
            if (!readHex4(low) || low < 0xDC00 || low > 0xDFFF) return false;
            codePoint = 0x10000 + ((codePoint - 0xD800) << 10) + (low - 0xDC00);
          } else if (codePoint >= 0xDC00 && codePoint <= 0xDFFF) {
            return false;
          }
          if (!appendCodePoint(codePoint, output, capacity, used)) return false;
          continue;
        }
        switch (value) {
          case '"': case '\\': case '/': break;
          case 'b': value = '\b'; break;
          case 'f': value = '\f'; break;
          case 'n': value = '\n'; break;
          case 'r': value = '\r'; break;
          case 't': value = '\t'; break;
          default: return false;
        }
      }
      if (output != nullptr) {
        if (used + 1 >= capacity) return false;
        output[used++] = static_cast<char>(value);
      }
    }
    return false;
  }

  bool parseLiteral(const char* literal) {
    const size_t size = strlen(literal);
    if (position_ + size > length_ || memcmp(data_ + position_, literal, size) != 0) return false;
    position_ += size;
    return true;
  }

  bool parseNumber() {
    const size_t start = position_;
    if (position_ < length_ && data_[position_] == '-') ++position_;
    if (position_ >= length_) return false;
    if (data_[position_] == '0') {
      ++position_;
      if (position_ < length_ && data_[position_] >= '0' && data_[position_] <= '9') return false;
    } else {
      if (data_[position_] < '1' || data_[position_] > '9') return false;
      while (position_ < length_ && data_[position_] >= '0' && data_[position_] <= '9') ++position_;
    }
    bool usesNonIntegerSyntax = false;
    if (position_ < length_ && data_[position_] == '.') {
      usesNonIntegerSyntax = true;
      ++position_;
      const size_t fraction = position_;
      while (position_ < length_ && data_[position_] >= '0' && data_[position_] <= '9') ++position_;
      if (position_ == fraction) return false;
    }
    if (position_ < length_ && (data_[position_] == 'e' || data_[position_] == 'E')) {
      usesNonIntegerSyntax = true;
      ++position_;
      if (position_ < length_ && (data_[position_] == '+' || data_[position_] == '-')) ++position_;
      const size_t exponent = position_;
      while (position_ < length_ && data_[position_] >= '0' && data_[position_] <= '9') ++position_;
      if (position_ == exponent) return false;
    }
    if (usesNonIntegerSyntax) {
      nonInteger_ = true;
      return false;
    }
    return position_ > start;
  }

  const uint8_t* data_;
  size_t length_;
  size_t position_;
  bool duplicate_;
  bool nonInteger_;
};

}  // namespace

LexicalError StrictJsonValidator::validate(const uint8_t* data, size_t length) const {
  if (data == nullptr && length != 0) return LexicalError::MALFORMED_JSON;
  for (size_t i = 0; i < length; ++i) {
    if (data[i] == 0) return LexicalError::EMBEDDED_NUL;
  }
  if (!validUtf8(data, length)) return LexicalError::INVALID_UTF8;
  return Scanner(data, length).run();
}

}  // namespace labforge
