# Adapter/current-context preparation — independent review

Date: 2026-10-06. Respond in Croatian/BHS. Findings are advisory; Codex assesses
them independently. This candidate is not yet independently accepted.

## Pinned scope

- Backend: https://github.com/elvisplantak/labforge-backend
- Branch: `codex/adapter-current-context-preparation`
- Review HEAD: `36d6046a10361bf7bdb5db7f440075573e9d2b41`
- Accepted base: `e47d2acf777a96a09fde763c4d8cb5f6c8fa5139` (fake-only scope).
- Comparison: https://github.com/elvisplantak/labforge-backend/compare/e47d2acf777a96a09fde763c4d8cb5f6c8fa5139...36d6046a10361bf7bdb5db7f440075573e9d2b41
- UI: https://github.com/elvisplantak/labforge-ui, same feature branch, documentation
  only over accepted/pushed `0699827604204f33f15393caddde71cbbec302ed`.

The user approved software preparation of explicit adapter configuration and an
independent current-input boundary using fake transports. Real devices/ports,
production activation, main merge, firmware upload, EEPROM work and physical
execution were not authorized or performed. Flow animation is explicitly deferred.

## Behavior and limits

Strict configuration includes all communication settings, a current-input deadline,
calibration scope/values, explicit existing route sequences and matching recovery/
flush plans. It excludes current references. Existing composition/worker/owner/
journals remain the path; no diagnostic layer/API, SQL migration or dependency.
Startup HELLO leaves references unknown. Fresh input binds to boot/nonce/epoch and
the exact request/time window before initial READY/Start/recovery, including direct
fresh-runtime entry. Old input is cleared before acquisition. Unknown pumps block
ordinary transfer/flush; explicit recovery may establish them. Completed same-session
command continuity remains authoritative through mandatory flush and later runs.

No concrete live evidence source/operator workflow or approved physical profile
is provided. The callback is synchronous and must bound its own I/O; late results
are refused, not forcibly cancelled. Correlation/attribution does not authenticate
hardware truth or detect a caller that relabels historical data. No physical routes,
working margins/calibrations or current references are invented. Canonical physical
and protocol facts remain firmware `HARDWARE_CONFIRMATIONS.md` and
`docs/LABFORGE_SERIAL_PROTOCOL_V1.md`; never access firmware `recovery/`.

## Evidence and review focus

44 new focused tests pass; full backend suite: **1826 passed in 103.01 s**. Ruff
and diff checks pass. 10 changed files, +949/-13. Fake Serial/DYNAMIXEL only.
No firmware/UI code changed; their builds were not rerun. No firmware resource
impact. The previous accepted UI verification remains 20 tests, lint and build.

Read `app/hardware/adapter_configuration.py`, the six small integration diffs,
`tests/test_adapter_configuration.py`, and `docs/ADAPTER_CURRENT_CONTEXT.md`.

1. Can initial/fresh or recovery entry bypass session-bound fresh input, or retain
   old references after a failed/partial/late response?
2. Are unknown references rejected before ordinary transfer/flush without breaking
   explicit recovery, terminal-command continuity, intent persistence or ownership?
3. Does transport-fault/restart preserve evidence, require recovery plus mandatory
   flush, and allow a later run without treating historical state as current trust?
4. Are configuration strictness, legacy compatibility and claimed physical limits
   accurate within this preparation scope?

Report findings by severity with concrete source/trigger and requested correction,
or accept the exact pinned commit for the declared fake-only preparation scope.
