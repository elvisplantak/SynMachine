#pragma once

#include <stddef.h>
#include <stdint.h>

namespace labforge {

constexpr size_t kMaxPayloadBytes = 512;

enum class LineEvent : uint8_t { NONE, FRAME_READY, LINE_TOO_LONG };

struct FrameView {
  const uint8_t* data;
  size_t length;
};

class LineReceiver {
 public:
  LineReceiver();
  LineEvent feed(uint8_t byte, FrameView& frame);
  size_t retainedBytes() const;

 private:
  uint8_t buffer_[kMaxPayloadBytes + 1];
  size_t length_;
  bool discarding_;
};

}  // namespace labforge
