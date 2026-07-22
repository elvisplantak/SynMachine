# LabForge session summary — 2026-07-22

This file is an informational session snapshot.

It does not override, in order of precedence:

1. the latest explicit user decision
2. the current `LABFORGE_CONTEXT.md`
3. the current `labforge-firmware/HARDWARE_CONFIRMATIONS.md`
4. repository-specific `AGENTS.md`

## Confirmed physical rewiring

The user explicitly confirmed that the physical tubing has been connected according to the approved LabForge v1 target topology. This confirms tubing topology only; the verification and commissioning work listed below remains pending.

## Exact V1-V8 topology

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

There is one shared Waste destination. The Column bottom does not connect to Waste.

## SF and Column bottom valve paths

    SF bottom
      -> SF_BOTTOM_VALVE
      -> SF_BOTTOM_OUT
      -> V8.k2

    Column bottom
      -> COLUMN_BOTTOM_VALVE
      -> Fractions / carousel

## Guided Demo SF behavior

- `SF` is unpressurized.
- Fill `SF` through `SF_TOP_IN` with `SF_BOTTOM_VALVE` closed.
- Open `SF_BOTTOM_VALVE` only during aspiration from `SF`, then close it before route switching and dispensing.
- Keep `COLUMN_BOTTOM_VALVE` closed while filling the Column; open it only during `COLUMN_FRACTION_COLLECTION`.
- Send all nominal `SF` contents to the Column; there is no Guided Demo split to Waste.
- Do not claim automatic phase detection, actual phase separation, measured delivered volume, or that `SF` is empty.
- Keep the Reactor mixer OFF before, during, and after `P2_TRANSFER_REACTOR_TO_SF`.
- Transfer volumes are nominal open-loop values.

## Completed backend operation plans

Backend repository: `~/Documents/labforge-backend`

Completed symbolic operation plans:

- `P1` solvent to Reactor
- `P1` `B1`/`B2` reagent transfers to Reactor
- `P2` Reactor to `SF`

Current completed backend branch: `codex/guided-demo-p2-reactor-to-sf-operation-plan`

Current completed commit: `ec68655 Add P2 reactor-to-SF operation plan`

Full test suite: `492 passed`

Symbolic operation plans are not permission or proof of hardware execution.

## Next planned P2_TRANSFER_SF_TO_COLUMN task

The next backend task is a safety-aware symbolic operation plan for `P2_TRANSFER_SF_TO_COLUMN`. It must represent the bottom-valve sequence, Column filling with `COLUMN_BOTTOM_VALVE` closed, all nominal `SF` contents routed to the Column, and no measured-volume, `SF`-empty, or automatic-phase-detection claim. `Stop` safety semantics and exact operation grouping are not implemented yet.

## Remaining physical verification

- leak testing
- individual route testing with liquid
- verification of every valve angle and physical route
- verification of `SF_BOTTOM_VALVE` actuation
- verification of `COLUMN_BOTTOM_VALVE` actuation
- pump volumetric calibration
- safe execution interlocks
- end-to-end hardware execution
- automatic phase detection remains unavailable and unverified

## Proposed / unconfirmed COLUMN_BOTTOM_VALVE Arduino pins

The following pins were only proposed as possibilities and are not confirmed, final, connected, or part of canonical confirmed pin mappings:

- proposed STEP: `D12`
- proposed DIR: `D13`

The actual driver connection and firmware mapping remain unconfirmed.
