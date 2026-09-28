# Simulated P1/P2 and protected SF transfers

User-approved offline continuation, 2026-09-28. Immediate base:
`2495d1fdfde4f306407cd4723a174acc39be36af`. Consolidated independent-review base:
`7ee5000f08238e7e7def2a681545b7a96eff88c7` (accepted durable-plan milestone).
Branch: `codex/simulated-p1-execution`.

## Scope and interfaces

The existing offline harness now executes all three P1 variants and both P2
transfer sources: Reactor to SF, and SF to Column. `SimulatedTransferRunner` and
`SimulatedTransferDevice` are aliases for the historical P1 names in
`app/hardware/simulated_p1_runner.py`. The latter remain compatible with tests.
Column fraction collection is still rejected before claiming the sequence.

This is explicit simulation, not a live adapter, phase lifecycle integration,
API activation or physical authorization. No Serial/Dynamixel connection is
opened. Existing production Service/SF code, route targets, pump calibration,
firmware and UI code are unchanged. Hypothetical route order and state fixtures
are test inputs only. They do not approve runtime routes or hardware trust.

## Durable SF intent and shared simulated ownership

An explicitly provisioned simulation database now also contains
`simulation_sf_actions`: action ID, phase ID, simulated SF session UUID,
OPEN/CLOSED target, intent/outcome, and error text. Each intent is committed on
a synchronous=FULL connection before the simulated SF send. Existing IDs fail
instead of sending again. A result-write failure can leave INTENT_PERSISTED;
that is unresolved, not success. Simulated definitive errors are represented
using the existing Arduino failure/rejection exception classes only for fault
injection; no claim is made about real Dynamixel failure classification.

Arduino and SF simulation actions execute under the same durable phase owner.
No owner is released between OPEN, pump aspiration and required CLOSE. Ownership
remains held after Stop/failure/ambiguity/crash. Only complete success releases
it; a previously attempted phase is never rerun. The expected database UUID is
supplied independently and SQLite open uses mode=rw, not automatic creation.
Older simulation databases lacking the new table are rejected without migration.
Create a new test database explicitly; never reuse a production runtime database.

## Required follow-ups and error preservation

The runner reuses `_execute_with_required_followup` and `ProtectedOperationError`
from the existing domain operation executor. It runs the stored required follow-up
after successful primary actions or an ordinary primary exception. Both exceptions
are preserved if primary and follow-up fail. Unknown evidence dominates definitive
failure at the phase level: a successful CLOSE never resolves an unknown pump
outcome. No route switch or dispense starts after either side fails.

- SF-to-Column preparation attempts required Column CLOSE even if SF CLOSE fails.
- Protected aspiration executes SF OPEN, then the pump, then required SF CLOSE.
- An OPEN failure skips the pump but still attempts the distinct CLOSE action.
- Stop is observed between operations, never between OPEN/aspiration/CLOSE.
- Arduino boot change blocks further Arduino sends but does not by itself skip
  the independently session-checked simulated SF CLOSE.
- SF session change blocks SF sends; it does not assert that a valve closed.
- No follow-up can run after process death. Restart leaves the owner unresolved
  and sends neither automatic CLOSE nor retry/resume commands. Explicit recovery
  policy and fresh physical trust remain future integration requirements.

Session identity is checked before and after sends. Device fixtures are supplied
independently from saved plans and consumed by a single attempt. The simulation
does not model fluid dynamics, confirm physical valve closure, or establish
production-wide locking across existing Service and SF entry points.

## Verification

- 21 new P2/SF cases, with 38 remaining P1/core cases: 59 simulation tests total.
- 165 combined simulation/store/planner/durable-Arduino tests pass.
- All 1233 backend tests pass; Ruff and diff/whitespace checks pass.
- Exact cross-device ordering and independently visible SF intent before send.
- All nine combinations of primary and required-close success/failure/unknown.
- OPEN failure/unknown skips the pump and attempts CLOSE; Stop during OPEN waits
  through aspiration and CLOSE; initial SF failure still attempts Column CLOSE.
- Arduino reboot and SF session replacement; competing runner during SF CLOSE.
- Abrupt subprocess exit after OPEN and before CLOSE: reopen does not transmit or
  change the database. SF intent/result write faults also block continuation.
- Prior P1 tests cover every action-slot failure, pump-direction Stop, database
  identity, journal-write failure, concurrent runners, and no resend after restart.

## Consolidated review questions and next work

Review from accepted persistence commit `7ee5000` through the pinned HEAD:

1. Is every simulated send preceded by durable intent and protected by the same
   sequence owner? Can a competing/restarted runner accidentally continue?
2. Are primary and CLOSE errors preserved, with uncertainty taking precedence,
   and does no subsequent normal action occur after either failure?
3. Are Stop and process-death behavior honest about required CLOSE guarantees?
4. Are simulation-only guarantees clearly separated from real lifecycle, route
   approval, device trust and production Service/SF ownership?

Next software work: Column collection wait/Stop and required Column CLOSE,
carousel failure/unknown trust loss, then actual lifecycle and shared production
ownership integration tested with fake transports before any API activation.
No main merge, physical test, firmware upload or real recovery is authorized.
