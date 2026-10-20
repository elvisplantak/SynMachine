# Demo routes and switching inventory — 2026-10-06

Scope: read-only reconstruction of accepted backend
`1c0e906ac2ad440ea741032192c29a67ab771739`, against firmware
`HARDWARE_CONFIRMATIONS.md`. This document contains code-derived targets,
application sequence and explicitly hypothetical switching proposals. It does
not authorize physical execution or fill unconfirmed route configuration.

## User-selected nominal pump range

On 2026-10-06 the user selected the existing supervised-demo approximation for
both P1/P2: full chamber coordinate 0, empty chamber coordinate 20500, nominal
working volume 20 ml, 1025 steps/ml and no additional endpoint reserve. Precise
measured calibration is deferred. This is a `DEMO_NOMINAL` decision, not a
`WORKING_VERIFIED` calibration or new measured-volume evidence.

The coordinate decision does not change the current command contract:
`PUMP_MOVE_ABSOLUTE_STEPS` accepts 1..20500; zero requires `PUMP_HOME`.
`command_planning._Planner._pump` rejects an ordinary transfer targeting zero.
Consequently a nominal 20 ml aspiration from 20500 produces target 0 and is
currently rejected, even though the calibration model accepts these endpoints.
No protocol/planner/firmware change or implicit HOME substitution is made here.
A later integration must address full-stroke cycle planning explicitly if needed.

## All route targets already present in code

Angles below are final target sets, not an ordered switching procedure. Valve
targets omitted from a route are left at their existing positions. Nominal valve
mapping is 90 degrees = k1-k3 and 180 degrees = k1-k2; HOME 0 is closed.

| Route ID | Nominal fluid path | Final targets, unordered |
| --- | --- | --- |
| `P1_TO_WASTE` | P1 -> V1 -> V2 -> Waste | V1=180, V2=180 |
| `P2_TO_WASTE` | P2 -> V3 -> V7 -> V8 -> V5 -> Waste | V3=180, V7=90, V8=90, V5=180 |
| `S_TO_P1` | S -> V6 -> V1 -> P1 | V6=180, V1=90 |
| `B1_TO_P1` | B1 -> V4 -> V6 -> V1 -> P1 | V4=180, V6=90, V1=90 |
| `B2_TO_P1` | B2 -> V4 -> V6 -> V1 -> P1 | V4=90, V6=90, V1=90 |
| `P1_TO_REACTOR` | P1 -> V1 -> V2 -> Reactor inlet | V1=180, V2=90 |
| `REACTOR_TO_P2` | Reactor outlet -> V3 -> P2 | V3=90 |
| `P2_TO_SF_TOP` | P2 -> V3 -> V7 -> SF top | V3=180, V7=180 |
| `SF_BOTTOM_TO_P2` | SF bottom -> SF bottom valve -> V8 -> V7 -> V3 -> P2 | V3=180, V7=90, V8=180 |
| `P2_TO_COLUMN` | P2 -> V3 -> V7 -> V8 -> V5 -> Column inlet | V3=180, V7=90, V8=90, V5=90 |

Source: `app/hardware/command_planning.py` `_ROUTE_TARGETS`, derived from the
documented tubing graph. Current physical actuation/flow and safe intermediate
connections cannot be established from this table alone.

## Existing orders and logical proposals

`RouteSequence.targets` supplies one explicit order per destination route.
The planner uses that order, skips targets already reached and awaits command
completion through the existing executor before a pump action. It has no default
order and does not automatically isolate all other valves or insert HOME/closed
positions between routes. A proposal must therefore be assessed against each
applicable previous valve state, including restart/recovery paths.

The following are the orders already used in
`tests/test_command_planning.py::ROUTES`. They are explicitly hypothetical test
data. They also illustrate a logical proposal to prepare the selected source or
destination away from the pump first, and switch the valve nearest the pump last.
That rationale alone does not prove safe transient or passive fluidic behavior.

| Destination route | Existing hypothetical test order / proposal for discussion |
| --- | --- |
| `P1_TO_WASTE` | V2=180 -> V1=180 |
| `P2_TO_WASTE` | V5=180 -> V8=90 -> V7=90 -> V3=180 |
| `S_TO_P1` | V6=180 -> V1=90 |
| `B1_TO_P1` | V4=180 -> V6=90 -> V1=90 |
| `B2_TO_P1` | V4=90 -> V6=90 -> V1=90 |
| `P1_TO_REACTOR` | V2=90 -> V1=180 |
| `REACTOR_TO_P2` | V3=90 |
| `P2_TO_SF_TOP` | V7=180 -> V3=180 |
| `SF_BOTTOM_TO_P2` | V8=180 -> V7=90 -> V3=180 |
| `P2_TO_COLUMN` | V5=90 -> V8=90 -> V7=90 -> V3=180 |

Keep these out of `candidate_configuration.route_sequences` until explicitly
confirmed for the intended physical demo. The confirmed historical dry Waste
setups differ: on 2026-08-08 the user verified HOME/set V1 then V2 before P1
HOME, and HOME/set V3 then V7 then V8 then V5 before P2 HOME. Those setup records
are not silently replaced by the opposite test order; neither establishes every
entry into Waste from an active process route.

## Run sequence and actually used transitions

Every syringe cycle is select aspiration route -> aspirate -> select dispense
route -> dispense. A further cycle selects the aspiration route again.

| Run stage | Route sequence per transfer cycle |
| --- | --- |
| Solvent addition | `S_TO_P1` -> `P1_TO_REACTOR` |
| B1 addition | `B1_TO_P1` -> `P1_TO_REACTOR` |
| B2 addition | `B2_TO_P1` -> `P1_TO_REACTOR` |
| Reactor to SF | `REACTOR_TO_P2` -> `P2_TO_SF_TOP` |
| SF to Column | `SF_BOTTOM_TO_P2` -> `P2_TO_COLUMN` |

B1/B2 order is configurable; zero-volume additions produce no transfer cycles.
Delay/reaction/SF mixing/settling/fraction collection do not select new V1-V8
routes. Routes left by the preceding phase/run still matter for the next entry.
Initial READY checks fresh references; it does not physically set a Waste route.

Per pump, the distinct normal-run edges to assess are:

- P1: `S_TO_P1` -> `P1_TO_REACTOR` and its reverse when repeated;
  `B1_TO_P1` -> `P1_TO_REACTOR` and its reverse;
  `B2_TO_P1` -> `P1_TO_REACTOR` and its reverse. Reverse edges include entry into
  later additions or a new run; no direct B1 -> B2 switch is scheduled.
- P2: `REACTOR_TO_P2` -> `P2_TO_SF_TOP` and its reverse when repeated;
  `P2_TO_SF_TOP` -> `SF_BOTTOM_TO_P2` at the stage boundary;
  `SF_BOTTOM_TO_P2` -> `P2_TO_COLUMN` and its reverse when repeated;
  `P2_TO_COLUMN` -> `REACTOR_TO_P2` on a subsequent run.
- Initial entry uses the fresh declared valve positions, not an assumed prior
  symbolic route. If earlier stages have zero cycles, their route changes do
  not establish an entry state for the first nonzero transfer.

## Flush sequence and additional edges

`MaintenancePlan.operations` first prepares flushing: stop SF mixer, close SF
and Column bottom valves, select P1 Waste/empty P1, then P2 Waste/empty P2,
then establish the explicitly supplied rinse-carousel reference.

The following route sequence is performed twice with the configured liquid
volume and then once with the configured air volume:

1. SF/Waste branch: P1 source -> P1 Reactor (aspirate/dispense),
   P2 Reactor -> P2 SF top (aspirate/dispense),
   P2 SF bottom -> P2 Waste (protected aspirate/dispense).
2. Column branch: P1 source -> P1 Reactor (aspirate/dispense),
   P2 Reactor -> P2 Column (aspirate/dispense),
   drain Column into the aligned rinse tube and close its bottom valve.

The P1 source is `S_TO_P1` for the two liquid cycles and `P1_TO_WASTE` for
the air cycle. The air-source designation is code policy, not independent proof
that the installed Waste route can safely supply air. Tube changes occur after
the first and second Column drains with the Column bottom valve closed.

Additional per-pump edges beyond the normal-run set:

- Entry from each possible interrupted/current route into P1/P2 Waste during
  flush preparation; Stop can leave an aspiration or dispense route selected.
- P1 `P1_TO_WASTE` -> `S_TO_P1` after preparation;
  `P1_TO_REACTOR` -> `P1_TO_WASTE` for air;
  `P1_TO_WASTE` -> `P1_TO_REACTOR` after aspirating air.
- P2 `P2_TO_WASTE` -> `REACTOR_TO_P2`;
  `SF_BOTTOM_TO_P2` -> `P2_TO_WASTE`;
  `REACTOR_TO_P2` -> `P2_TO_COLUMN`.
  `P2_TO_COLUMN` -> `REACTOR_TO_P2` also occurs between rinse branches/cycles.

Flush currently has no B1/B2-source aspiration cycle. Finishing Flush leaves
P1's last selected route toward Reactor and P2's toward Column, rather than
automatically reselecting Waste.

## Recovery entry and existing constraints

Recovery stops the SF mixer, closes the SF bottom valve, HOMEs/closes Column,
then HOMEs each V1-V8 in the explicitly configured order. It selects P1 Waste,
HOMEs/empties P1, then selects P2 Waste and HOMEs/empties P2, then establishes
the explicitly confirmed manual carousel reference. The overall valve HOME
order remains unconfirmed for this profile. Recovery can begin with unknown
references; neither the test order V1..V8 nor a historical setup grants approval
to HOME from every unknown fluidic condition.

Before P2 switching the planner requires SF bottom CLOSED. Reactor/SF transfer
also requires Reactor mixer stopped; Column filling requires Column CLOSED.
Protected SF aspiration opens SF bottom only for aspiration and attempts closing
it before the next route. Collection closes Column before carousel movement.
These existing command sequencing checks do not establish valve sealing,
intermediate port connections or passive movement while pumps are stationary.

Remaining physical input is confirmation/correction of the intended valve
switching orders for these actual entries, including any required isolation not
expressible by today's exact-target-only `RouteSequence`. The inventory can be
used route by route; the user need not reconstruct topology or algorithm phases.


## Actual switching cases for discussion — 2026-10-06

Status: `PROPOSED_NOT_PHYSICALLY_CONFIRMED`. No candidate route targets or
execution code is changed. Tables use the explicit hypothetical orders above
and the planner's actual no-op rule. They describe endpoint commands only,
not hydraulic behavior during rotation. Pumps are not commanded to move until
the route operations complete.

`?` means the previous symbolic route does not constrain that valve. It does
not mean a runtime may use an untrusted position: RUN still needs a complete
fresh reference or retained same-session state. A conditional target becomes
a command only when the actual known position differs. Valves not in the
destination route keep their positions, even if omitted from the last column.

These are 24 distinct route-history cases to discuss: 12 normal-run cases,
six additional flush cases and six additional Waste-preparation entries.
Repeated destination selections add no changes when all targets are reached.
Fresh startup can provide other position combinations; those entries and
Recovery from unknown references are separate from these history cases.

### Normal run, repetition and next-run boundaries

| Previous route | Next route | Commands in hypothetical order | Already at target; no command |
| --- | --- | --- | --- |
| `S_TO_P1` | `P1_TO_REACTOR` | V2=?->90 (if different); then V1=90->180 | none |
| `P1_TO_REACTOR` | `S_TO_P1` | V6=?->180 (if different); then V1=180->90 | none |
| `B1_TO_P1` | `P1_TO_REACTOR` | V2=?->90 (if different); then V1=90->180 | none |
| `P1_TO_REACTOR` | `B1_TO_P1` | V4=?->180 (if different); then V6=?->90 (if different); then V1=180->90 | none |
| `B2_TO_P1` | `P1_TO_REACTOR` | V2=?->90 (if different); then V1=90->180 | none |
| `P1_TO_REACTOR` | `B2_TO_P1` | V4=?->90 (if different); then V6=?->90 (if different); then V1=180->90 | none |
| `REACTOR_TO_P2` | `P2_TO_SF_TOP` | V7=?->180 (if different); then V3=90->180 | none |
| `P2_TO_SF_TOP` | `REACTOR_TO_P2` | V3=180->90 | none |
| `P2_TO_SF_TOP` | `SF_BOTTOM_TO_P2` | V8=?->180 (if different); then V7=180->90 | V3=180 |
| `SF_BOTTOM_TO_P2` | `P2_TO_COLUMN` | V5=?->90 (if different); then V8=180->90 | V7=90, V3=180 |
| `P2_TO_COLUMN` | `SF_BOTTOM_TO_P2` | V8=90->180 | V7=90, V3=180 |
| `P2_TO_COLUMN` | `REACTOR_TO_P2` | V3=180->90 | none |

### Additional flushing transitions

| Previous route | Next route | Commands in hypothetical order | Already at target; no command |
| --- | --- | --- | --- |
| `P1_TO_WASTE` | `S_TO_P1` | V6=?->180 (if different); then V1=180->90 | none |
| `P1_TO_REACTOR` | `P1_TO_WASTE` | V2=90->180 | V1=180 |
| `P1_TO_WASTE` | `P1_TO_REACTOR` | V2=180->90 | V1=180 |
| `P2_TO_WASTE` | `REACTOR_TO_P2` | V3=180->90 | none |
| `SF_BOTTOM_TO_P2` | `P2_TO_WASTE` | V5=?->180 (if different); then V8=180->90 | V7=90, V3=180 |
| `REACTOR_TO_P2` | `P2_TO_COLUMN` | V5=?->90 (if different); then V8=?->90 (if different); then V7=?->90 (if different); then V3=90->180 | none |

### Additional Waste-preparation entries

| Previous route | Next route | Commands in hypothetical order | Already at target; no command |
| --- | --- | --- | --- |
| `S_TO_P1` | `P1_TO_WASTE` | V2=?->180 (if different); then V1=90->180 | none |
| `B1_TO_P1` | `P1_TO_WASTE` | V2=?->180 (if different); then V1=90->180 | none |
| `B2_TO_P1` | `P1_TO_WASTE` | V2=?->180 (if different); then V1=90->180 | none |
| `REACTOR_TO_P2` | `P2_TO_WASTE` | V5=?->180 (if different); then V8=?->90 (if different); then V7=?->90 (if different); then V3=90->180 | none |
| `P2_TO_SF_TOP` | `P2_TO_WASTE` | V5=?->180 (if different); then V8=?->90 (if different); then V7=180->90 | V3=180 |
| `P2_TO_COLUMN` | `P2_TO_WASTE` | V5=90->180 | V8=90, V7=90, V3=180 |

### Three concrete examples

1. **Solvent aspiration -> Reactor dispense.** After `S_TO_P1`, V1=90 and
   V6=180. Propose V2->90 if required, then V1 90->180, then dispense P1.
   If V2 was already 90, only V1 moves. On returning to solvent, V6 remains
   180 and only V1 180->90 is needed. This is why first entry and a repeated
   cycle can have different command counts without a different route.
2. **SF top -> SF bottom aspiration.** After `P2_TO_SF_TOP`, V3=180 and
   V7=180. Propose V8->180 if required, then V7 180->90. V3 remains 180:
   it is not automatically closed and reopened. SF bottom must remain CLOSED
   throughout switching, open only for protected P2 aspiration, then close.
3. **SF bottom aspiration -> Column dispense.** After `SF_BOTTOM_TO_P2`,
   V3=180, V7=90 and V8=180. With SF bottom CLOSED and Column bottom CLOSED,
   propose V5->90 if required, then V8 180->90. V3/V7 remain unchanged.
   The unchanged valves keep connecting P2 to the branch being switched;
   their presence in the destination order does not provide isolation.

### Confirmed behavior and remaining procedure decisions

- On 2026-10-06 the user confirmed that installed V1-V8 interrupt the old
  connection before opening the new one during 90/180 switching. This
  resolves that particular uncertainty; it does not confirm pressure/sealing
  or approve an entire ordered procedure. Canonical record: firmware
  `HARDWARE_CONFIRMATIONS.md`, User-confirmed V1-V8 connection change behavior.
- Whether the selected stationary-pump procedure is acceptable for the actual
  fluid heights/pressure, including the unchanged V3/V7 cases above. No
  gravity/siphon/pressure behavior is inferred here.
- Whether switching needs explicit isolation beyond final route targets.
  Current `RouteSequence` accepts only the final target set once per valve;
  it cannot express V1->0 then V1->180 or closing an otherwise omitted valve.
  Also, valve position 0 invokes HOME in the existing firmware contract; it
  is not an independently verified instantaneous shutoff operation.
- Safe entry for fresh declared positions and unknown-reference Recovery,
  including the overall valve HOME order. Historical dry Waste setup orders
  remain evidence for their recorded setups only.

## Complete destination-order proposal for user confirmation

With the user-confirmed old-before-new connection change, propose the ten
destination orders listed in the existing order table above for the demo.
Keep pumps stationary throughout route switching, await each command result,
retain the existing SF/Column closure and mixer checks, and move a pump only
after all required route commands complete. Already-reached targets remain
no-ops. No additional zero/HOME/isolation movement is proposed here.

These are proposed ordered procedures, not physical confirmations. Waste
orders here prepare V2 before V1, and V5/V8/V7 before V3; they differ from
the historical dry HOME-and-set setup order and therefore need explicit
acceptance for this procedure. Previous dry setups remain recorded unchanged.

The actual current positions still determine omitted commands. If the user
requires disconnecting an already-connected pump/branch first, that is a
different procedure requiring an explicit extension of the current planner.
Do not translate that requirement into an implicit HOME command.

Fresh startup entries and unknown-reference Recovery remain separate gates.
The overall valve HOME order is not selected by this proposal. A generic
instruction to continue or confirmation of internal valve behavior does not
approve these proposed orders. Until the user accepts/corrects them, keep
all physical candidate `route_sequences.targets` and the ordered/HOME
confirmation field unset. Physical execution still needs separate approval.


## User acceptance and planned supervised verification — 2026-10-06

The user explicitly accepted the exact ten destination orders and reviewed
stationary-pump procedure above. This supersedes the pending acceptance status
in the preceding proposal sections. Canonical record: firmware
`HARDWARE_CONFIRMATIONS.md`, User-approved demo destination switching orders.
The physical worksheet now contains these approved ordered targets, transcribed
from the accepted proposal. Existing test orders are not a source of approval.
The complete profile remains incomplete/non-activatable; no runtime changed.

Approval of destination switching does not select the overall valve HOME order,
establish current references, approve liquid delivery/cleaning results or grant
permission to open live ports or move devices. No new physical result is claimed.

Suggested next session: supervised staged checking on 2026-10-07, with no motion
in this planning session. Begin with motor power off: identify the installed
firmware/device connections, actual contents and mechanical readiness; separate
the previous fake browser launcher from a deliberately configured real Service
session. Do not convert `tests.browser_check` into a real-device launcher.

Before the first HOME/movement, agree on the concrete dry condition, fresh
reference establishment and exact bounded commands; obtain authorization plus
new motor-power readiness. The overall startup/Recovery valve HOME procedure is
still a separate decision. Current references must come from this session, not
old positions or durable historical success alone.

First physical objective is valve switching only with pumps stationary and
appropriate empty/dry conditions confirmed: establish references, then inspect
selected P1 transitions before P2 transitions. At each step compare command
completion with the user's observed valve position/path. No result is silently
promoted into hydraulic/wet proof. Subsequent dry-air pump operation needs its
own verified Waste/source path and explicitly agreed travel.

Only after dry checking and the remaining input/profile gates may a separate
supervised small nominal-volume liquid test check S -> P1 -> Reactor, then
B1/B2 paths, then Reactor -> P2 -> SF and SF -> P2 -> Column. Agree the liquid,
volume, destination capacity and actual readiness before that test. Full 20 ml
ordinary aspiration is still rejected because zero is HOME-only; do not silently
substitute HOME. No complete autonomous RUN/Recovery/Flush is promised for the
next session while adapter/current-reference/HOME and flush inputs remain missing.

Remaining integration inputs include installed adapter identity/timing, actual
current-reference acquisition, startup/Recovery HOME order, rinse volumes/drain/
tube settings and explicit real-profile composition. Preparation and fake tests
precede any activation of that composition. Motor-power readiness must be newly
confirmed before each powered physical test as required by the hardware record.
