Please respond in Croatian/BHS. Review this completed software integration slice.

Repository: elvisplantak/labforge-backend
Branch: codex/owned-recovery-flush
Review HEAD: e84ea97e177ff23be8d043e9b79be27a7a75e3a5
Integration commit: a14c7beb77f7bd830a8368e1a400cf08be872b3b
Immediate base: 9245e9e3f66716eb5dde17aaa3bd3b432f058e99
Last independently accepted base: 3d9fab24f325f3a2da59d69215465e110acd3c33
The prior four-checkpoint range received a conditional acceptance with one LOW
freshness finding. Its targeted correction is separately pinned to ff589ac on
codex/status-request-freshness (base 9245e9e); see the status-request-freshness
follow-up and complete patch. HEAD includes the identical correction via cherry-pick.
Neither the prior range nor this integration is marked independently accepted yet.

User approval: connect recovery, mandatory flush and durable owner release/new-run
permission through the existing execution path; prepare existing real adapters
using fake transports in tests. No additional diagnostic layer, physical execution,
production activation or main merge was authorized.

Scope: 27 files, +1936/-33 lines, including the 6-file freshness correction.
The original integration scope was 21 files, +1829/-25 lines.
Existing OwnedOfflineRuntime/OwnedTransferRunner,
plan store, journals and ownership execute recovery -> FLUSH_REQUIRED -> explicit
required flush -> READY -> owner release -> new run. Old runs/evidence remain
terminal/unchanged. Clean Stop can flush retained pump contents without re-homing.
New maintenance intent/event JSON is stored in existing lifecycle tables; SQL
schemas and versions are unchanged. No database migration/provisioning at reopen.

PreparedAdapterDevice uses existing ArduinoSerialClient and SfBottomValveActuator;
preflight reuses fresh observations under ownership. All adapter tests inject fake
Serial ports and DYNAMIXEL sessions; no real port or production process was used.

Focused review questions:
1. Are interruption, maintenance replacement, lifecycle completion and owner-release
   crash boundaries conservative, including READY with retained ownership?
2. Can stale/copied state, an old run/plan, Service interference, session replacement,
   Stop during the last command or domain-only completion bypass mandatory flush?
3. Are homing/Waste ordering, clean-Stop emptying, SF required CLOSE and Column
   close/move/reopen boundaries preserved through errors and dual cleanup failures?
4. Does adapter preparation keep journals-before-bytes, fresh correlation, explicit
   timing and transport cleanup without claiming physical/session trust?

Current HEAD verification after freshness correction: 108 focused connected tests
passed in 18.67 s; full suite 1718 passed in 75.17 s. Ruff and diff/commit checks
passed. Original integration verification: 40 focused new tests passed;
full suite 1710 passed in 72.62 s;
Ruff and staged/working diff checks passed. Includes actual subprocess death during
recovery/flush, empty initial references, historical unknown evidence preservation,
release/completion failures and a complete new ten-phase run after mandatory flush.
These are local results, not independently rerun results.

Limits: separate database commits are non-atomic; advisory locks cover this explicit
composition only; SF scope is host correlation; readiness is an operator statement.
Volumes, margins, routes/switching order, tube alignment and drain time remain
explicit inputs needing physical verification. No measured cleaning/drainage claim,
automatic interrupted-run resume, production startup/API/UI activation or firmware
change. Optional standalone flush from READY remains outside this integrated slice.

Primary additions: app/demo/maintenance_plan.py, app/hardware/owned_maintenance.py,
app/hardware/prepared_adapter_device.py. Connected changes: owned_offline_runtime.py,
owned_transfer_runner.py, owned_phase_session.py, command_planning.py,
command_plan_store.py, sequence_ownership.py, simulated_lifecycle.py and machine
models/events/domain completion guards. Detail: docs/OWNED_RECOVERY_FLUSH.md.

Report actual Critical/High/Medium/Low defects with locations and impact; distinguish
them from explicitly deferred production/physical gates. Suggestions remain advisory.
