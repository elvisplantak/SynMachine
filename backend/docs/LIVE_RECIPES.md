# SynMachine — explicit live Recipes setup

Scope: user-authorized preparation on 2026-10-19. Recipes retain their existing
high-level actions and mL inputs; the backend selects approved routes and executes
separate syringe aspiration/dispense. No raw actuator recipe language or pump
seconds-to-volume conversion is added. Firmware and its installed timings do not
change. The physical module is controlled only by explicit existing UI actions.

SynMachine is the current visible working name. Existing `labforge` paths,
`LABFORGE_*` variables, `LABFORGE/1`, profile identities and state bindings remain
unchanged; no state migration or reprovisioning accompanies this naming change.

## Entry point and profile

`python -m app.live_execution` provides three separate actions. Importing it,
validating a profile and provisioning a new state directory never open a device.
`serve` requires an explicit real-device flag and operator identity. It binds only
127.0.0.1, one worker, no reload, with the existing owned application, worker,
journals, protected follow-ups, Stop, reconciliation and recipe integrity checks.
The legacy environment-driven Arduino/SF composition must be unset first.

`LIVE_RECIPES_PROFILE.json` uses the previously confirmed Arduino Mega and U2D2
USB by-id identities, existing adapter timing, commissioned SF positions/profile,
user-approved destination orders and nominal P1/P2 0..20500 / 20 mL calibration.
The 600-second input window is a host operator-form timeout, not a hardware fact.
No old positions or boot identities are persisted as current references. Configured
ports are selected explicitly, not discovered automatically. Equal resolved paths
are rejected. Real Arduino opening additionally requests Linux Serial exclusivity.

The user's report of prior independent liquid checks is recorded in firmware
HARDWARE_CONFIRMATIONS.md; it supplies no measured-volume calibration or new
specific route/HOME/flush facts. Calibration stays DEMO_NOMINAL. Exact 20 mL
ordinary aspiration targeting position zero remains rejected by the existing
firmware/planner contract; HOME is never substituted automatically.

## Prepare without connecting

From the active backend worktree:

```bash
env -u LABFORGE_ARDUINO_PORT -u LABFORGE_SF_BOTTOM_VALVE_PORT \
  /home/elvis/Documents/labforge-backend/.venv/bin/python -m app.live_execution validate \
  --profile docs/LIVE_RECIPES_PROFILE.json

env -u LABFORGE_ARDUINO_PORT -u LABFORGE_SF_BOTTOM_VALVE_PORT \
  /home/elvis/Documents/labforge-backend/.venv/bin/python -m app.live_execution provision \
  --profile docs/LIVE_RECIPES_PROFILE.json \
  --state-dir /home/elvis/.local/state/labforge/recipes-live-v1
```

Provision is explicit and accepts a newly created directory only. A partial
failure remains intact; repeating provision cannot overwrite it. The manifest
binds the three existing owned database identities and the profile content digest.
Fake/foreign/missing/symlinked/corrupt state or altered configuration is refused,
without reset, migration, repair or rebind. Recipe storage is separate from the
old temporary fake library, which is preserved. Never create replacement state
to bypass an interrupted command, retained ownership or required maintenance.

A private random operator credential is stored as `operator.key` (owner-only).
It is not printed in server logs, committed or sent through GET status. Read it
locally and enter it into the existing fresh-reference UI form when requested.

## Deliberate connection

After current physical preparation and the applicable operator authorization:

```bash
env -u LABFORGE_ARDUINO_PORT -u LABFORGE_SF_BOTTOM_VALVE_PORT \
  /home/elvis/Documents/labforge-backend/.venv/bin/python -m app.live_execution serve \
  --profile docs/LIVE_RECIPES_PROFILE.json \
  --state-dir /home/elvis/.local/state/labforge/recipes-live-v1 \
  --operator Elvis --connect-real-devices --port 8000
```

Startup validates/locks the existing bundle and performs existing Arduino HELLO.
Opening USB can reset the Mega. It sends no automatic HOME, pump/valve/mixer
command, SF write, recovery, flushing or recipe Start. No retry/reconnect/replay
is added. SF connection remains scoped to existing observation/execution actions.
An occupied HTTP listener is rejected before real construction; no unrelated
server is terminated. Existing files/journals are retained across restart.

Start the existing UI with `npm run dev -- --host 127.0.0.1 --port 5173 --strictPort`.
Its existing API proxy uses 8000. Open http://127.0.0.1:5173/ and Recipes. Check
**Real devices** and the profile identity before starting. Test launchers report
**Test devices — no physical movement**; older unidentified backends are labelled
unidentified, never assumed fake. Read failures remove the last connection label.

## First use and references

Service controls remain available through the same shared owner while idle.
Use the existing supervised Service procedures to establish actual current
controller references if unknown. Do not guess raw pump coordinates or reuse
historical logs. A pump HOME may move liquid; use a physically verified safe
route. The launcher does not automate the previously dry-only all-device HOME
bootstrap or declare that HOME order safe for a filled system.

`Initialize configured system` requests fresh operator input without actuator
commands. Supply independently established same-session pump empty coordinates
(20500 under this nominal profile), V1-V8 references, stopped mixers, closed SF
bottom, current Column reference and manually aligned carousel. The controller
must itself have valid references; the form is not a firmware position setter.
Unknown references must stay unknown and block execution. Before first Start,
separate new input is requested. Later phases retain successful same-session
command continuity; they never reconstruct it from history after restart.

Create/save a recipe, review it, enter fresh preparation and explicitly select
`Start reviewed procedure`. The previous recipe schema, immutable revisions and
content-digest checks remain unchanged. Pumps are entered in mL in Recipes;
absolute steps remain available in Service. Heating/Reactor mixing are not added.

## Deliberately unconfigured maintenance

The shipped profile explicitly sets recovery_plan and flush_plan to null. No
unconfirmed HOME order, rinse volumes, air volumes, drain time or safe tube margin
is copied from a test fixture. The backend exposes available maintenance actions;
the UI disables absent actions and explains their unavailability. Existing full
profiles and legacy UI responses retain their existing behavior.

Stop/fault/restart retain existing ownership and RECOVERY_REQUIRED/FLUSH_REQUIRED.
Missing plans do not release ownership, claim cleaning or permit another run.
Adding automatic recovery/flush later requires explicit physically applicable
inputs and a deliberate profile/state update; the digest binding rejects silent
changes. Do not delete/reprovision state to unblock execution.

## Evidence

See tests/test_live_execution.py for fake-only launcher/profile/refusal checks,
real adapter composition over injected fake ports, actual UI declaration HTTP,
complete saved-recipe execution twice, restart library preservation and Stop with
required maintenance retained. Existing operator/runtime suites remain relevant.
New software scope is self-verified; prior animation acceptance does not extend
to this new live entry point. No physical execution is asserted by these tests.

Final software verification: complete backend 1937 passed; focused live entry
17 passed; 84 focused configuration/operator/live checks passed at the earlier
focused stage. Ruff and diff checks passed. UI 51 passed including 24 real
headless-browser fixtures (all APIs fake), zero skipped; lint and TypeScript/Vite
build passed. JS337.12kB/gzip92.45, CSS53.04kB/gzip10.58. No real device was opened
to obtain these results. The final connection remains an explicit later step.
