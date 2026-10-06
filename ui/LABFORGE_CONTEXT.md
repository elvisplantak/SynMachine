# LabForge UI context

This project is a React + Vite + TypeScript frontend mockup for the broader LabForge / chemputer hardware-control project.

Project folder:

    ~/Documents/labforge-ui

Development server:

    npm run dev

Local URL:

    http://localhost:5173/

## Broader LabForge architecture

LabForge is intended to become a software-controlled modular lab automation system.

Expected architecture:

    React frontend
      -> FastAPI backend + LabForge core
      -> pyserial
      -> Arduino Mega
      -> valves, syringe pumps, switches, actuators

Meaning:

- React frontend visualizes the system and sends high-level user actions.
- Python/FastAPI backend is the “brain”.
- Arduino Mega is the low-level executor.
- Arduino should execute low-level valve/pump/switch commands.
- Arduino should not contain high-level protocol intelligence.
- React should not directly decide unsafe hardware actions.
- Later, UI commands, text commands, protocol builder commands, and voice commands should all go through the same backend parser/planner/safety layer.
- Voice input must never bypass backend safety/parser/firewall logic.
- For now, mock/demo state in React is acceptable.

## Main UI goal

Build a dark-mode “instrument panel” UI for LabForge.

The UI should feel like:

- lab instrument dashboard
- chemputer control cockpit
- physical process-flow diagram
- understandable to a chemist who is not a programmer

The main visual idea is:

    show the physical flow of liquid through the system

The central UI element should be an SVG scheme showing:

- reagent bottles
- one shared solvent bottle
- 3-way valves
- syringe pumps
- reactor
- separatory funnel
- column
- waste
- fraction collector

The UI should clearly show:

- current action
- active liquid route
- estimated fluid movement
- pump state
- valve state
- protocol step
- log/telemetry

## User modes

There are two mental models.

### Chemist / normal user mode

The chemist should see high-level workflow meaning:

    Transfer B1 to Reactor
    Transfer Reactor to SF
    Transfer SF bottom phase to Column
    Collect fraction
    Wash line

The chemist should not need to think primarily in terms of:

    V4 = 180°
    V6 = 90°
    P1 aspirate

Those details can exist in technical/service mode.

### Technical / service mode

Service mode can show:

- valve names V1...V8
- port labels k1/k2/k3
- valve angles 0°/90°/180°
- direct hardware controls
- pump aspirate/dispense controls
- homing actions
- debug logs

For now, because the SVG/topology is still being designed, it is acceptable to keep port labels visible.

Later we may add a toggle:

    User mode / Technical mode

## Intended screens

The UI will likely have multiple screens later.

### 1. Dashboard / Run screen

Main screen for a chemist.

Should contain:

- central SVG physical scheme
- current protocol/action
- active route
- current step
- volume
- pump status
- alerts
- run/pause/abort controls

### 2. Protocols screen

For selecting and viewing protocols.

Examples:

    Fill reactor demo
    Prime P1
    Reactor to SF
    Reactor to Column
    Full colored-water workflow

Protocol steps should be human-readable:

    1. Add 2.0 ml B1 to reactor
    2. Add 5.0 ml S to reactor
    3. Wait 10 s
    4. Transfer reactor contents to SF
    5. Transfer SF bottom phase to column

### 3. Route Test screen

For testing source/destination transfers.

Example form:

    Source: B1
    Destination: Reactor
    Volume: 2.0 ml

    [Preview route]
    [Execute]

Preview should explain both high-level and technical route.

Example:

    This transfer is possible.

    Phase 1: B1 -> V4 -> V6 -> V1 -> P1
    Phase 2: P1 -> V1 -> V2 -> Reactor

### 4. Manual / Service screen

For direct hardware debugging.

Examples:

    Home V1
    Set V1 to 90°
    Set V1 to 180°
    Aspirate P1 1 ml
    Dispense P1 1 ml

This screen should clearly look like service mode and not normal chemist workflow.

### 5. Logs screen / bottom log bar

Logs should eventually have two levels.

Human log:

    Added 2.0 ml B1 to reactor.
    Transferred reactor contents to SF.

Technical log:

    V4=180, V6=90, V1=90, P1 aspirate 2.0 ml
    ACK V4
    DONE P1

## Layout direction

The preferred visual layout is left-to-right.

Preserve this visual flow:

    B1 / B2 / S
      -> P1 input branch
      -> P1 syringe pump
      -> Reactor
      -> P2 output branch
      -> Separatory funnel / Column / Fractions

## Current physical machine state

As explicitly confirmed by the user on 2026-07-21, the physical tubing has been connected according to the approved LabForge v1 target topology. The confirmed present physical topology is:

    V1.k1 <-> P1
    V1.k2 <-> V2.k1
    V1.k3 <-> V6.k1

    V2.k1 <-> V1.k2
    V2.k2 <-> shared Waste
    V2.k3 <-> Reactor R_IN

    V3.k1 <-> P2
    V3.k2 <-> V7.k1
    V3.k3 <-> Reactor R_OUT

    V4.k1 <-> V6.k3
    V4.k2 <-> B1
    V4.k3 <-> B2

    V5.k1 <-> V8.k3
    V5.k2 <-> shared Waste
    V5.k3 <-> Column inlet

    V6.k1 <-> V1.k3
    V6.k2 <-> shared solvent S
    V6.k3 <-> V4.k1

    V7.k1 <-> V3.k2
    V7.k2 <-> SF_TOP_IN
    V7.k3 <-> V8.k1

    V8.k1 <-> V7.k3
    V8.k2 <-> SF_BOTTOM_OUT
    V8.k3 <-> V5.k1

The confirmed bottom paths are:

    SF bottom
      -> SF_BOTTOM_VALVE
      -> SF_BOTTOM_OUT
      -> V8.k2

    Column bottom
      -> COLUMN_BOTTOM_VALVE
      -> Fractions / carousel

There is one shared Waste destination. The Column bottom does not connect to Waste.

## Approved target LabForge v1 topology

The approved logical topology uses one shared Waste destination and one shared solvent source `S`. The user-confirmed present physical tubing topology now matches this approved target. This agreement does not by itself verify valve angles, actuation, liquid delivery, calibration, interlocks, or end-to-end execution.

### Target P1 reagent / solvent loading branch

    B1 -> V4.k2
    B2 -> V4.k3
    V4.k1 -> V6.k3

    S -> V6.k2
    V6.k1 -> V1.k3

    P1 -> V1.k1
    V1.k2 -> V2.k1

    V2.k3 -> Reactor
    V2.k2 -> Waste

Functional meaning:

- `V4` selects `B1` or `B2`.
- `V6` selects the `B1/B2` branch or shared solvent `S`.
- `V1` switches between aspiration from the selected source and dispensing from `P1`.
- `V2` selects `Reactor` or `Waste`.
- `S` is the single solvent source used for both reaction dilution and washing.
- `V2 -> Waste` can be used for priming, bubble removal, and washing liquid disposal.

### Target P2 reactor / downstream branch

The approved target P2 topology is:

    Reactor R_OUT -> V3.k3
    P2 -> V3.k1
    V3.k2 -> V7.k1

    V7.k2 -> SF_TOP_IN
    V7.k3 -> V8.k1

    V8.k2 -> SF_BOTTOM_OUT
    V8.k3 -> V5.k1

    V5.k2 -> Waste
    V5.k3 -> Column

    Column -> COLUMN_BOTTOM_VALVE -> Fractions / carousel

Functional meaning:

- `V3` switches `P2` between aspiration from the reactor and the downstream branch.
- `V7` selects `SF_TOP_IN` or the downstream `V8` branch.
- `V8` connects either `SF_BOTTOM_OUT` or the final destination branch.
- `V5` is now in the P2 branch and selects `Waste` or `Column`.
- The column bottom outlet does not connect to Waste.
- The column bottom outlet routes through `COLUMN_BOTTOM_VALVE` to the fraction carousel.

## UI implementation status

The current UI represents the approved target LabForge v1 topology for both P1 and P2. In particular, it shows `B2 -> V4.k3`, one shared solvent source `S -> V6.k2`, and `V5` in the P2 branch. The user-confirmed present physical tubing topology now matches this representation.

The V3 mapping shown in the UI represents the approved target topology:

    Reactor R_OUT -> V3.k3
    P2 -> V3.k1
    V3.k2 -> V7.k1

## Confirmed physical build and remaining commissioning

The physical tubing matches the approved LabForge v1 topology, including `V3.k2 <-> V7.k1`, one shared solvent source `S`, and `V5` in the downstream P2 branch. Main mechanical assembly, tubing work, and wiring are substantially complete. The valves and pumps have been leak-tested, and no leaks were observed during that testing. Tested actuator motors operated correctly during the performed manual and commissioning checks.

These confirmations establish physical build progress, observed leak-test results, and basic observed motor movement only. They do not prove that every valve reaches the correct angle, every fluidic route is correct, homing is safe, either bottom valve is fully commissioned, or either pump delivers a calibrated volume.

The following remain separate pending checks:

- individual liquid-route testing
- verification of every valve angle and corresponding physical route
- safe homing-route verification
- complete `SF_BOTTOM_VALVE` actuation verification
- complete `COLUMN_BOTTOM_VALVE` actuation verification
- pump volumetric calibration, final operational calibration, and working limits
- safe execution interlocks
- end-to-end backend-to-firmware hardware execution
- automatic phase detection
- measured delivered-volume confirmation
- one remaining motor connection / pin-documentation item; the available source of truth does not identify the actuator

The confirmed topology is not hardware execution permission. Symbolic backend operation plans also do not authorize hardware execution.

### Shared Waste and screening workflow

- There is only one visual and logical `Waste` destination.
- The shared Waste destination is only for `V2 -> Waste` and `V5 -> Waste`.
- The column bottom outlet does not connect to Waste.
- `Column -> COLUMN_BOTTOM_VALVE -> Fractions / carousel`.
- `B1` and `B2` containers and exposed inlet tube ends are manually replaced and cleaned between different screening series.
- During one screening series using the same stock solutions, the `B1` and `B2` inlet branches may remain primed.
- Between screening runs, wash `P1`, the reactor, and the common path with solvent `S`.
- Full `B1` and `B2` branch cleaning is done after the screening series, not necessarily between every run in the same series.

The user likes the current left-to-right spacing. Do not compress the layout unnecessarily unless explicitly asked.

A possible final UI layout:

    +------------------------------------------------------+
    | LabForge Console            Dashboard Protocols Logs |
    +------------------------------------------------------+
    |                                                      |
    |  LEFT PANEL       CENTER SVG SCHEME       RIGHT PANEL|
    |                                                      |
    |  protocol         physical flow           pump state |
    |  current step     active route            reactor    |
    |  volume           valves/pumps            alerts     |
    |  run/pause        liquid movement         SF/column  |
    |                                                      |
    +------------------------------------------------------+
    | Command input / telemetry log                        |
    +------------------------------------------------------+

For now, the current focus is the central SVG scheme.

## SVG design approach

The central scheme is built using SVG.

Preferred coordinate convention:

    x negative = left
    x 0        = center
    x positive = right

    y negative = up
    y 0        = center
    y positive = down

A useful SVG viewBox for the current scheme:

    <svg viewBox="-900 -420 1800 840">

The coordinate grid was useful during design, but it should be hideable later. In demo mode, only the scheme should remain.

## Visual style

Current preferred style:

- dark background
- glowing cyan/blue active paths
- inactive pipes beige/gray
- light mechanical modules
- subtle shadows
- instrument-panel / lab-device feel
- clean enough for a chemist
- not toy-like
- not pure programmer/debug UI

Active route color:

    cyan / blue glow

Inactive pipe color:

    beige / gray

Valve body style:

    light industrial mechanical block

## Valve design

Valves should not look like plain circles.

Preferred valve style:

    industrial 3-way valve block

A valve should show:

- main body
- 3 visible ports
- label V1, V2, V3...
- port labels k1, k2, k3
- internal active path showing which ports are connected
- closed state indication

Current 3-way valve logic:

    0°   = closed
    90°  = k1 <-> k3
    180° = k1 <-> k2

For technical mode, port labels should be visible:

    k1, k2, k3

Later, user mode may hide these labels.

Important: valve labels V1...V8 must be readable. If labels are too small, increase contrast/size.

## Syringe pumps

P1 and P2 are syringe pumps, not inline pumps.

This is very important.

A transfer is not simply:

    source -> destination

It has two phases:

    Phase 1: SOURCE -> SYRINGE_PUMP
    Phase 2: SYRINGE_PUMP -> DESTINATION

Example:

    B1 -> P1
    P1 -> Reactor

The UI should eventually represent aspirate/dispense phases.

Current pump symbols are acceptable as early placeholders, but later they should look more clearly like syringe pumps.

## Physical topology protection

The current physical topology is documented above in "Current physical machine state".

Preserve these high-level constraints:

- `B1` and `B2` feed `V4`, not separate solvent branches.
- `S` is the only solvent source and feeds `V6`.
- `V5` belongs to the P2 branch as the `Column` / `Waste` selector.
- There is only one shared `Waste` destination.
- `P1` and `P2` are syringe pumps and must not be treated as inline pumps.
- The left-to-right physical process direction should stay readable.

### Reactor

    R_IN -> Reactor -> R_OUT

Important P1 visual correction:

    B1 -> V4.k2
    B2 -> V4.k3
    V4.k1 -> V6.k3
    S -> V6.k2

Important P2 visual correction:

    V8.k3 -> V5.k1
    V5.k2 -> Waste
    V5.k3 -> Column

The visual should not show multiple Waste bottles or legacy split solvent bottles.

## Current implementation status

The current UI is mostly in:

    src/App.tsx
    src/App.css

Current components or intended components:

    Pipe
    Valve
    Bottle
    Pump
    Reactor
    Separator
    Column
    Waste
    Fractions

Later, once the design stabilizes, these should be split into separate files, for example:

    src/components/Valve.tsx
    src/components/Pump.tsx
    src/components/Bottle.tsx
    src/components/Pipe.tsx
    src/components/Reactor.tsx
    src/components/Separator.tsx
    src/components/Column.tsx
    src/components/Waste.tsx
    src/components/Fractions.tsx
    src/data/topology.ts

Do not refactor into many files unless asked. First keep the UI stable.

## Current Guided Demo system decisions — 2026-07-16

### Current frontend state and implementation focus

The experimental frontend branch contains Dashboard, Protocol Builder, the full Logs draft, the Service draft, the Guided Demo cockpit, and a Guided Demo-specific `Demo Log`. Relevant checkpoints are:

- `377694b Refine Guided Demo cockpit layout`
- `d4e0841 Add Guided Demo log draft`

The complete normal interface remains in the repository. Dashboard, Protocol Builder, full Logs, and Service have not been deleted or abandoned. Current implementation focus is temporarily narrowed to Guided Demo, Demo Log, and the backend and firmware required by those two views.

### Guided Demo purpose and scope

Guided Demo is intended for one authorized remote user to configure and observe one real-time run using colored, low-risk liquids. The current implementation remains frontend-only and does not control hardware.

The intended real demo uses one run, `B1`, `B2`, shared solvent `S`, `P1` transfer into the Reactor, Reactor mixing, `P2` transfer from the Reactor into `SF`, SF mixing, SF settling, nominal transfer of all SF contents to the Column, Column fraction collection, a Reactor camera, and an Overview camera. The system must not claim automatic phase detection, actual phase separation, or measured delivered volume. Physical heating is disabled. Temperature remains a simulated/display-only parameter for demonstrating future UI behavior; it must not produce a heater command.

The ten configured parameters are:

1. B1:B2 volume ratio
2. Total mixture volume
3. Combined B1+B2 volume
4. Addition order
5. Addition speed command
6. Reactor mixing command
7. SF mixing command
8. Simulated target temperature
9. Reaction duration
10. Delay between additions

The system calculates B1 volume, B2 volume, S volume, and total volume. The current ratio is a volume ratio, not a molar ratio, because stock concentrations are not configured.

The current top-level backend phase model is:

1. `READY`
2. `P1_TRANSFER_S_TO_REACTOR`
3. `P1_TRANSFER_FIRST_LIQUID_TO_REACTOR`
4. `DELAY_BETWEEN_ADDITIONS`
5. `P1_TRANSFER_SECOND_LIQUID_TO_REACTOR`
6. `REACTION_HOLD`
7. `P2_TRANSFER_REACTOR_TO_SF`
8. `SF_MIXING`
9. `SF_SETTLING`
10. `P2_TRANSFER_SF_TO_COLUMN`
11. `COLUMN_FRACTION_COLLECTION`
12. `COMPLETED`

`P1` and `P2` are syringe pumps. Aspirate and dispense remain separate symbolic and physical operations inside the relevant transfer phase; they are no longer represented as separate top-level `RunPhase` values. The first and second liquid identities still depend on `AdditionOrder`.

### Parameter locking and phase permissions

After physical execution starts, permanently lock the B1:B2 ratio, total mixture volume, combined B1+B2 volume, calculated B1/B2/S volumes, and addition order.

Phase-dependent controls are:

- Addition speed: editable only during `P1_TRANSFER_FIRST_LIQUID_TO_REACTOR` and `P1_TRANSFER_SECOND_LIQUID_TO_REACTOR`.
- Reactor mixing: editable during Reactor-related phases.
- Delay: editable only during the delay phase.
- Simulated temperature: editable only during Reaction hold.
- Reaction duration / remaining time: editable during Reaction hold.
- SF mixing: editable only during SF mixing.

The preferred UI convention for unavailable controls is a disabled control, a visible lock icon, and a short explanation. A color change is optional. The backend must independently enforce all locks and phase permissions; frontend disabled state is not a safety boundary.

### Topology and hardware verification status

Guided Demo displays the complete approved target P1 and P2/SF topology. The physical tubing, including `V3.k2 <-> V7.k1`, is confirmed connected according to that topology. Main mechanical assembly, tubing work, and wiring are substantially complete. The valves and pumps have been leak-tested with no observed leaks, and tested actuator motors moved correctly during the performed manual and commissioning checks.

Individual liquid-route testing, verification of every valve angle and corresponding route, safe homing-route verification, complete bottom-valve actuation verification, pump volumetric and final operational calibration, working limits, interlocks, end-to-end backend-to-firmware hardware execution, automatic phase detection, and measured delivered-volume confirmation remain pending. One motor connection / pin-documentation item also remains pending; the currently available source of truth does not identify which actuator it concerns. Basic observed motor movement is not proof of correct valve angles, correct fluidic routes, safe homing, fully commissioned bottom valves, or calibrated pump delivery.

### Guided Demo SF-to-Column workflow decisions — 2026-07-22

- `SF` is unpressurized.
- Fill `SF` through `SF_TOP_IN` while `SF_BOTTOM_VALVE` is closed.
- Open `SF_BOTTOM_VALVE` only during aspiration from `SF`.
- Close `SF_BOTTOM_VALVE` before route switching and dispensing.
- Keep `COLUMN_BOTTOM_VALVE` closed while the Column is being filled.
- Open `COLUMN_BOTTOM_VALVE` only during `COLUMN_FRACTION_COLLECTION`.
- Send all nominal `SF` contents to the Column in the current Guided Demo; there is no split to Waste.
- Do not claim automatic phase detection or actual phase separation.
- Keep the Reactor mixer OFF before, during, and after `P2_TRANSFER_REACTOR_TO_SF`.
- Transfer volumes are nominal open-loop values, not measured delivered volumes.

### Demo Log and persistence scope

Guided Demo has a separate simplified `Demo Log` for the remote user. It is distinct from the full application Logs screen and is intended to show configured run values, a human-readable phase/event timeline, control-command changes, phase progress, optional technical details, and future Reactor and Overview camera media.

The current Demo Log uses clearly marked example data and has no backend storage. Initial backend persistence should cover data required by Guided Demo and Demo Log rather than the entire future logging platform.

### Minimal backend focus

The next development focus is a minimal real backend core for Guided Demo and Demo Log, implemented independently of UI component details. Its responsibilities include:

- Guided Demo configuration validation and B1/B2/S volume calculation
- an immutable fluid plan after start
- a run state machine and phase-dependent control policy
- an explicit verified route catalog and operation execution
- serial communication with Arduino Mega
- run and event persistence
- state and event delivery to Guided Demo and Demo Log

Do not implement a universal route planner or complete general protocol engine at this stage. The backend should use logical identifiers such as `P1`, `P2`, `V1`–`V8`, `REACTOR_MIXER`, `SF_MIXER`, and `CAROUSEL`. It must not know Arduino pin numbers. Pin assignments and low-level motor configuration belong in firmware configuration and can be added later without changing the backend state-machine design.

The current project organization plan uses three neighboring but separate Git repositories:

- `~/Documents/labforge-ui`
- `~/Documents/labforge-backend`
- `~/Documents/labforge-firmware`

Together they form one LabForge system, but they are not currently planned as one Git repository.

### Current backend planning progress — 2026-07-22

Backend repository:

    ~/Documents/labforge-backend

Current completed backend branch and commit:

    codex/guided-demo-p2-sf-to-column-operation-plan
    2c18f0a460ec655bd69d917461feeda031717a07
    2c18f0a Add P2 SF-to-Column operation plan

Accepted verification for this commit:

    508 passed
    .venv/bin/ruff check . -> All checks passed!
    git diff --check -> passed

No push or merge was reported.

Completed symbolic operation plans:

- `P1` solvent to Reactor
- `P1` `B1`/`B2` reagent transfers to Reactor
- `P2` Reactor to `SF`
- `P2` `SF` to Column

These symbolic plans are planning artifacts, not a hardware executor and not permission or proof of hardware execution.

The completed `P2_TRANSFER_SF_TO_COLUMN` operation plan adds the logical routes `SF_BOTTOM_TO_P2` and `P2_TO_COLUMN`. These are logical route identifiers only; physical valve angles, Arduino pins, and motor steps are not part of the plan.

The exact scheduler-visible sequence is:

    PREPARE_SF_TO_COLUMN_TRANSFER

    for each transfer cycle:
        SELECT_ROUTE SF_BOTTOM_TO_P2
        ASPIRATE_FROM_SF cycle_volume
        SELECT_ROUTE P2_TO_COLUMN
        DISPENSE P2 cycle_volume

`PREPARE_SF_TO_COLUMN_TRANSFER` is one protected scheduler operation with the required internal sequence:

    SET SF_BOTTOM_VALVE CLOSED
    SET COLUMN_BOTTOM_VALVE CLOSED

There is no normal Stop checkpoint between those two actions. `SF_BOTTOM_VALVE` closes first because `SF` nominally contains liquid and presents the more immediate gravity-flow risk.

`ASPIRATE_FROM_SF` is one protected scheduler operation for every `P2` aspiration cycle, with the required internal sequence:

    OPEN SF_BOTTOM_VALVE
    ASPIRATE P2 cycle volume
    CLOSE SF_BOTTOM_VALVE

There is no normal Stop checkpoint inside this operation. `SF_BOTTOM_VALVE` opens and closes during every aspiration cycle; it does not remain open during route switching or dispensing. `COLUMN_BOTTOM_VALVE` remains closed throughout this phase, and no Waste route is used.

The requested nominal transfer volume is `fluid_plan.total_configured_volume_ml`. It remains a nominal open-loop value, not measured delivered volume. Successful completion must not be described as proof that `SF` is physically empty, measured delivery, automatic phase-boundary detection, or actual phase separation.

Normal `Stop demo` semantics apply at scheduler-operation boundaries: the current scheduler operation may finish, but the next scheduler operation must not start. Therefore:

- Stop during `PREPARE_SF_TO_COLUMN_TRANSFER` allows both required close actions to finish.
- Stop before `ASPIRATE_FROM_SF` does not begin aspiration.
- Stop during `ASPIRATE_FROM_SF` allows valve opening, aspiration, and the required close to finish.
- After that Stop, `SELECT_ROUTE P2_TO_COLUMN` and `DISPENSE` do not begin.
- `P2` may remain nominally full after an aborted protected aspiration; the system must not dispense merely to empty `P2` after Stop.
- Stop during an already-started dispense may allow that dispense to finish, but no next cycle begins.
- After normal abort, the existing lifecycle remains run `ABORTED` and machine `FLUSH_REQUIRED`.

A failed required close is not a successful normal abort. A future executor must fail the protected operation, block route switching and dispensing, stop further plan execution, and propagate a fault. No completed machine-level fault-state redesign is claimed. The exact machine recovery/fault transition remains unresolved and must be completed before hardware execution.

There are no independent valve-position feedback sensors. For the low-risk colored-liquid Guided Demo, after a valve command reports successful completion, software deliberately treats the valve as actually `OPEN` or `CLOSED`. This assumption does not prove physical movement and is not automatically acceptable for serious chemistry.

For `P2_TRANSFER_SF_TO_COLUMN`, zero cycles are a validation error. A zero-volume or zero-cycle request must not succeed as an empty plan, become a close-only transfer plan, or continue toward fraction collection without transferring liquid. The generic `TransferCyclePlan` behavior was not globally changed.

### Next backend safety-design task: `COLUMN_FRACTION_COLLECTION`

The next task is functional and safety design only for `COLUMN_FRACTION_COLLECTION`; it is not implemented or fully designed here. The already accepted high-level intent is:

1. Open `COLUMN_BOTTOM_VALVE`.
2. Collect for the Service-configured fraction duration.
3. Close `COLUMN_BOTTOM_VALVE`.
4. Move the carousel.
5. Reopen only after carousel motion completes.
6. Never move the carousel while the outlet is open.
7. Leave the outlet closed after the final fraction.

Fraction count and fraction duration are Service-configured. Before implementation, discuss protected Stop boundaries around Column valve opening, collection, and closing; Stop while collecting; Column close failure; carousel movement failure; fraction timing semantics; the final-fraction completion race; zero-fraction configuration; whether more protected compound operations are required; exact logical state retained after abort; and interaction with `FLUSH_REQUIRED`.

### Firmware and hardware development

The user has experimentally validated, non-blocking Arduino C++ `Pump` and `Valve` classes. Complete original working files will be supplied later and must be reviewed conservatively before modification; do not assume they require a rewrite. Review should focus on public API, `update()` behavior, homing, debounce, timeout, stop/abort handling, busy/done/error states, volume-to-step conversion, speed updates during movement, and serial integration.

A `Carousel` firmware class will also be required. Do not invent its final behavior before confirming the number of positions, home/index sensing, steps per position, direction policy, and mechanical alignment behavior.

`P1` and `P2` may be developed and tested in parallel. The user intends early testing against the real machine with colored liquids. A detailed user-facing simulated machine is not a priority because P2 is expected to be physically ready shortly. Small test doubles or fake command results remain acceptable for automated backend tests, but must not become a separate simulated product or delay real hardware integration.

### Cameras

Guided Demo uses exactly two planned cameras: Reactor camera and Overview camera. The camera system is separate from the hardware safety-command path. Loss of video must not prevent the local backend from safely controlling or stopping the machine.

## Current colored-liquid demo machine, recovery, flush, and commissioning decisions — 2026-07-17

These decisions apply to the current colored-liquid Guided Demo scope. They are intentionally optimized for a fast, low-risk demo and are not a complete serious-chemistry safety protocol. Exact physical routes must match the approved topology and be physically verified before hardware execution.

### Confirmed P1 and P2 hardware facts and pending calibration

- `P1` and `P2` both use 10 mL syringes and have the same user-confirmed mechanical syringe orientation.
- Position `0` is the home-switch end. Near `0`, the plunger is maximally retracted and syringe chamber volume is maximal.
- Position `20500` is the recovered approximate pushed-plunger position, where chamber volume is minimal.
- Movement toward `0` physically aspirates; movement toward `20500` physically dispenses. These facts apply to both pumps and supersede the older statement that P2 orientation was unconfirmed.
- `20500` is a confirmed recovered software travel value, not a validated volumetric calibration. `steps/ml`, `working_full_position_steps`, and `working_empty_position_steps` remain pending experimental measurement or selection. Working positions must remain slightly inside the physical endpoints.
- Reliable pump speed limits and final step intervals remain pending experimental testing. Speed should later be operator-adjustable only within experimentally validated limits.

### Startup and homing policy

- Normal cold startup requires homing all confirmed motorized valves and both syringe pumps.
- Homing is not repeated before every normal aspiration, dispense, prime, or flush stroke. Normal cycles use the calibrated working stroke inside the physical endpoints.
- Re-homing is required after loss of trusted position, including a power interruption or interrupted low-level motion.
- Pump homing is fluidic: movement toward `0` increases chamber volume and can aspirate from the selected route. A verified safe fluidic route must be configured before homing either pump.
- Exact low-level valve positions for safe pump-homing routes remain pending final physical verification.
- The Column bottom valve homing direction and open/closed mapping remain pending physical confirmation. Its pins, direction, steps, and positions are not yet defined.

### `RunStatus` and `MachineState`

`RunStatus` describes one experiment and retains the lifecycle `CREATED`, `RUNNING`, `PAUSED`, `ABORTING`, `ABORTED`, `COMPLETED`, and `FAULTED`.

The separate colored-demo `MachineState` describes whether the complete machine can accept another operation: `STARTING`, `READY`, `BUSY`, `RECOVERING`, `FLUSH_REQUIRED`, and `FLUSHING`. An old run may remain `ABORTED` or `FAULTED` after the machine later returns to `READY`. A machine-level `FAULTED` state is not defined for this narrow demo; failure of recovery or flushing is deferred to the serious-system design.

- A new run may start only in `READY`; starting it changes the machine to `BUSY`.
- Normal completion returns the machine to `READY`.
- Automatic flushing after every successful run is not required. The operator may manually run `Flush system` when useful.

### `Stop demo`

The user-facing action is named `Stop demo`, not `Stop system`.

1. The user requests `Stop demo` and the run enters `ABORTING`.
2. The current atomic operation is allowed to finish; no next atomic operation starts.
3. The run becomes `ABORTED` and the machine becomes `FLUSH_REQUIRED`.
4. The old run cannot resume. The operator must manually complete `Flush system` before starting a new run.

`Pump.stop()` or `Valve.stop()` must not implement normal `Stop demo` during active motion because that would lose trusted position. An Emergency Stop button and workflow are outside the current Guided Demo scope.

### Automatic recovery after power loss

If power is lost during an active or incomplete run, that run must not resume. On the next startup it is marked `FAULTED`, the machine enters `RECOVERING`, and colored-demo recovery runs automatically:

1. Detect that the previous run or atomic operation did not finish cleanly.
2. Mark the old run `FAULTED`.
3. Restore known valve positions through homing.
4. Configure verified safe routes for the pumps.
5. Home `P1` and `P2`.
6. Empty unknown pump contents toward Waste.
7. Stop automatic recovery.
8. Enter `FLUSH_REQUIRED`.

Recovery does not automatically run the full rinse protocol. The operator must manually start `Flush system`, and a new run is forbidden until it finishes successfully. Exact valve positions and low-level recovery operations remain future executor and firmware work.

The Waste tube will terminate near the top of the Waste bottle, above the maximum permitted liquid level, and the container must not be hermetically sealed. Aspirating through the Waste route is intended to draw air, not liquid Waste; this air-gap route supports safe pump recovery concepts and the final air purge. This is a colored-liquid demo decision, not a validated serious-chemistry waste design.

### Manually triggered `Flush system`

`Flush system` is a high-level local-operator action allowed only in `READY` or `FLUSH_REQUIRED`. Its transitions are `READY` or `FLUSH_REQUIRED` -> `FLUSHING` -> `READY` after successful completion. It is unavailable during an active run, automatic recovery, or another flush.

The default colored-demo plan uses two liquid flush cycles. Each cycle contains:

1. SF/Waste-path pass: `S -> P1 -> Reactor -> P2 -> SF/Waste path -> Waste`.
2. Column-path pass: `S -> P1 -> Reactor -> P2 -> Column -> carousel rinse tube`.

After both cycles, a final air purge uses air aspirated through the Waste air-gap route and passes through the verified cleaned paths. `P1` and `P2` are syringe pumps, so every pass consists of separate aspiration and dispense operations, never inline continuous flow. Each liquid pass should use almost the complete working syringe stroke, slightly inside `0` and `20500`; working stroke, exact flush volume, speed, and air-purge stroke remain pending calibration. Pumps are not re-homed before every flush stroke.

### Column flushing and carousel tubes

- The demo Column is gravity-driven and is not operated as a pressurized column.
- During normal flushing, the Column bottom valve may remain open. It closes while the carousel changes tubes and reopens after the next rinse tube is positioned.
- Carousel tubes have a nominal 10 mL capacity. Four initial positions are reserved for Column rinse cycle 1, Column rinse cycle 2, Column air purge, and spare/overflow.
- Exact slot numbers, steps per slot, home sensing, safe working fill volume, and carousel motion calibration remain pending physical measurement.
- A full 10 mL must not be described as safely collectible in one tube until the working syringe stroke and tube fill margin are experimentally confirmed.

### Pump priming

`P1` is the precision-dosing pump and is primed with solvent `S`, not `B1` or `B2`. Its route is `S -> P1 -> Waste`; priming output must go to Waste, never back into the S bottle. The default is two cycles, with the prime stroke pending calibration. The purpose is to remove air from the common P1 dosing path before precise B1/B2 dosing.

`P2` is primarily a transport pump but is still primed to reduce air. Priming occurs after S has been dispensed into the Reactor and before reaction-mixture transfer, using `Reactor S -> P2 -> Reactor`. The default is two cycles, with the prime stroke pending calibration. A technical Demo Log event may later report completion.

Neither P1 nor P2 priming adds a new top-level Guided Demo phase.

### `Flush B1/B2 source lines`

This operator-assisted local Service/Maintenance procedure supports changing colored liquids, removing carryover, and end-of-demo cleaning; it is not part of the remote Guided Demo cockpit:

1. Replace the B1 and B2 bottles with rinse solvent and confirm both rinse sources are connected.
2. Aspirate rinse solvent through the B1 source line and dispense it to Waste, using the current default of two cycles.
3. Repeat the two-cycle rinse for the B2 source line.
4. Lift both intake tubes above the rinse liquid or place them in clean empty bottles, then confirm that air purge may begin.
5. Aspirate air through each source line and dispense it toward Waste.

Exact rinse stroke and speed remain pending calibration.

### Service-screen pump commissioning

Pump experiments and calibration will use the existing Service screen, not a separate temporary application or screen. A `Pump commissioning` section for P1 and P2 may initially use raw steps and step intervals. Hardware-action buttons remain unavailable until backend and firmware integration exists.

Values still requiring experimental determination are:

- `working_full_position_steps` and `working_empty_position_steps`
- `steps/ml`
- P1 and P2 prime strokes
- minimum reliable, maximum useful, and default step intervals
- flush speed range and air-purge stroke
- carousel positions and motion calibration
- Column bottom valve homing direction and open/closed mapping

### Deferred serious-system scope

The full protocol for serious chemistry remains deferred, including chemical incompatibilities, emergency-stop handling, pressure hazards, toxic or volatile solvents, advanced fault recovery, and handling of a recovery or flush operation that itself fails.

## Desired coding workflow

When changing UI code:

1. Inspect current files first.
2. Do not rewrite everything unless explicitly asked.
3. Prefer small, safe patches.
4. Preserve current visual direction unless asked to redesign.
5. Preserve left-to-right layout.
6. Keep port/topology meaning correct.
7. Run:

       npm run build

8. Fix TypeScript/build errors.
9. Summarize what changed.
10. Mention any remaining issues.

## User preferences

The user prefers communication in Croatian/BHS.

Keep code, variable names, function names, CSS class names, file names, package names, and terminal errors in English.

The user is building this step by step and does not want huge uncontrolled redesigns.

The user likes realistic, critical feedback, not empty encouragement.

The user wants the UI to be understandable to a chemist who is not a programmer.

The user is using Ubuntu 24.04, VS Code, React + Vite + TypeScript.

The user wants this UI to become part of a broader LabForge system for controlling a real lab automation device, not just a static mockup.

## Things not to do

Do not:

- turn the whole UI into a generic web dashboard
- ignore the physical topology
- treat P1/P2 as inline pumps
- hide important hardware meaning too early
- redesign unrelated UI when fixing one issue
- compress the left-to-right layout unless asked
- make valve labels too small
- show obsolete split solvent bottles
- put `V5` back into the P1 input branch
- bypass backend safety/parser architecture in future command or voice features


### Timed SF mixing decision — 2026-09-30

The user chose automatic SF mixing for a duration in seconds configured before
starting the run, rather than manual phase completion. Backend execution settings
now carry optional `sf_mixing_duration_seconds`; automatic SF mixing requires an
explicit positive finite value. Existing snapshots without it remain readable,
but no duration is inferred and that automatic phase cannot be prepared.
A corresponding explicit seconds input is now present in the connected Guided
Demo controls, together with settling and fraction settings. The existing local
preview remains separate from backend execution.

The owned fake-transport execution path holds shared hardware ownership through
START, the complete interruptible wait, required STOP and lifecycle result
persistence. This uses the current firmware's fixed commissioned mixer profile;
it does not implement or claim a mapping from `sf_mixing_command_percent` to
physical speed. No new hardware execution, firmware change or production startup
activation is authorized by this decision or its software tests.

### Explicit application/UI integration — 2026-10-03

The candidate `OwnedApplicationExecution` connects the FastAPI application and
Guided Demo controls to the existing owned executor. One worker/shared owner and
the same journals serve runs, recovery, flushing and Service. Default environment
startup does not activate this candidate. Tests inject fake transports only.
Connected controls read persisted phases/events, explicitly start work, send
out-of-queue Stop and use existing pause-capable wait controls. They cannot manually
confirm phase, Stop or flush completion. Maintenance also supports machine-only
scope, so first flushing or Service-fault recovery needs no fabricated run.
Explicit recovery retains exclusion until mandatory flushing succeeds. Plans,
calibrations and current device context remain server-supplied inputs; no physical
readiness is inferred. Backend detail: `docs/OWNED_APPLICATION_EXECUTION.md`.

The subsequent `build_adapter_application_execution` helper prepares resource
lifetime for those existing adapters. It opens nothing during construction;
explicit startup locks/validates the existing bundle before Serial handshake and
current-context preparation. Connection closes on the worker after orderly Stop
or failed setup. The context provider receives only boot identity, never an
unwrapped adapter or inferred position. Tests use fake transports; no live provider,
production environment activation, concrete calibration or switching default is
supplied.

### Guided browser verification profile — 2026-10-04

Backend `python -m tests.browser_check` explicitly composes the owned application
with existing Serial/SF adapters over hardwired fake transports. Its development
fixtures are hypothetical test data, not established physical routes or calibration.
Wall-clock waits allow browser Pause/Resume/Stop; an optional injected transport
failure exercises retained ownership, recovery and mandatory flushing. A marked
isolated temporary bundle persists across restarts and is never reset or repaired
by the launcher. It rejects live-port environment settings before application import.
No production activation or additional diagnostic API is added. Launch procedure:
backend `docs/BROWSER_CHECK.md`. User-led browser checks on 2026-10-04 confirmed
initialization, Start/Pause/Resume/completion, clean Stop/mandatory flush, injected
transport failure, restart/recovery/flush and a successful new run after another
restart. The same marked temporary bundle was retained throughout.

Restart between recovery and flushing preserves FLUSH_REQUIRED and ownership,
but discards execution session continuity. Fresh explicit recovery must precede
flushing in that new session. Durable FLUSH_REQUIRED alone cannot authorize
commands. Successful flush/release permits a new run even after restart, while
the old interrupted run remains a terminal historical record. UI guidance now
explains the required repeated recovery and identifies previous request responses
separately from actual backend state. These are software test results only.

### Independent review and UI follow-up — 2026-10-04

The supplied consolidated review accepted backend `e47d2acf` for the declared
fake-only software scope without findings. UI `544f7c4e` needs follow-up for
execution visibility across navigation/reload and non-applied percentage wording.
The uncommitted candidate on `codex/connected-execution-review-followup` adds a
global read-only execution banner with direct access to connected controls and
visible unknown-state handling on read failure. It disables/labels stored
addition/Reactor/SF percentages in connected settings/review while retaining
explicit SF mixing duration as an execution input. It adds no backend API,
command, speed mapping, automatic resubmission or resume. Twenty UI tests pass,
including eight isolated fake-API browser cases. User initially requested no
commit/push and a return to review after these two corrections. The subsequent
independent follow-up review accepted the complete candidate with zero findings
and closed both issues. The supplied request now authorizes one focused local
commit; push still requires separate authorization. Codex confirmed the working
diff matched the reviewed candidate and reran all UI checks successfully before
finalization. Backend remains unchanged at the accepted fake-only checkpoint.
Execution-driven flow animation was discussed and explicitly deferred; no
animation implementation or physical execution is authorized by this checkpoint.

### Explicit adapter/current-context software preparation — 2026-10-06

The user subsequently authorized and Codex pushed the accepted UI follow-up as
`0699827` on 2026-10-04. Its application code is unchanged by this next milestone.
User-approved adapter preparation at backend `36d6046` adds strict explicit
configuration and fresh attributed current input to the existing owned executor.
Startup leaves positions unknown; initial READY/Start and recovery bind input to
the connected session/request and a configured monotonic deadline. Missing,
foreign, stale or late input blocks before commands. Recovery can establish unknown
references using existing commands; ownership remains held through mandatory flush.
Successful same-session command continuity is retained instead of replaced by a
new callback snapshot. No diagnostic API/layer or production activation was added.

Fake transports verify the full fault/restart/recovery/flush/new-run path; 1826
backend tests pass. Independent review accepted backend `36d6046` and UI
documentation `3be3124` with zero findings for the declared fake-only preparation
scope. Codex verified the key conclusions against source; no correction is
needed. The reviewer did not independently rerun commands. This typed callback
does not yet implement a concrete live current-evidence source/operator workflow
or authenticate physical truth.
Static route/calibration inputs and software deadlines do not authorize physical
use. Details and missing physical inputs: backend `docs/ADAPTER_CURRENT_CONTEXT.md`.
Future production composition must explicitly use the configured/session-bound
provider rather than allow legacy assembly to bypass freshness. That is a future
integration gate, not a defect in this accepted preparation checkpoint.
Live configuration, physical readiness and execution remain separately gated;
flow animation remains deferred.


### Fresh operator current input through the existing UI — 2026-10-06

The user approved this concrete input source and chose the existing UI. Backend
`1c0e906` and UI implementation `7e36cf7` on `codex/operator-current-input`
connect a bounded, credential-attributed, single-use operator declaration to the
existing configured provider/owned executor. Initialization/first Start obtain
separate fresh references. Unknown RUN data blocks before commands; recovery can
retain unknown actuator references while requiring fresh stopped Reactor/manual
alignment and existing maintenance readiness. Ownership remains through mandatory
flushing and completed same-session command continuity serves later phases/runs.

UI credentials/consent/references are never restored or automatically submitted.
Stop/Cancel/timeout/shutdown unblock waiting input; restart invalidates request
identity and cannot promote a historical declaration receipt into readiness.
Receipt metadata stays in existing plan assumptions without secrets or migration;
old canonical records remain readable. The narrow declaration credential does
not establish general API authentication or physical truth. Production composition,
credential provisioning and actual reference acquisition remain gated.

All 1858 backend tests and 26 UI tests pass; Ruff, UI lint/build and diff checks
pass, using fake transports/intercepted APIs only. Optional fake launcher flag
`--operator-confirmations` permits manual browser checking with a random
process-local credential. Independent review accepted exact backend
`1c0e906ac2ad440ea741032192c29a67ab771739` and UI implementation
`7e36cf7b6518c08c514aa2e151b18f31ac888cb3` for this fake-only scope,
with zero findings at every severity. Codex checked the key conclusions against
source and agrees; no software correction is needed. The reviewer did not
independently rerun verification commands, and no GitHub combined status checks
were present on those HEADs. Later UI checkpoint/review closure commits change
documentation only. Manual browser verification of the new panel remains pending.

Existing P1/P2 step coordinates (HOME 0, approved maximum 20500) and demo-only
1025 steps/ml remain confirmed. Working margins are explicitly recorded as
"jos nije potvrdjeno". Dated dry Waste HOME routes/setup orders also exist;
complete safe switching between every process route is still unconfirmed.
The incomplete physical worksheet preserves known facts separately from null
candidate inputs and cannot activate hardware. No real port, production, upload,
EEPROM, main merge or flow animation is added. Further physical work requires
separate approval and fresh readiness. Backend details: `docs/OPERATOR_CURRENT_INPUT.md`.


### User-selected nominal demo pump range and route inventory — 2026-10-06

After the operator current-input review, the user explicitly selected P1/P2
full=0, empty=20500, nominal working volume=20 ml and no endpoint reserve for
the supervised demo, keeping 1025 steps/ml. Precise measured calibration is
deferred for this demo; no production calibration claim is made. This supersedes
the earlier pending working-margin status only for the nominal demo scope.
Firmware `HARDWARE_CONFIRMATIONS.md` records the decision; backend
`ADAPTER_PHYSICAL_PROFILE.draft.json` now contains those user-selected values
with `DEMO_NOMINAL` scope and remains non-activatable because other inputs are null.

No execution/protocol code changed. The existing absolute pump-move contract
accepts 1..20500; zero requires HOME. A nominal 20 ml ordinary aspiration from
20500 would currently be rejected by the planner. Full-stroke cycle handling
must be explicitly addressed if required, not silently converted to HOME.

Backend `docs/DEMO_ROUTE_SWITCHING_INVENTORY.md` reconstructs all ten target sets,
run/flush/recovery entries and existing hypothetical test orders. These orders
can be discussed logically but remain unconfirmed for physical use; known dry
Waste setup orders are separately retained. No real device was opened or moved.


### Valve transition proposal and confirmed connection behavior — 2026-10-06

The user approved preparing concrete valve switching procedures and then
explicitly confirmed that V1-V8 interrupt the old connection before the new one
opens during 90/180 switching. Firmware `HARDWARE_CONFIRMATIONS.md` records that
physical fact; no measured timing/sealing/pressure evidence is inferred.

Backend `docs/DEMO_ROUTE_SWITCHING_INVENTORY.md` now distinguishes 24 route-history
cases and no-op/conditional moves, with three detailed examples. A local logical
check covered 124 synthetic endpoint combinations and all ten destination
target/order sets; this is not hydraulic validation. Existing hypothetical
destination orders are proposed for the stationary-pump demo procedure, keeping
the existing SF/Column closure and completion checks. V3 may remain connected
while V7/V8 change; the nearest-pump-last rationale does not provide automatic
isolation when that valve is already at target.

The user has not yet accepted those complete orders. All physical candidate
route targets and the combined ordered/HOME confirmation remain unset. Fresh
startup and unknown-reference Recovery/HOME order remain separate decisions.
No runtime, protocol, production, firmware-code or physical execution changed.
Next: obtain acceptance/corrections for the concrete proposal, then record only
the approved procedure and continue the remaining profile work.


### Destination orders accepted; physical checking planned — 2026-10-06

The user explicitly accepted the ten reviewed destination switching orders for
the demo. This supersedes pending acceptance in the preceding proposal section.
Firmware `HARDWARE_CONFIRMATIONS.md` records the exact ordered targets and
stationary-pump/SF/Column/completion constraints. The backend worksheet now
contains those approved orders, sourced from the user-accepted proposal, with
startup/Recovery HOME entry and observed dry/wet results still separate. No
active profile, runtime/protocol change or physical execution was introduced.

The user asked about checking on the machine tomorrow, 2026-10-07. Proposed next
session: establish actual installed device/contents/readiness with motor power
off, agree current references/HOME entry, then seek concrete physical-test
authorization and new motor-power readiness before staged dry valve checks with
pumps stationary. Dry-air pump checks and small nominal-volume liquid-path checks
follow only with their own agreed conditions/authorization. The fake browser
launcher remains hardwired fake. The incomplete profile does not yet enable a
full autonomous RUN/Recovery/Flush, and full 20 ml ordinary aspiration remains
blocked by the zero/HOME command boundary. No physical authorization is inferred
from the planning question or acceptance of destination orders.
