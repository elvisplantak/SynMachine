#include "protocol/LineReceiver.h"

namespace labforge {

LineReceiver::LineReceiver() : length_(0), discarding_(false) {}

LineEvent LineReceiver::feed(uint8_t byte, FrameView& frame) {
  frame = {nullptr, 0};
  if (discarding_) {
    if (byte == '\n') discarding_ = false;
    return LineEvent::NONE;
  }
  if (byte == '\n') {
    size_t payloadLength = length_;
    if (payloadLength > 0 && buffer_[payloadLength - 1] == '\r') --payloadLength;
    frame = {buffer_, payloadLength};
    length_ = 0;
    return LineEvent::FRAME_READY;
  }
  if (length_ < kMaxPayloadBytes) {
    buffer_[length_++] = byte;
    return LineEvent::NONE;
  }
  if (length_ == kMaxPayloadBytes && byte == '\r') {
    buffer_[length_++] = byte;
    return LineEvent::NONE;
  }
  length_ = 0;
  discarding_ = true;
  return LineEvent::LINE_TOO_LONG;
}

size_t LineReceiver::retainedBytes() const { return length_; }

}  // namespace labforge
