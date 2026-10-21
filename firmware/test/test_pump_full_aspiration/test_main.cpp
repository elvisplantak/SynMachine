#include <unity.h>

#include <initializer_list>
#include <stdio.h>
#include <string.h>

#include "actuator/P1MotionController.h"
#include "protocol/HelloOkWriter.h"
#include "protocol/MessageParser.h"
#include "protocol/PumpFullAspirationContract.h"
#include "service/P1CommandRuntime.h"

using namespace labforge;

void setUp() {}
void tearDown() {}

namespace {
constexpr char NONCE[] = "123e4567-e89b-12d3-a456-426614174000";
constexpr char OPERATION[] = "323e4567-e89b-12d3-a456-426614174002";
constexpr BootIdentityResult IDENTITY{true, 7, IdentityFailureReason::NONE};

class FakeIo : public P1MotionIo {
 public:
  int physical = 0;
  bool homeEnabled = true;
  bool forceHome = false;
  bool direction = false;
  bool step = false;
  unsigned pulses = 0;
  unsigned directionWrites = 0;
  bool homeActive() const override {
    return forceHome || (homeEnabled && physical <= 0);
  }
  void writeDirection(bool high) override { direction = high; ++directionWrites; }
  void writeStep(bool high) override { step = high; }
  void pulseStep(uint16_t highUs) override {
    TEST_ASSERT_EQUAL_UINT16(kP1StepHighUs, highUs);
    physical += direction ? 1 : -1;
    ++pulses;
    step = false;
  }
};

P1MotionResult finish(P1MotionController& controller, uint32_t& now) {
  P1MotionResult result = P1MotionResult::NONE;
  for (unsigned i = 0; controller.busy() && i < 25000; ++i) {
    now += kP1StepIntervalUs;
    result = controller.update(now);
  }
  TEST_ASSERT_FALSE(controller.busy());
  return result;
}

void atEmpty(P1MotionController& controller, uint32_t& now) {
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareHome());
  TEST_ASSERT_TRUE(controller.start(now));
  TEST_ASSERT_EQUAL(P1MotionResult::COMPLETED, finish(controller, now));
  TEST_ASSERT_EQUAL(P1PrepareResult::READY,
                    controller.prepareMoveAbsolute(kP1MaximumAbsoluteSteps));
  TEST_ASSERT_TRUE(controller.start(now));
  TEST_ASSERT_EQUAL(P1MotionResult::COMPLETED, finish(controller, now));
  TEST_ASSERT_EQUAL_UINT16(kP1MaximumAbsoluteSteps, controller.positionSteps());
}

InboundMessage parse(const char* arguments, const char* name = "PUMP_ASPIRATE_FULL_STROKE") {
  char line[512];
  snprintf(line, sizeof(line),
      "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\","
      "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":7,"
      "\"phase_execution_id\":\"full-stroke\",\"operation_command_id\":\"%s\","
      "\"command\":\"%s\",\"arguments\":%s}", NONCE, OPERATION, name, arguments);
  const ParseResult result = MessageParser().parse(
      reinterpret_cast<const uint8_t*>(line), strlen(line));
  TEST_ASSERT_EQUAL(ParseStatus::VALID_MESSAGE, result.status);
  return result.message;
}

void test_full_stroke_contract_is_exact_and_identity_differs_from_home() {
  for (const char* pump : {"P1", "P2"}) {
    char arguments[32];
    snprintf(arguments, sizeof(arguments), "{\"pump\":\"%s\"}", pump);
    PumpFullAspirationCommand command{};
    TEST_ASSERT_EQUAL(PumpHomeContractStatus::VALID,
                      parsePumpFullAspiration(parse(arguments), command));
    const auto identity = semanticIdentity(command);
    TEST_ASSERT_EQUAL(CommandKind::PUMP_ASPIRATE_FULL_STROKE, identity.command);
    TEST_ASSERT_FALSE(commandSemanticIdentityEqual(identity,
        {CommandKind::PUMP_HOME, command.pump, 0}));
  }
  const char* bad[] = {"{}", "{\"pump\":\"P3\"}", "{\"pump\":true}",
      "{\"pump\":\"P1\",\"target_steps\":0}", "{\"pump\":\"P2\",\"speed\":600}"};
  for (const char* arguments : bad) {
    PumpFullAspirationCommand command{};
    TEST_ASSERT_EQUAL(PumpHomeContractStatus::INVALID_ARGUMENTS,
                      parsePumpFullAspiration(parse(arguments), command));
  }
}

void test_only_trusted_empty_inactive_home_can_prepare_without_gpio() {
  FakeIo io; P1MotionController controller(io); uint32_t now = 0;
  TEST_ASSERT_EQUAL(P1PrepareResult::POSITION_UNTRUSTED, controller.prepareFullAspiration());
  TEST_ASSERT_EQUAL_UINT32(0, io.directionWrites);
  atEmpty(controller, now);
  const unsigned writes = io.directionWrites, pulses = io.pulses;
  io.forceHome = true;
  TEST_ASSERT_EQUAL(P1PrepareResult::HOME_SWITCH_ACTIVE, controller.prepareFullAspiration());
  io.forceHome = false;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareFullAspiration());
  TEST_ASSERT_EQUAL(P1PrepareResult::BUSY, controller.prepareFullAspiration());
  TEST_ASSERT_EQUAL_UINT32(writes, io.directionWrites);
  TEST_ASSERT_EQUAL_UINT32(pulses, io.pulses);
  TEST_ASSERT_TRUE(controller.abort());
  TEST_ASSERT_EQUAL(P1PositionTrust::TRUSTED, controller.positionTrust());
  TEST_ASSERT_EQUAL(P1PrepareResult::TARGET_REQUIRES_HOME, controller.prepareMoveAbsolute(0));
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareMoveAbsolute(20000));
  TEST_ASSERT_TRUE(controller.start(now));
  TEST_ASSERT_EQUAL(P1MotionResult::COMPLETED, finish(controller, now));
  TEST_ASSERT_EQUAL(P1PrepareResult::INVALID_TARGET, controller.prepareFullAspiration());
}

void test_full_stroke_reaches_stable_home_and_dispenses_back_to_empty() {
  FakeIo io; P1MotionController controller(io); uint32_t now = 0;
  atEmpty(controller, now); const unsigned before = io.pulses;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareFullAspiration());
  TEST_ASSERT_TRUE(controller.start(now));
  TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED, controller.positionTrust());
  TEST_ASSERT_EQUAL(P1MotionResult::COMPLETED, finish(controller, now));
  TEST_ASSERT_EQUAL_UINT32(kP1MaximumAbsoluteSteps, io.pulses - before);
  TEST_ASSERT_EQUAL_UINT16(0, controller.positionSteps());
  TEST_ASSERT_EQUAL(P1PositionTrust::TRUSTED, controller.positionTrust());
  TEST_ASSERT_FALSE(io.step);
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareMoveAbsolute(20500));
  TEST_ASSERT_TRUE(controller.start(now));
  TEST_ASSERT_EQUAL(P1MotionResult::COMPLETED, finish(controller, now));
  TEST_ASSERT_EQUAL_UINT16(20500, controller.positionSteps());
  TEST_ASSERT_FALSE(io.homeActive());
}

void test_missing_home_is_bounded_and_abort_invalidates_trust() {
  FakeIo io; P1MotionController controller(io); uint32_t now = 0;
  atEmpty(controller, now); io.homeEnabled = false;
  const unsigned before = io.pulses;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareFullAspiration());
  TEST_ASSERT_TRUE(controller.start(now));
  TEST_ASSERT_EQUAL(P1MotionResult::MOTION_TIMEOUT, finish(controller, now));
  TEST_ASSERT_EQUAL_UINT32(kP1MaximumAbsoluteSteps, io.pulses - before);
  TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED, controller.positionTrust());
  TEST_ASSERT_FALSE(io.step);
  io.homeEnabled = true; atEmpty(controller, now);
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareFullAspiration());
  TEST_ASSERT_TRUE(controller.start(now)); now += kP1StepIntervalUs;
  controller.update(now); TEST_ASSERT_TRUE(controller.abort());
  TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED, controller.positionTrust());
  TEST_ASSERT_FALSE(io.step);
}

void test_early_home_or_activation_after_preflight_cannot_complete_a_full_stroke() {
  for (bool atStart : {false, true}) {
    FakeIo io; P1MotionController controller(io); uint32_t now = 0;
    atEmpty(controller, now); const unsigned before = io.pulses;
    TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareFullAspiration());
    if (atStart) io.forceHome = true;
    TEST_ASSERT_TRUE(controller.start(now));
    if (!atStart) {
      now += kP1StepIntervalUs; controller.update(now);
      io.forceHome = true;
    }
    TEST_ASSERT_EQUAL(P1MotionResult::HOME_SWITCH_UNEXPECTED, finish(controller, now));
    TEST_ASSERT_EQUAL_UINT32(atStart ? 0 : 1, io.pulses - before);
    TEST_ASSERT_EQUAL(P1PositionTrust::UNTRUSTED, controller.positionTrust());
    TEST_ASSERT_FALSE(io.step);
  }
}

void test_early_home_glitch_resumes_bounded_search_without_false_completion() {
  FakeIo io; P1MotionController controller(io); uint32_t now = 0;
  atEmpty(controller, now); const unsigned before = io.pulses;
  TEST_ASSERT_EQUAL(P1PrepareResult::READY, controller.prepareFullAspiration());
  TEST_ASSERT_TRUE(controller.start(now));
  now += kP1StepIntervalUs; controller.update(now);
  io.forceHome = true; now += kP1StepIntervalUs; controller.update(now);
  TEST_ASSERT_EQUAL(P1MotionState::CONFIRMING_UNEXPECTED_HOME, controller.state());
  io.forceHome = false; controller.update(now);
  TEST_ASSERT_EQUAL(P1MotionState::SEARCHING_HOME, controller.state());
  TEST_ASSERT_EQUAL(P1MotionResult::COMPLETED, finish(controller, now));
  TEST_ASSERT_EQUAL_UINT32(20500, io.pulses - before);
}

void test_runtime_both_pumps_order_started_and_replay_without_other_motion() {
  for (unsigned selected = 0; selected < 2; ++selected) {
    FakeIo p1io, p2io; P1MotionController p1(p1io), p2(p2io);
    uint32_t now = 0; atEmpty(p1, now); atEmpty(p2, now);
    P1CommandRuntime runtime(p1, p2); SessionState session; session.establish(NONCE);
    CommandStatusCache cache; uint8_t output[464]; char frame[512];
    const char* pump = selected == 0 ? "P1" : "P2";
    snprintf(frame, sizeof(frame),
        "{\"protocol\":\"LABFORGE/1\",\"type\":\"COMMAND\","
        "\"backend_session_nonce\":\"%s\",\"controller_boot_id\":7,"
        "\"phase_execution_id\":\"full-stroke\",\"operation_command_id\":\"%s\","
        "\"command\":\"PUMP_ASPIRATE_FULL_STROKE\",\"arguments\":{\"pump\":\"%s\"}}",
        NONCE, OPERATION, pump);
    const unsigned p1before = p1io.pulses, p2before = p2io.pulses;
    auto send = [&]() { return runtime.dispatch(reinterpret_cast<const uint8_t*>(frame),
        strlen(frame), IDENTITY, session, cache, output, sizeof(output)); };
    send(); TEST_ASSERT_EQUAL(CommandState::ACCEPTED, cache.find(OPERATION)->record.state);
    TEST_ASSERT_EQUAL_UINT32(p1before, p1io.pulses);
    TEST_ASSERT_EQUAL_UINT32(p2before, p2io.pulses);
    size_t length = 0; bool starts = false;
    TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(IDENTITY, cache, output, sizeof(output), length, starts));
    TEST_ASSERT_TRUE(starts);
    TEST_ASSERT_EQUAL_UINT32(p1before, p1io.pulses);
    TEST_ASSERT_EQUAL_UINT32(p2before, p2io.pulses);
    TEST_ASSERT_TRUE(runtime.confirmStartedFrameWritten(now, cache));
    for (unsigned i = 0; cache.find(OPERATION)->record.state == CommandState::STARTED && i < 25000; ++i) {
      now += kP1StepIntervalUs; runtime.update(now, cache);
    }
    TEST_ASSERT_EQUAL(CommandState::COMPLETED, cache.find(OPERATION)->record.state);
    TEST_ASSERT_TRUE(runtime.nextLifecycleFrame(IDENTITY, cache, output, sizeof(output), length, starts));
    const unsigned p1after = p1io.pulses, p2after = p2io.pulses;
    TEST_ASSERT_EQUAL_UINT32(selected == 0 ? 20500 : 0, p1after - p1before);
    TEST_ASSERT_EQUAL_UINT32(selected == 1 ? 20500 : 0, p2after - p2before);
    send(); TEST_ASSERT_EQUAL_UINT32(p1after, p1io.pulses); TEST_ASSERT_EQUAL_UINT32(p2after, p2io.pulses);
    TEST_ASSERT_EQUAL(CommandState::COMPLETED, cache.find(OPERATION)->record.state);
  }
}

void test_full_capability_hello_fits_existing_buffer_at_maximum_boot_id() {
  uint8_t output[kHelloOkFrameCapacity]; size_t length = 0;
  const BootIdentityResult identity{true, UINT32_MAX, IdentityFailureReason::NONE};
  TEST_ASSERT_TRUE(writeHelloOk(NONCE, identity, output, sizeof(output), length, true));
  TEST_ASSERT_LESS_THAN_UINT32(sizeof(output), length);
  TEST_ASSERT_LESS_OR_EQUAL_UINT32(513, length);
  TEST_ASSERT_NOT_NULL(strstr(reinterpret_cast<const char*>(output), "PUMP_ASPIRATE_FULL_STROKE"));
}
}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_full_stroke_contract_is_exact_and_identity_differs_from_home);
  RUN_TEST(test_only_trusted_empty_inactive_home_can_prepare_without_gpio);
  RUN_TEST(test_full_stroke_reaches_stable_home_and_dispenses_back_to_empty);
  RUN_TEST(test_missing_home_is_bounded_and_abort_invalidates_trust);
  RUN_TEST(test_early_home_or_activation_after_preflight_cannot_complete_a_full_stroke);
  RUN_TEST(test_early_home_glitch_resumes_bounded_search_without_false_completion);
  RUN_TEST(test_runtime_both_pumps_order_started_and_replay_without_other_motion);
  RUN_TEST(test_full_capability_hello_fits_existing_buffer_at_maximum_boot_id);
  return UNITY_END();
}
