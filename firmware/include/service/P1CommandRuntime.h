#pragma once

#include <stddef.h>
#include <stdint.h>

#include "actuator/P1MotionController.h"
#include "actuator/CarouselMotionController.h"
#include "actuator/ColumnBottomValveMotionController.h"
#include "actuator/SfMixerMotionController.h"
#include "actuator/ValveMotionController.h"
#include "identity/BootIdentityStore.h"
#include "protocol/CommandStatusCache.h"
#include "protocol/MessageParser.h"
#include "protocol/NoMotionDispatcher.h"
#include "protocol/SessionState.h"

namespace labforge {

class P1CommandRuntime {
 public:
  explicit P1CommandRuntime(P1MotionController& controller);
  P1CommandRuntime(P1MotionController& p1Controller,
                   P1MotionController& p2Controller);
  P1CommandRuntime(P1MotionController& p1Controller,
                   P1MotionController& p2Controller,
                   ValveMotionController* const* valveControllers,
                   uint8_t valveControllerCount);
  P1CommandRuntime(P1MotionController& p1Controller,
                   P1MotionController& p2Controller,
                   ValveMotionController* const* valveControllers,
                   uint8_t valveControllerCount,
                   ColumnBottomValveMotionController& columnValveController);
  P1CommandRuntime(P1MotionController& p1Controller,
                   P1MotionController& p2Controller,
                   ValveMotionController* const* valveControllers,
                   uint8_t valveControllerCount,
                   ColumnBottomValveMotionController& columnValveController,
                   CarouselMotionController& carouselController);
  P1CommandRuntime(P1MotionController& p1Controller,
                   P1MotionController& p2Controller,
                   ValveMotionController* const* valveControllers,
                   uint8_t valveControllerCount,
                   ColumnBottomValveMotionController& columnValveController,
                   CarouselMotionController& carouselController,
                   SfMixerMotionController& sfMixerController);

  DispatchResult dispatch(const uint8_t* payload, size_t length,
                          const BootIdentityResult& identity,
                          SessionState& session, CommandStatusCache& cache,
                          uint8_t* output, size_t capacity);

  bool nextLifecycleFrame(const BootIdentityResult& identity,
                          CommandStatusCache& cache, uint8_t* output,
                          size_t capacity, size_t& outputLength,
                          bool& startsMotion);
  bool confirmStartedFrameWritten(uint32_t nowUs,
                                  CommandStatusCache& cache);
  bool startedFrameTransportFailed();
  void update(uint32_t nowUs, CommandStatusCache& cache);
  bool abort(CommandStatusCache& cache);
  bool hasPendingLifecycleFrame() const;

 private:
  enum class RuntimeState : uint8_t {
    IDLE,
    EMIT_STARTED,
    WAIT_STARTED_WRITE,
    RUNNING,
    EMIT_TERMINAL,
  };

  DispatchResult dispatchCommand(const InboundMessage& message,
                                 const BootIdentityResult& identity,
                                 SessionState& session,
                                 CommandStatusCache& cache, uint8_t* output,
                                 size_t capacity);
  bool reject(const InboundMessage& message,
              const BootIdentityResult& identity, CommandStatusCache& cache,
              CommandErrorCode error, uint8_t* output, size_t capacity,
              size_t& outputLength,
              const CommandSemanticIdentity* semanticIdentity = nullptr);
  bool accept(const InboundMessage& message,
              const CommandSemanticIdentity& semanticIdentity,
              const BootIdentityResult& identity, CommandStatusCache& cache,
              uint8_t* output, size_t capacity, size_t& outputLength);
  void finish(P1MotionResult result, CommandStatusCache& cache);
  void finishValve(ValveMotionResult result, CommandStatusCache& cache);
  void finishColumnValve(ColumnValveMotionResult result,
                         CommandStatusCache& cache);
  void finishCarousel(CarouselMotionResult result, CommandStatusCache& cache);
  void finishSfMixer(SfMixerCommandResult result, CommandStatusCache& cache);
  void handleSessionReplacement(const char* newNonce);
  P1MotionController* controllerFor(PumpId pump);
  ValveMotionController* controllerFor(ValveId valve);

  P1MotionController& p1Controller_;
  P1MotionController* p2Controller_ = nullptr;
  P1MotionController* activeController_ = nullptr;
  ValveMotionController* const* valveControllers_ = nullptr;
  uint8_t valveControllerCount_ = 0;
  ValveMotionController* activeValveController_ = nullptr;
  ColumnBottomValveMotionController* columnValveController_ = nullptr;
  ColumnBottomValveMotionController* activeColumnValveController_ = nullptr;
  CarouselMotionController* carouselController_ = nullptr;
  CarouselMotionController* activeCarouselController_ = nullptr;
  SfMixerMotionController* sfMixerController_ = nullptr;
  SfMixerMotionController* activeSfMixerController_ = nullptr;
  MessageParser parser_;
  NoMotionDispatcher protocolDispatcher_;
  RuntimeState runtimeState_ = RuntimeState::IDLE;
  CommandStatusRecord activeRecord_{};
  char lifecycleNonce_[kUuidTextCapacity]{};
  bool suppressUnsolicitedLifecycle_ = false;
};

}  // namespace labforge
