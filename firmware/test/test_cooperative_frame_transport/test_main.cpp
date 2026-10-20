#include <unity.h>

#include "actuator/P1MotionController.h"
#include "protocol/CooperativeFrameTransport.h"

using namespace labforge;

void setUp() {}
void tearDown() {}

namespace {

class FakeIo final : public P1MotionIo {
 public:
  bool home = false;
  bool direction = false;
  bool step = false;
  uint16_t lastPulseHighUs = 0;
  uint32_t nowUs = 0;
  uint32_t lastRiseUs = 0;
  uint32_t minimumRiseSpacingUs = UINT32_MAX;
  unsigned risingEdges = 0;

  bool homeActive() const override { return home; }
  void writeDirection(bool high) override { direction = high; }
  void writeStep(bool high) override { step = high; }
  void pulseStep(uint16_t highUs) override {
    step = true;
    if (risingEdges > 0) {
      const uint32_t spacing = nowUs - lastRiseUs;
      if (spacing < minimumRiseSpacingUs) minimumRiseSpacingUs = spacing;
    }
    lastRiseUs = nowUs;
    ++risingEdges;
    lastPulseHighUs = highUs;
    step = false;
  }
};

void test_transport_never_offers_more_than_fixed_chunk_or_available_space() {
  CooperativeFrameTransport transport;
  TEST_ASSERT_TRUE(transport.begin(100, false));
  FrameTxSlice slice = transport.nextSlice(64);
  TEST_ASSERT_EQUAL_UINT32(0, slice.offset);
  TEST_ASSERT_EQUAL_UINT32(kSerialTxChunkCapacity, slice.length);
  TEST_ASSERT_EQUAL(FrameTxCompletion::NONE,
                    transport.commit(slice.length, slice.length));

  slice = transport.nextSlice(3);
  TEST_ASSERT_EQUAL_UINT32(kSerialTxChunkCapacity, slice.offset);
  TEST_ASSERT_EQUAL_UINT32(3, slice.length);
}

void test_pending_output_cannot_stretch_atomic_step_high() {
  FakeIo io;
  P1MotionController controller(io);
  CooperativeFrameTransport transport;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(0));
  TEST_ASSERT_TRUE(transport.begin(400, false));

  io.nowUs = kP1DirectionSetupUs;
  TEST_ASSERT_EQUAL(P1MotionResult::NONE, controller.update(io.nowUs));
  TEST_ASSERT_EQUAL_UINT32(1, io.risingEdges);
  TEST_ASSERT_EQUAL_UINT16(kP1StepHighUs, io.lastPulseHighUs);
  TEST_ASSERT_FALSE(io.step);

  for (unsigned i = 0; i < 20; ++i) {
    const FrameTxSlice slice = transport.nextSlice(16);
    transport.commit(slice.length, slice.length);
    TEST_ASSERT_FALSE(io.step);
  }
}

void test_sustained_query_response_tx_does_not_catch_up_or_starve_home() {
  FakeIo io;
  P1MotionController controller(io);
  CooperativeFrameTransport transport;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(0));
  TEST_ASSERT_TRUE(transport.begin(400, false));

  P1MotionResult result = P1MotionResult::NONE;
  for (io.nowUs = 0; io.nowUs <= 40000; io.nowUs += 100) {
    if (io.nowUs == 5000) io.home = true;
    const unsigned before = io.risingEdges;
    result = controller.update(io.nowUs);
    TEST_ASSERT_LESS_OR_EQUAL_UINT32(before + 1, io.risingEdges);
    if (result == P1MotionResult::COMPLETED) break;

    if (transport.pending()) {
      const FrameTxSlice slice = transport.nextSlice(1);
      transport.commit(slice.length, slice.length);
    } else {
      TEST_ASSERT_TRUE(transport.begin(400, false));
    }
  }

  TEST_ASSERT_EQUAL(P1MotionResult::COMPLETED, result);
  TEST_ASSERT_GREATER_OR_EQUAL_UINT32(kP1StepIntervalUs,
                                     io.minimumRiseSpacingUs);
  TEST_ASSERT_FALSE(io.step);
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_transport_never_offers_more_than_fixed_chunk_or_available_space);
  RUN_TEST(test_pending_output_cannot_stretch_atomic_step_high);
  RUN_TEST(test_sustained_query_response_tx_does_not_catch_up_or_starve_home);
  return UNITY_END();
}
