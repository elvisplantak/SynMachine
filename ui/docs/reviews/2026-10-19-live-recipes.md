# Independent review — explicit live Recipes entry point

Please respond in Croatian/BHS. Review this cohesive new scope; prior animation
acceptance does not extend to these new implementation HEADs.

| Repository | Branch | Base | Reviewed code HEAD |
| --- | --- | --- | --- |
| elvisplantak/labforge-backend | codex/live-recipes-ui | 5c99e190e70c234507f3cf44abd66beca0354bd2 | 60e04e585fc31a58124b18aa7b5dd145b45b854d |
| elvisplantak/labforge-ui | codex/live-recipes-ui | 4d6996f (prior UI documentation HEAD) | b79c878a0cf7dc9d0b89223e8d8e56afd82c32cd |
| elvisplantak/labforge-firmware | codex/live-recipes-ui | 3cc2de2fe69ff4990dccc003f7baa2adb446ff7f | af940d9d3060fc4ae585fc398b6775ff4765692b (report only) |

Backend commit: https://github.com/elvisplantak/labforge-backend/commit/60e04e585fc31a58124b18aa7b5dd145b45b854d
UI commit: https://github.com/elvisplantak/labforge-ui/commit/b79c878a0cf7dc9d0b89223e8d8e56afd82c32cd
Firmware report: https://github.com/elvisplantak/labforge-firmware/commit/af940d9d3060fc4ae585fc398b6775ff4765692b

User scope: prepare existing Recipes for real-machine execution; user will then
perform liquid testing. They report prior satisfactory independent wet checks.
They explicitly selected existing logical recipe actions and mL/step-based pumps,
not raw valve sequences or timed pump actuation. No extra calibration, HOME order,
flush quantities or current references were supplied by that report.

Implementation:
- app.live_execution has inert validate/provision and explicit localhost serve
  --connect-real-devices. It rejects legacy live-port environment, occupied HTTP
  listener, invalid profile and missing/foreign/fake/symlinked/corrupt state.
- Provision is explicit, new-directory-only. Three existing owned DBs and a
  profile-digest manifest are retained across restart; no reset/migration/rebind.
  Private random operator.key is 0600, not logged or returned by status.
- Existing adapter/owned runtime, journals, intent-before-bytes, atomic Stop,
  protected SF/Column follow-ups and no-replay/reconciliation remain the path.
  Startup selects real Serial with exclusive=True and existing timings for HELLO
  only. There is no automatic HOME/actuation/recovery/recipe Start.
- Profile uses previously recorded USB identities, commissioned SF coupling and
  profile, user-approved route orders and nominal demo P1/P2 calibration.
  No fixtures are copied as live physical inputs. Current references stay fresh
  operator declarations; no historical raw position/boot is saved as readiness.
- Required configuration maintenance fields now accept explicit null. Missing
  plans remain unavailable; backend start_maintenance rejects and UI disables
  them. Stop/failure/restart still retain ownership and mandatory maintenance.
- Optional status fields identify LIVE/FAKE/UNSPECIFIED, profile_id and available
  maintenance_actions. UI shows connection identity before recipe entry, fails
  unidentified on invalid/read-error status, and never assumes legacy is fake.
- Recipe schema, snapshot/digest binding, compiler, actuator protocol and firmware
  executable code are unchanged. Firmware change is attributed user report only.

Evidence: final complete backend 1937 passed; live entry 17 passed; earlier focused
configuration/operator/live 84 passed. UI 51 passed (24 actual headless browser
cases), zero skips. Ruff, UI lint, TypeScript/Vite build and diff checks passed.
JS337.12kB/gzip92.45, CSS53.04kB/gzip10.58. Tests inject fake Serial/DYNAMIXEL only.
Offline profile validation and explicit initial provisioning at
/home/elvis/.local/state/labforge/recipes-live-v1 opened no device. Existing fake
state/library is preserved. Real first-connection status is recorded separately
in LABFORGE_CURRENT_STATE.md; no physical recipe test is claimed by this packet.

Focused questions:
1. Do validation/provision/serve, identity/digest binding, credential handling and
   explicit real factories preserve inert preparation, durable state and the
   existing ownership/dispatch/no-replay boundaries? app/live_execution.py and
   tests/test_live_execution.py; adapter_application/configuration.
2. Does explicit null maintenance refuse unconfigured work while preserving
   required maintenance and retained ownership after Stop/fault/restart? Existing
   owned runtime/runner semantics should be compared; no bypass is intended.
3. Do optional mode/profile/action fields and UI handling identify live vs fake
   before Start without issuing commands or changing recipe authorization?
   ExecutionEnvironment.tsx, OwnedDemoControls.tsx, RecipeWorkspace.tsx,
   guidedDemoApi.ts and the new UI fixture/unit regressions.

Classify findings by severity and distinguish software preparation acceptance
from real current-reference/physical/wet validation. No main merge or firmware
upload is requested. Do not access firmware recovery/.


## Actual first connection evidence

After preparation and verification the user freshly confirmed machine stopped,
motor power OFF and both USBs connected. Explicit serve started successfully on
127.0.0.1:8000 (PID17990) and completed existing HELLO. No agent actuator request,
HOME, initialization or operator declaration was sent. GET execution reports
LIVE/labforge-supervised-recipes-v1, idle, error null, owner null, flow null,
operator input configured, maintenance_actions empty. Machine remains absent and
recipe library empty. Read-only SQL confirms Arduino journal0, SF journal0,
prepared plans0, waits0 and owner slot null. This is a no-motion connection check,
not physical recipe/wet acceptance. UI runs on 5173; user will enter their recipe.
