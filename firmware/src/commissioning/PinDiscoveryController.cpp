#include "commissioning/PinDiscoveryController.h"

#include <stdlib.h>
#include <string.h>

namespace labforge {
namespace {

constexpr PinDiscoveryPins kNoPins{0, 0};
constexpr PinDiscoveryPins kPairAPins{34, 35};
constexpr PinDiscoveryPins kPairBPins{36, 37};

bool parsePulseCount(const char* command, uint8_t& count) {
  constexpr char prefix[] = "PULSE ";
  if (strncmp(command, prefix, sizeof(prefix) - 1) != 0) return false;
  const char* value = command + sizeof(prefix) - 1;
  if (*value == '\0') return false;
  char* end = nullptr;
  const long parsed = strtol(value, &end, 10);
  if (*end != '\0' || parsed < 1 || parsed > kPinDiscoveryMaximumPulses)
    return false;
  count = static_cast<uint8_t>(parsed);
  return true;
}

}  // namespace

PinDiscoveryController::PinDiscoveryController()
    : selectedPair_(PinDiscoveryPair::NONE),
      direction_(PinDiscoveryDirection::UNSET),
      armed_(false) {}

PinDiscoveryPins PinDiscoveryController::pinsFor(PinDiscoveryPair pair) {
  if (pair == PinDiscoveryPair::PAIR_A) return kPairAPins;
  if (pair == PinDiscoveryPair::PAIR_B) return kPairBPins;
  return kNoPins;
}

PinDiscoveryResult PinDiscoveryController::result(
    PinDiscoveryStatus status) const {
  return {status, PinDiscoveryAction::NONE, pinsFor(selectedPair_), direction_,
          0};
}

void PinDiscoveryController::disarm() { armed_ = false; }

PinDiscoveryResult PinDiscoveryController::process(const char* command) {
  if (command == nullptr) {
    disarm();
    return result(PinDiscoveryStatus::INVALID_COMMAND);
  }
  if (strcmp(command, "SELECT A") == 0 || strcmp(command, "SELECT B") == 0) {
    selectedPair_ = command[7] == 'A' ? PinDiscoveryPair::PAIR_A
                                      : PinDiscoveryPair::PAIR_B;
    direction_ = PinDiscoveryDirection::UNSET;
    disarm();
    return result(PinDiscoveryStatus::OK);
  }
  if (strcmp(command, "DIR LOW") == 0 || strcmp(command, "DIR HIGH") == 0) {
    if (selectedPair_ == PinDiscoveryPair::NONE) {
      disarm();
      return result(PinDiscoveryStatus::SELECTION_REQUIRED);
    }
    direction_ = command[4] == 'L' ? PinDiscoveryDirection::LOGIC_LOW
                                   : PinDiscoveryDirection::LOGIC_HIGH;
    disarm();
    return result(PinDiscoveryStatus::OK);
  }
  if (strcmp(command, "ARM") == 0) {
    if (selectedPair_ == PinDiscoveryPair::NONE)
      return result(PinDiscoveryStatus::SELECTION_REQUIRED);
    if (direction_ == PinDiscoveryDirection::UNSET)
      return result(PinDiscoveryStatus::DIRECTION_REQUIRED);
    armed_ = true;
    return result(PinDiscoveryStatus::OK);
  }
  if (strcmp(command, "DISARM") == 0) {
    disarm();
    return result(PinDiscoveryStatus::OK);
  }

  uint8_t pulseCount = 0;
  if (parsePulseCount(command, pulseCount)) {
    if (!armed_) return result(PinDiscoveryStatus::NOT_ARMED);
    const PinDiscoveryPins pins = pinsFor(selectedPair_);
    const PinDiscoveryDirection direction = direction_;
    disarm();
    return {PinDiscoveryStatus::OK, PinDiscoveryAction::EMIT_PULSES, pins,
            direction, pulseCount};
  }

  disarm();
  if (strncmp(command, "PULSE", 5) == 0)
    return result(PinDiscoveryStatus::INVALID_PULSE_COUNT);
  return result(PinDiscoveryStatus::INVALID_COMMAND);
}

}  // namespace labforge
