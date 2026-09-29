# Simulated Column fraction collection

Offline continuation approved by the user on 2026-09-29 after pausing V8 repair.
Base: `f87a6c4f7612b7621e18ba1f3a5bc4aec68fcb00`, independently accepted with
zero remaining findings. Branch: `codex/simulated-p1-execution`.

## Behavior

The existing isolated simulator now accepts ColumnFractionCollectionOperationPlan.
Each fraction follows prepared Column OPEN, CollectionWait, required Column CLOSE;
carousel movement follows only successful completion of that operation. The
existing nominal carousel mapping includes 40-to-1 wrap. No physical port,
calibration, target, route order, firmware or production API behavior changes.

The simulated device advances virtual time only. Its wait hook injects a mid-wait
Stop or fault; no wall-clock timing, sensor observation or volume inference occurs.
Stop is checked before and after the hook. A timer-interrupted fraction is recorded
as COLLECTION_STOP_REQUESTED at phase level and is NOT included in the completed
operation count. CLOSE still runs. Stop arriving during successful CLOSE is
observed at the next operation boundary. If CLOSE fails, its failure takes
precedence over a normal Stop outcome. No carousel move follows either case.

Required follow-up uses the same accepted protected-operation helper as SF.
Ordinary primary errors still attempt CLOSE; combined failures preserve both
exceptions, and unknown outcomes dominate definitive failure. Process death
cannot guarantee CLOSE, and reopening never automatically sends it or resumes.

## Durable simulation evidence

Two new tables are created only by explicit new-database provisioning:

- simulation_waits: phase/operation identity, exact Decimal duration spelling,
  INTENT_PERSISTED before waiting, then COMPLETED, STOP_REQUESTED or OUTCOME_UNKNOWN.
- simulation_carousel_projection: historical per-phase simulated position, cleared
  before a carousel command can be sent and restored only after durable success.

Carousel failure/unknown leaves both the device fixture and stored projection
unknown. A detected Arduino session change also invalidates that projection.
These records are historical evidence, never current physical trust after restart.
Owner retention prevents further operations and replay after interrupted attempts.
Orphan wait/projection records block even the first send. Existing databases lacking
these tables fail closed; no migration or automatic repair is implemented.

## Verification

30 new collection tests; one former collection-rejection test removed:
94 simulation tests, 200 combined focused tests and all 1268 backend tests pass.
Ruff and diff/whitespace checks pass. Coverage includes:

- exact OPEN/wait/CLOSE/move ordering, three fractions and 40-to-1 wrap;
- Stop during OPEN, wait and CLOSE without subsequent carousel movement;
- 15 primary/wait/required-CLOSE result combinations;
- carousel definitive failure, ambiguous outcome and session change;
- intent/result persistence faults for wait and required Column CLOSE;
- reboot during collection, orphan durable evidence, and subprocess exit during
  wait with no send or database modification after reopen.

All previous P1 and P2/SF simulations remain covered. Tests use temporary databases
and fake devices. No live transport, actuator operation or firmware upload is part
of this software milestone.

## Remaining integration boundary

The subsequent offline lifecycle binding is documented in
`SIMULATED_LIFECYCLE_BINDING.md`. It exercises real lifecycle transitions with
fixture databases and simulated devices. Production-wide Service/SF ownership,
approved live route-switching order, live Stop semantics and independently
established hardware/session trust remain unimplemented. Virtual waits are not a live
timer implementation. Those remain prerequisites before API activation.

Consolidate the next independent review around collection plus the next substantial
integration boundary rather than requesting review of this mechanical checkpoint.
Include partial-fragment accounting, required CLOSE failure precedence, durable
wait evidence, projection invalidation, and restart blocking in that review.
