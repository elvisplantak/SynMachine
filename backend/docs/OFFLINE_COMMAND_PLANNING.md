# Offline command planning checkpoint

User-approved scope (2026-09-26): develop the backend bridge from existing
Guided Demo operation plans to low-level commands, using automated tests only.
No physical commands, Serial connection, upload, or runtime activation.

`app.hardware.command_planning.prepare_command_plan(operations, context)`
prepares the entire operation tuple before returning any result. It has no I/O,
transport dependency, application-startup hook, or API endpoint. The existing
Service APIs, execution coordinator, databases, and firmware are unchanged.

## Inputs and guarantees

- Explicit phase identity and expected trusted controller boot ID.
- Explicit pump calibration/nominal mapping and assumed current positions.
  No HOME, empty-pump, calibration, or safe-route assumption is synthesized.
- Explicit referenced valve positions and caller-proposed switching sequences.
  Final valve target sets are derived from the approved topology and nominal
  90/180-degree port mapping. They are not physically verified routes. There is
  no built-in switching order; test orders are hypothetical fixtures only.
- Separate SF and Column state assumptions, Reactor mixer OFF for Reactor-to-SF
  transfer, and an explicit carousel tube aligned for the first fraction.

The output retains scheduler-operation boundaries. Protected SF aspiration
keeps OPEN and aspiration in its primary actions and CLOSED in its required
follow-up. Column collection keeps OPEN and a Stop-interruptible wait in the
primary actions and CLOSED in its required follow-up. SF-to-Column preparation
retains SF close first and Column close as required follow-up even if the SF
close fails. An already-closed Column yields no redundant motion command.
A future runner must attempt required follow-up on primary failure as well as
normal completion, propagate either failure, and block all later operations.

Aspirating decreases pump coordinates and dispensing increases them. Conversion
uses exact rational arithmetic from the supplied Decimal calibration and volume.
Unrepresentable fractional steps are rejected, not rounded. Every target must
fit both the configured working range and LABFORGE/1 `1..20500`. In particular,
nominal full-span 20 ml aspiration from 20500 using 1025 steps/ml would target
zero and is rejected. HOME is never substituted for that transfer. A later
milestone must explicitly settle working margins/cycle capacity and any
quantization policy; this checkpoint does not change physical calibration.

Already-reached rotary-valve and Column targets are omitted because firmware
rejects redundant positioning. Empty scheduler operations remain in the plan.
Carousel fraction numbers map from the explicit physical starting tube, with
40-to-1 wrap and at most 40 fractions. The compiler requires a projected
completed collection and closed Column before each carousel move.

All output actions are immutable. Predicted final positions apply only if the
whole plan executes successfully; they are neither observations nor live state.

## Identity and remaining runtime boundary

Action UUIDs are deterministic from the phase ID, operation number, and action
slot. Re-preparing identical input preserves IDs; changing arguments in the same
slot conflicts with the existing durable Arduino journal. Skipped valve actions
do not renumber the IDs of other valve actions.

This is NOT durable exactly-once execution. Before connecting this output to the
real executor, the next milestone must:

1. Persist the complete immutable plan and assumptions before any physical action,
   and reject reusing a phase identity with changed order, omissions, or input.
2. Establish/validate current references, physical readiness, route switching
   policy, and boot/session identity. Never promote these offline assumptions to
   trusted machine state or re-plan from projected positions after failure.
3. Exclude interleaving Service/other actuator commands for the whole sequence,
   including the independently connected SF Dynamixel valve.
4. Persist each low-level intent before transmission and advance only after its
   correlated terminal COMPLETED result. Unknown outcomes must not be retried.
5. Preserve required-follow-up and Stop semantics, including failure/unknown
   during a required close. A host SF action ID alone is not a durable Dynamixel
   journal; that integration remains required.
6. Integrate the runner with the existing phase coordinator and API. This module
   is deliberately not plugged into either one yet.

Physical V8 repair and retest, route validation, pump HOME boundary regression,
wet calibration, Reactor mixer commissioning, and live UI integration remain
separate. No hardware readiness is claimed by this checkpoint.

## Verification and independent review focus

Verified on 2026-09-26: 46 focused tests, 1126 complete backend tests, Ruff,
and `git diff --check` pass. No UI/firmware code changed and no hardware was
accessed.

Tests exercise existing P1 solvent/reagent and P2 transfer builders, protected
SF actions, Column collection, all eight nominal routes, exact volume conversion,
unknown references, wrong route/pump/direction, out-of-range and zero targets,
repeated/no-op targets, carousel wrapping, stable/conflicting identities, and
LABFORGE/1 parser acceptance including the maximum-length phase ID.

Review this boundary before runtime integration, focusing on topology-derived
final targets versus unverified switching order, pump endpoint/quantization
rejection, protected-operation structure, and identity/whole-plan persistence.
