#pragma once

#include <stdint.h>

namespace labforge {

#ifndef LABFORGE_PIN_DISCOVERY_MAXIMUM_PULSES
#define LABFORGE_PIN_DISCOVERY_MAXIMUM_PULSES 5
#endif

constexpr uint16_t kPinDiscoveryMaximumPulses =
    LABFORGE_PIN_DISCOVERY_MAXIMUM_PULSES;
static_assert(kPinDiscoveryMaximumPulses > 0,
              "Pin discovery must allow at least one pulse");

enum class PinDiscoveryPair : uint8_t { NONE, PAIR_A, PAIR_B };
enum class PinDiscoveryDirection : uint8_t { UNSET, LOGIC_LOW, LOGIC_HIGH };
enum class PinDiscoveryAction : uint8_t { NONE, EMIT_PULSES };
enum class PinDiscoveryStatus : uint8_t {
  OK,
  INVALID_COMMAND,
  SELECTION_REQUIRED,
  DIRECTION_REQUIRED,
  NOT_ARMED,
  INVALID_PULSE_COUNT,
};

struct PinDiscoveryPins {
  uint8_t step;
  uint8_t direction;
};

struct PinDiscoveryResult {
  PinDiscoveryStatus status;
  PinDiscoveryAction action;
  PinDiscoveryPins pins;
  PinDiscoveryDirection direction;
  uint16_t pulseCount;
};

class PinDiscoveryController {
 public:
  PinDiscoveryController();

  PinDiscoveryResult process(const char* command);
  void disarm();

  bool armed() const { return armed_; }
  PinDiscoveryPair selectedPair() const { return selectedPair_; }
  PinDiscoveryDirection direction() const { return direction_; }

  static PinDiscoveryPins pinsFor(PinDiscoveryPair pair);

 private:
  PinDiscoveryResult result(PinDiscoveryStatus status) const;

  PinDiscoveryPair selectedPair_;
  PinDiscoveryDirection direction_;
  bool armed_;
};

}  // namespace labforge
