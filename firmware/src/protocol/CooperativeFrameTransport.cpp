#include "protocol/CooperativeFrameTransport.h"

namespace labforge {

bool CooperativeFrameTransport::begin(size_t frameLength,
                                      bool startsMotion) {
  if (pending_ || frameLength == 0) return false;
  frameLength_ = frameLength;
  offset_ = 0;
  startsMotion_ = startsMotion;
  pending_ = true;
  return true;
}

FrameTxSlice CooperativeFrameTransport::nextSlice(
    size_t availableForWrite) const {
  if (!pending_ || availableForWrite == 0) return {offset_, 0};
  size_t length = remaining();
  if (length > kSerialTxChunkCapacity) length = kSerialTxChunkCapacity;
  if (length > availableForWrite) length = availableForWrite;
  return {offset_, length};
}

FrameTxCompletion CooperativeFrameTransport::commit(size_t offeredLength,
                                                     size_t writtenLength) {
  if (!pending_ || writtenLength > offeredLength ||
      writtenLength > remaining())
    return FrameTxCompletion::NONE;
  offset_ += writtenLength;
  if (offset_ != frameLength_) return FrameTxCompletion::NONE;

  const bool completedStarted = startsMotion_;
  pending_ = false;
  frameLength_ = 0;
  offset_ = 0;
  startsMotion_ = false;
  return completedStarted ? FrameTxCompletion::STARTED_FRAME_COMPLETE
                          : FrameTxCompletion::FRAME_COMPLETE;
}

bool CooperativeFrameTransport::pending() const { return pending_; }

size_t CooperativeFrameTransport::remaining() const {
  return pending_ ? frameLength_ - offset_ : 0;
}

}  // namespace labforge
