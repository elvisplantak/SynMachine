#pragma once

#include <stddef.h>
#include <stdint.h>

namespace labforge {

constexpr size_t kSerialTxChunkCapacity = 16;

struct FrameTxSlice {
  size_t offset;
  size_t length;
};

enum class FrameTxCompletion : uint8_t {
  NONE,
  FRAME_COMPLETE,
  STARTED_FRAME_COMPLETE,
};

class CooperativeFrameTransport {
 public:
  bool begin(size_t frameLength, bool startsMotion);
  FrameTxSlice nextSlice(size_t availableForWrite) const;
  FrameTxCompletion commit(size_t offeredLength, size_t writtenLength);
  bool pending() const;
  size_t remaining() const;

 private:
  size_t frameLength_ = 0;
  size_t offset_ = 0;
  bool startsMotion_ = false;
  bool pending_ = false;
};

}  // namespace labforge
