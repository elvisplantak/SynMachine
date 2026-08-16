#include <unity.h>

#include <cstdio>
#include <cstring>

#include "actuator/CarouselMotionController.h"
#include "actuator/ColumnBottomValveMotionController.h"
#include "actuator/SfMixerMotionController.h"
#include "protocol/CommandLifecycleWriter.h"
#include "protocol/HelloOkWriter.h"
#include "service/P1CommandRuntime.h"

using namespace labforge;

namespace {

constexpr char NONCE[] = "123e4567-e89b-12d3-a456-426614174000";
constexpr BootIdentityResult IDENTITY{true, 7, IdentityFailureReason::NONE};

class PumpIo : public P1MotionIo {
 public:
  bool homeActive() const override { return false; }
  void writeDirection(bool) override { ++directionWrites; }
  void writeStep(bool) override {}
  void pulseStep(uint16_t) override { ++pulses; }
  uint16_t directionWrites = 0;
  uint16_t pulses = 0;
};

class ValveIo : public ValveMotionIo {
 public:
  bool homeActive() const override { return false; }
  void writeDirection(bool) override {}
  void writeStep(bool) override {}
  void pulseStep(uint16_t) override {}
};

class CarouselIo : public CarouselMotionIo {
 public:
  void writeDirection(bool) override {}
  void writeStep(bool) override {}
  void pulseStep(uint16_t) override {}
};

class MixerIo : public SfMixerMotionIo {
 public:
  void writeDirection(bool high) override {
    direction = high;
    ++directionWrites;
  }
  void writeStep(bool high) override { step = high; }
  void pulseStep(uint16_t highUs) override {
    ++pulses;
    lastPulseWidth = highUs;
    step = false;
  }
  bool direction = true;
  bool step = false;
  uint16_t directionWrites = 0;
  uint16_t pulses = 0;
  uint16_t lastPulseWidth = 0;
};

void makeCommand(char* frame, size_t capacity, const char* operation,
                 const char* command, const char* arguments,
                 const char* nonce = NONCE) {
  std::snprintf(
      frame, capacity,
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\","
      "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":7,"
      "\"phase_execution_id\":\"phase-1\","
      "\"operation_command_id\":\"%s\",\"command\":\"%s\","
      "\"arguments\":%s}",
      nonce, operation, command, arguments);
}

struct Fixture {
  PumpIo pumpIo;
  P1MotionController p1{pumpIo};
  P1MotionController p2{pumpIo};
  ValveIo columnIo;
  ColumnBottomValveMotionController column{columnIo};
  CarouselIo carouselIo;
  CarouselMotionController carousel{carouselIo};
  MixerIo mixerIo;
  SfMixerMotionController mixer{mixerIo};
  P1CommandRuntime runtime{p1, p2, nullptr, 0, column, carousel, mixer};
  SessionState session;
  CommandStatusCache cache;
  uint8_t output[kHelloOkFrameCapacity]{};

  Fixture() { session.establish(NONCE); }
};

void dispatch(Fixture& fixture, const char* operation, const char* command,
              const char* arguments) {
  char frame[384];
  makeCommand(frame, sizeof(frame), operation, command, arguments);
  fixture.runtime.dispatch(reinterpret_cast<const uint8_t*>(frame),
                           std::strlen(frame), IDENTITY, fixture.session,
                           fixture.cache, fixture.output,
                           sizeof(fixture.output));
}

void startLifecycle(Fixture& fixture, uint32_t nowUs) {
  size_t length = 0;
  bool startsMotion = false;
  TEST_ASSERT_TRUE(fixture.runtime.nextLifecycleFrame(
      IDENTITY, fixture.cache, fixture.output, sizeof(fixture.output), length,
      startsMotion));
  TEST_ASSERT_TRUE(startsMotion);
  TEST_ASSERT_TRUE(
      fixture.runtime.confirmStartedFrameWritten(nowUs, fixture.cache));
}

void test_start_waits_for_started_frame_and_continues_after_completion() {
  Fixture fixture;
  constexpr char operation[] = "323e4567-e89b-12d3-a456-426614174002";
  dispatch(fixture, operation, "SF_MIXER_SET_STATE", "{\"running\":true}");
  TEST_ASSERT_EQUAL_UINT16(0, fixture.mixerIo.directionWrites);
  TEST_ASSERT_EQUAL_UINT16(0, fixture.mixerIo.pulses);
  startLifecycle(fixture, 100);
  TEST_ASSERT_EQUAL_UINT16(1, fixture.mixerIo.directionWrites);
  TEST_ASSERT_FALSE(fixture.mixerIo.direction);
  TEST_ASSERT_EQUAL_UINT16(0, fixture.mixerIo.pulses);
  fixture.runtime.update(104, fixture.cache);
  TEST_ASSERT_EQUAL(CommandState::STARTED,
                    fixture.cache.find(operation)->record.state);
  fixture.runtime.update(105, fixture.cache);
  TEST_ASSERT_EQUAL_UINT16(1, fixture.mixerIo.pulses);
  TEST_ASSERT_EQUAL_UINT16(kSfMixerStepHighUs,
                           fixture.mixerIo.lastPulseWidth);
  TEST_ASSERT_EQUAL(CommandState::COMPLETED,
                    fixture.cache.find(operation)->record.state);
  fixture.runtime.update(105 + kSfMixerStepIntervalUs, fixture.cache);
  TEST_ASSERT_EQUAL_UINT16(2, fixture.mixerIo.pulses);
  TEST_ASSERT_TRUE(fixture.mixer.running());
}

void test_running_mixer_blocks_other_actuators_but_accepts_stop() {
  Fixture fixture;
  dispatch(fixture, "323e4567-e89b-12d3-a456-426614174002",
           "SF_MIXER_SET_STATE", "{\"running\":true}");
  startLifecycle(fixture, 100);
  fixture.runtime.update(105, fixture.cache);

  dispatch(fixture, "423e4567-e89b-12d3-a456-426614174003", "PUMP_HOME",
           "{\"pump\":\"P1\"}");
  TEST_ASSERT_NOT_NULL(std::strstr(reinterpret_cast<char*>(fixture.output),
                                  "CONTROLLER_BUSY"));
  TEST_ASSERT_EQUAL_UINT16(0, fixture.pumpIo.directionWrites);

  constexpr char stopOperation[] = "523e4567-e89b-12d3-a456-426614174004";
  dispatch(fixture, stopOperation, "SF_MIXER_SET_STATE",
           "{\"running\":false}");
  startLifecycle(fixture, 200);
  fixture.runtime.update(200, fixture.cache);
  TEST_ASSERT_FALSE(fixture.mixer.running());
  TEST_ASSERT_FALSE(fixture.mixerIo.step);
  TEST_ASSERT_EQUAL(CommandState::COMPLETED,
                    fixture.cache.find(stopOperation)->record.state);
}

void test_session_replacement_does_not_change_running_mixer_output() {
  Fixture fixture;
  dispatch(fixture, "323e4567-e89b-12d3-a456-426614174002",
           "SF_MIXER_SET_STATE", "{\"running\":true}");
  startLifecycle(fixture, 100);
  fixture.runtime.update(105, fixture.cache);
  TEST_ASSERT_TRUE(fixture.mixer.running());
  const uint16_t pulses = fixture.mixerIo.pulses;

  const char hello[] =
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"HELLO\","
      "\"backend_session_nonce\":"
      "\"223e4567-e89b-12d3-a456-426614174001\"}";
  fixture.runtime.dispatch(reinterpret_cast<const uint8_t*>(hello),
                           std::strlen(hello), IDENTITY, fixture.session,
                           fixture.cache, fixture.output,
                           sizeof(fixture.output));
  TEST_ASSERT_TRUE(fixture.mixer.running());
  fixture.runtime.update(105 + kSfMixerStepIntervalUs, fixture.cache);
  TEST_ASSERT_EQUAL_UINT16(pulses + 1, fixture.mixerIo.pulses);
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_start_waits_for_started_frame_and_continues_after_completion);
  RUN_TEST(test_running_mixer_blocks_other_actuators_but_accepts_stop);
  RUN_TEST(test_session_replacement_does_not_change_running_mixer_output);
  return UNITY_END();
}
