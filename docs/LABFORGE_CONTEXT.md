# SynMachine system context

SynMachine is one mechatronic laboratory-automation project, organized as a
monorepo with `ui/`, `backend/`, `firmware/`, `docs/` and `hardware/`.

The UI owns interaction and visualization; Python/FastAPI owns validation,
durable recipe versions, lifecycle, route planning, command journals and
orchestration; Arduino Mega owns pins, direction, stepping, homing and low-level
execution. P1/P2 are syringe pumps with separate aspiration and dispense.

Recipes uses existing logical operations: ADD from B1/B2/S, passive WAIT,
Reactor-to-SF transfer, SF mixing/settling, SF-to-Column transfer and final timed
fraction collection. Arbitrary textual procedures/XDL, new modules and new raw
actuator recipe operations are not part of this migration. Route animations
represent current backend command scopes, not sensed liquid flow.

The current machine is a mechatronic demonstrator tested with colored liquids.
The owner reports silicone tubing and medical-plastic valves/syringes. PTFE
tubing/valves and glass syringes with PTFE plungers are a planned next material
stage, with selection for the intended chemical procedure. No new physical
verification or chemical capability is inferred from documentation changes.

The last reviewed live Recipes preparation remains scoped to its original
accepted implementations; use [the migration map](history/README.md) to resolve
their original IDs. The live profile remains nominal 1025 steps/mL with the
existing limits; its Recovery/Flush plans remain null and required maintenance
cannot be cleared by restart/reprovisioning. The repository migration preserved
profile IDs/digests, runtime state,
operator credentials and USB identities. Later commissioning and owner-performed
standalone uploads supersede the migration-time installed-firmware statement;
the currently installed Arduino image is unverified. See the immediate checkpoint
in LABFORGE_CURRENT_STATE.md before resuming any physical work.

Confirmed physical facts: [firmware/HARDWARE_CONFIRMATIONS.md](../firmware/HARDWARE_CONFIRMATIONS.md).
Serial semantics: [firmware/docs/LABFORGE_SERIAL_PROTOCOL_V1.md](../firmware/docs/LABFORGE_SERIAL_PROTOCOL_V1.md).
Detailed older architecture/topology context is preserved in
[the imported UI snapshot](../ui/LABFORGE_CONTEXT.md).

Existing legacy local worktrees and unrelated work remain preserved. The
migration itself did not connect to devices; later commissioning is recorded in
LABFORGE_CURRENT_STATE.md. Opening a future live Serial connection needs fresh
readiness; historical positions cannot be used as present references. The owner
selected Apache-2.0 on
2026-10-20 and approved the English README. A supplied prototype photograph is
included unchanged in the approved documentation/license/photo checkpoint,
integrated into main. The owner confirmed ownership of the old code and decided
to retain the recovery archive for public access. No new recovery access is
implied. The README acknowledges inspiration from Professor Lee Cronin and the
Cronin Group at the University of Glasgow. GitHub presentation and publication
checks are recorded in PUBLICATION.md. The owner explicitly authorized public
visibility on 2026-10-20; SynMachine is now public and anonymous access was verified.
Original component repositories remain private; no physical execution is implied.

## Next software phase — 2026-11-07

The owner chose SiLA 2 integration next and XDL for a later phase. The initial
SiLA development slice now adapts existing FastAPI routes in-process using the
optional `unitelabs-sila==0.13.0` SDK. It retains existing validation, lifecycle,
ownership and journals, exposing discovery/status, recipe reads/preview, explicit
execution, persisted progress and exact-operation Stop. The listener requires TLS,
binds loopback and permits explicitly FAKE execution only. See
`backend/docs/SILA2.md` for the Draft Feature contract, dependency decision,
launcher and limits. Production authentication/exposure and live composition are
separate future work. XDL is unimplemented.

Independent review accepted implementation commit
`222e9e5c163576a706bc32455ad60b8066c946c8` for this declared fake-only scope,
with zero findings at every severity and no requested software corrections.
The review record and evidence limits are in `backend/docs/SILA2.md`.

The owner subsequently approved independent-client interoperability on the same
computer with fake devices. `backend/tools/sila2-client/` now provides a separate
C# client using the official `SiLA2.Client.Dynamic` 10.3.3 implementation, locked
dependencies and explicit TLS certificate/server-identity checks. The fake demo
and tests cover recipe execution, progress, exact Stop and reconnect after client
loss without replay; that checkpoint left the accepted Python server unchanged. This new
work does not inherit the earlier review's acceptance.

The owner then approved local SiLA client access control, still fake-only.
Explicit expiring per-client tokens now enforce READ_ONLY versus CONTROL at
server RPC admission, with request attribution linked to existing run/operation
IDs. Launchers issue temporary private token files; the C# client uses
`--token-file`. Policy checks, selected-field durable audit, audit-failure and
unknown-outcome behavior are documented in `backend/docs/SILA2.md`. Existing
HTTP/UI authorization is unchanged; this is not production-wide identity or a
SiLA AuthenticationService implementation. The earlier review does not accept
these later changes. Production/live composition must still be defined separately.

Independent review of access-control commit `30a7ee3` found one Medium issue in
the generic wrapper's pre-deserialization guarantee; it did not accept that
checkpoint. The narrow follow-up now admits raw application RPC bytes before
calling any configured original gRPC deserializer, then retains the SDK handler,
response serialization and backend path. Malformed-wire regressions explicitly
exercise that optional seam as well as the pinned SDK's native decoding.
Independent follow-up review accepted exact correction commit
`a10a068806697e0125caab90e252b0187fb838db` against `30a7ee3`, with zero findings
and the previous Medium resolved. Acceptance covers only the narrow fake/local
admission correction, not the entire preceding integration or production/live
operation. The detailed record and verification limits are in `backend/docs/SILA2.md`.

The live owner remains blocked after the earlier wet attempt, and its reconciliation
is explicitly deferred. Develop against fake devices/separate test state; this
phase does not authorize real-device access, uploads, state repair or merging
into main. The integration branch starts at handoff `ae8c78f` over commissioning
`1ea4e7a`; public main contains different execution code and is not implicitly
merged or accepted by this milestone.
