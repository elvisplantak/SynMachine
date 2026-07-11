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

## Current fluid topology

The current physical-flow model uses one shared Waste destination and one combined solvent source `S`.

### P1 reagent / solvent loading branch

Logical P1 connections:

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
- `V6` selects the `B1/B2` branch or solvent `S`.
- `V1` switches between aspiration from the selected source and dispensing from `P1`.
- `V2` selects `Reactor` or `Waste`.
- `S` is the single solvent source used for both reaction dilution and washing.
- `V2 -> Waste` can be used for priming, bubble removal, and washing liquid disposal.

### P2 reactor / downstream branch

Logical P2 connections:

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

The current physical topology is documented above in "Current fluid topology".

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
