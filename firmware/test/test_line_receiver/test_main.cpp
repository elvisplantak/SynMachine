#include <unity.h>

#include <initializer_list>
#include <string.h>

#include "protocol/LineReceiver.h"

using namespace labforge;

void test_lf_crlf_fragmentation_and_multiple_frames() {
  LineReceiver receiver;
  FrameView frame{};
  TEST_ASSERT_EQUAL(LineEvent::NONE, receiver.feed('a', frame));
  TEST_ASSERT_EQUAL(LineEvent::FRAME_READY, receiver.feed('\n', frame));
  TEST_ASSERT_EQUAL_UINT32(1, frame.length);
  TEST_ASSERT_EQUAL_UINT8('a', frame.data[0]);
  TEST_ASSERT_EQUAL(LineEvent::NONE, receiver.feed('b', frame));
  TEST_ASSERT_EQUAL(LineEvent::NONE, receiver.feed('\r', frame));
  TEST_ASSERT_EQUAL(LineEvent::FRAME_READY, receiver.feed('\n', frame));
  TEST_ASSERT_EQUAL_UINT32(1, frame.length);
  TEST_ASSERT_EQUAL_UINT8('b', frame.data[0]);
  TEST_ASSERT_EQUAL(LineEvent::FRAME_READY, receiver.feed('\n', frame));
  TEST_ASSERT_EQUAL_UINT32(0, frame.length);
}

void test_exact_512_with_lf_and_crlf() {
  for (bool crlf : {false, true}) {
    LineReceiver receiver;
    FrameView frame{};
    for (size_t i = 0; i < 512; ++i) TEST_ASSERT_EQUAL(LineEvent::NONE, receiver.feed('x', frame));
    TEST_ASSERT_LESS_OR_EQUAL_UINT32(513, receiver.retainedBytes());
    if (crlf) TEST_ASSERT_EQUAL(LineEvent::NONE, receiver.feed('\r', frame));
    TEST_ASSERT_EQUAL(LineEvent::FRAME_READY, receiver.feed('\n', frame));
    TEST_ASSERT_EQUAL_UINT32(512, frame.length);
  }
}

void test_real_513_reports_once_discards_and_recovers() {
  LineReceiver receiver;
  FrameView frame{};
  size_t errors = 0;
  for (size_t i = 0; i < 520; ++i) {
    if (receiver.feed('x', frame) == LineEvent::LINE_TOO_LONG) ++errors;
  }
  TEST_ASSERT_EQUAL_UINT32(1, errors);
  TEST_ASSERT_EQUAL_UINT32(0, receiver.retainedBytes());
  TEST_ASSERT_EQUAL(LineEvent::NONE, receiver.feed('\n', frame));
  TEST_ASSERT_EQUAL(LineEvent::NONE, receiver.feed('{', frame));
  TEST_ASSERT_EQUAL(LineEvent::NONE, receiver.feed('}', frame));
  TEST_ASSERT_EQUAL(LineEvent::FRAME_READY, receiver.feed('\n', frame));
  TEST_ASSERT_EQUAL_UINT32(2, frame.length);
}

void test_512_then_cr_then_real_payload_overflows() {
  LineReceiver receiver;
  FrameView frame{};
  for (size_t i = 0; i < 512; ++i) receiver.feed('x', frame);
  TEST_ASSERT_EQUAL(LineEvent::NONE, receiver.feed('\r', frame));
  TEST_ASSERT_EQUAL(LineEvent::LINE_TOO_LONG, receiver.feed('x', frame));
  TEST_ASSERT_EQUAL(LineEvent::NONE, receiver.feed('\n', frame));
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_lf_crlf_fragmentation_and_multiple_frames);
  RUN_TEST(test_exact_512_with_lf_and_crlf);
  RUN_TEST(test_real_513_reports_once_discards_and_recovers);
  RUN_TEST(test_512_then_cr_then_real_payload_overflows);
  return UNITY_END();
}
