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
cannot be cleared by restart/reprovisioning. The integration does not alter
profile IDs/digests, runtime state, operator credentials or USB identities.
Commissioning and later owner-performed standalone uploads are on separate
timelines; the currently installed firmware and present physical references are
unverified. See LABFORGE_CURRENT_STATE.md before considering any physical work.

Confirmed physical facts: [firmware/HARDWARE_CONFIRMATIONS.md](../firmware/HARDWARE_CONFIRMATIONS.md).
Serial semantics: [firmware/docs/LABFORGE_SERIAL_PROTOCOL_V1.md](../firmware/docs/LABFORGE_SERIAL_PROTOCOL_V1.md).
Detailed older architecture/topology context is preserved in
[the imported UI snapshot](../ui/LABFORGE_CONTEXT.md).

Existing legacy local worktrees and any running sessions are preserved. This
integration has not connected to devices or taken ownership of old runtime state.
Opening a future live Serial connection needs fresh readiness; historical
positions cannot be used as present references. The owner selected Apache-2.0 on
2026-10-20 and approved the English README. A supplied prototype photograph is
included unchanged in the approved documentation/license/photo checkpoint,
integrated into main. The owner confirmed ownership of the old code and decided
to retain the recovery archive for public access. No new recovery access is
implied. The README acknowledges inspiration from Professor Lee Cronin and the
Cronin Group at the University of Glasgow. GitHub presentation and publication
checks are recorded in PUBLICATION.md. The owner explicitly authorized public
visibility on 2026-10-20; SynMachine is now public and anonymous access was verified.
Original component repositories remain private; no physical execution is implied.

## Initial SiLA 2 software integration — 2026-11-08

The owner chose SiLA 2 next and XDL for later. The initial fake/local integration
provides TLS/loopback status, saved recipe reads/preview, explicit Start, persisted
progress and exact-operation Stop over existing FastAPI routes, validation,
lifecycle, ownership and command journals. It uses optional
`unitelabs-sila==0.13.0`; the independent C# example uses
`SiLA2.Client.Dynamic` 10.3.3. READ_ONLY/CONTROL tokens and selected-field request
attribution protect the SiLA listener, with admission before request decoding.
Existing HTTP/UI behavior remains unchanged. GitHub CI exercises fake devices
and the independent client without deployment.

`integration/sila2-main` ports only the SiLA/CI delta from `feature/sila2-ci`
at `40d8a65` onto main `49b5beb`. It does not merge commissioning's protocol,
wet-test or reconciliation changes. Existing main UI, README media and domain
execution code are preserved. Original source branches/review records remain
available; the earlier exact-commit acceptances do not automatically accept this
port. See `backend/docs/SILA2_MAIN_INTEGRATION.md` and `backend/docs/SILA2.md`.

The listener requires an explicitly FAKE backend. Live composition, production
credentials/certificates, external exposure and operator/emergency-stop policy
remain separate work, alongside the deferred wet-state reconciliation and
physical tests. XDL remains unimplemented. Preparing the integration does not
authorize physical actions or bypass the separate main-merge approval boundary.
