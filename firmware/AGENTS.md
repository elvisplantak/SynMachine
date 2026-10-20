# LabForge firmware working rules

- Communicate with the user in Croatian/BHS. Keep code, identifiers, paths,
  commands, commit messages, and terminal errors in English.
- Before work, read `../docs/LABFORGE_DEVELOPMENT_GOVERNANCE.md`,
  `../docs/LABFORGE_CURRENT_STATE.md`,
  `../docs/LABFORGE_CONTEXT.md`, and local
  `HARDWARE_CONFIRMATIONS.md`.
- Before changing serial communication, parsing, sessions, command lifecycle,
  reconnect behavior, or actuator protocol, read
  `docs/LABFORGE_SERIAL_PROTOCOL_V1.md`.
- Governance overrides older workflow instructions. The serial-protocol document
  remains canonical for communication semantics; hardware confirmations remain
  canonical for confirmed physical facts. Neither may invent facts owned by the
  other.
- Follow the milestone-scoped autonomous workflow and approval boundaries in
  the governance document.
- Never access, search, list, diff, summarize, modify, or use anything under
  `recovery/` without explicit authorization for that exact action.
- Firmware owns pins, motor direction, stepping, homing, debounce, low-level
  timeout behavior, and device execution. Backend owns lifecycle, high-level
  policy, routes, and orchestration.
- Never invent pins, valve ports, sensors, polarity, directions, steps,
  calibration, or hardware capability. `P1` and `P2` are syringe pumps with
  separate aspiration and dispense operations and the confirmed common physical
  orientation documented in `HARDWARE_CONFIRMATIONS.md`.
- Pump homing can move fluid and requires a physically verified safe route.
- Inspect and preserve existing work. Isolate changes in another branch or
  worktree when appropriate; stop only if safe isolation is impossible.
- Keep changes cohesive and avoid unrelated refactoring.
- For firmware code, run focused and complete native tests, warning-enabled
  native compilation, the Mega 2560 build, memory/resource reporting,
  `git diff --check`, and final Git status. Documentation-only work requires
  diff/whitespace/status verification, not builds.
- Self-review the complete relevant diff, but report concise changed-file,
  diff-stat, verification, risk, and final-status information unless focused
  content is requested.
