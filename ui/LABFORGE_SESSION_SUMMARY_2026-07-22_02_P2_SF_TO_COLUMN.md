# LabForge session summary — P2 SF to Column operation plan

Date: 2026-07-22

## Accepted backend result

Repository:

    ~/Documents/labforge-backend

Branch and commit:

    codex/guided-demo-p2-sf-to-column-operation-plan
    2c18f0a460ec655bd69d917461feeda031717a07
    2c18f0a Add P2 SF-to-Column operation plan

Accepted verification:

    508 passed
    .venv/bin/ruff check . -> All checks passed!
    git diff --check -> passed

No push or merge was reported.

The completed symbolic operation plans are `P1` solvent to Reactor, `P1` `B1`/`B2` reagent transfers to Reactor, `P2` Reactor to `SF`, and `P2` `SF` to Column. They are planning artifacts, not a hardware executor or permission for physical execution.

## Accepted SF-to-Column operation semantics

The operation plan adds logical routes `SF_BOTTOM_TO_P2` and `P2_TO_COLUMN`. They do not define physical valve angles, Arduino pins, or motor steps.

The scheduler-visible phase sequence is exactly:

    PREPARE_SF_TO_COLUMN_TRANSFER

    for each transfer cycle:
        SELECT_ROUTE SF_BOTTOM_TO_P2
        ASPIRATE_FROM_SF cycle_volume
        SELECT_ROUTE P2_TO_COLUMN
        DISPENSE P2 cycle_volume

The protected phase-entry operation `PREPARE_SF_TO_COLUMN_TRANSFER` contains, in order:

    SET SF_BOTTOM_VALVE CLOSED
    SET COLUMN_BOTTOM_VALVE CLOSED

There is no normal Stop checkpoint between these actions. The `SF` valve closes first because `SF` nominally contains liquid and presents the more immediate gravity-flow risk.

Every protected `ASPIRATE_FROM_SF` operation contains, in order:

    OPEN SF_BOTTOM_VALVE
    ASPIRATE P2 cycle volume
    CLOSE SF_BOTTOM_VALVE

There is no normal Stop checkpoint inside it. `SF_BOTTOM_VALVE` opens and closes for every aspiration cycle and never remains open during route switching or dispensing. `COLUMN_BOTTOM_VALVE` remains closed throughout the phase. No Waste route is used.

The requested nominal volume is `fluid_plan.total_configured_volume_ml`. This remains an open-loop nominal value. The plan must not claim that `SF` is physically empty, measured delivery, automatic phase-boundary detection, or actual phase separation.

## Stop, close-failure, and valve-state boundaries

Normal Stop lets the current scheduler operation finish and prevents the next one from starting:

- Stop during `PREPARE_SF_TO_COLUMN_TRANSFER` lets both close actions finish.
- Stop before `ASPIRATE_FROM_SF` does not start aspiration.
- Stop during `ASPIRATE_FROM_SF` lets opening, aspiration, and the required close finish.
- Then `SELECT_ROUTE P2_TO_COLUMN` and `DISPENSE` do not start.
- `P2` may remain nominally full; the system must not dispense only to empty it after Stop.
- An already-started dispense may finish, but the next cycle does not start.
- The normal abort lifecycle remains run `ABORTED` plus machine `FLUSH_REQUIRED`.

A failed required close is not a successful normal abort. The future executor must fail the protected operation, block route switching and dispensing, stop further plan execution, and propagate a fault. A completed machine-level fault-state redesign is not claimed. Its exact recovery/fault transition remains unresolved before hardware execution.

No independent valve-position feedback sensors exist. For this low-risk colored-liquid Guided Demo, a successfully completed valve command is deliberately treated by software as meaning the valve is actually `OPEN` or `CLOSED`. This does not prove physical movement and is not automatically acceptable for serious chemistry.

For `P2_TRANSFER_SF_TO_COLUMN`, zero cycles are a validation error. A zero-volume or zero-cycle plan cannot succeed empty, become a close-only plan, or advance to fraction collection. Generic `TransferCyclePlan` behavior was not globally changed.

## Preserved hardware boundary

The confirmed tubing remains:

    SF bottom
    -> SF_BOTTOM_VALVE
    -> SF_BOTTOM_OUT
    -> V8.k2

    V5.k3
    -> Column inlet

    Column bottom
    -> COLUMN_BOTTOM_VALVE
    -> fractions / carousel

There is one shared Waste, and Column bottom does not connect to Waste.

The following remain unconfirmed: leak-tight routes, liquid route tests, valve-angle verification, physical bottom-valve actuation, Column bottom driver wiring, Column bottom Arduino pins, volumetric calibration, safe hardware interlocks, and end-to-end execution. `D12` and `D13` remain unconfirmed suggestions only, not actual pins.

## Next task

The next task is functional and safety design for `COLUMN_FRACTION_COLLECTION`, not implementation or a complete design. Accepted high-level intent:

1. Open `COLUMN_BOTTOM_VALVE`.
2. Collect for the configured fraction duration.
3. Close `COLUMN_BOTTOM_VALVE`.
4. Move the carousel.
5. Reopen only after carousel motion completes.
6. Never move the carousel while the outlet is open.
7. Leave the outlet closed after the final fraction.

Fraction count and fraction duration are Service-configured. Still unresolved are protected Stop boundaries around opening, collection, and closing; Stop during fraction collection; Column close failure; carousel movement failure; fraction timing semantics; the final-fraction completion race; zero-fraction configuration; possible additional protected compound operations; exact retained logical state after abort; and interaction with `FLUSH_REQUIRED`.
