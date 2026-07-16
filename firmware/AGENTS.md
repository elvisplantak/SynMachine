# LabForge firmware working rules

- Communicate with the user in Croatian/BHS. Keep code and technical identifiers in English.
- Before firmware work, read `../labforge-ui/LABFORGE_CONTEXT.md` and local `HARDWARE_CONFIRMATIONS.md`.
- The sibling `LABFORGE_CONTEXT.md` is the canonical system-level LabForge context. Local firmware documentation is the source for confirmed low-level hardware behavior.
- Before edits, inspect `git status --short`, the current branch, and recent history.
- Use a separate, clearly named Git branch for each active firmware experiment or functional change.
- Keep changes small, targeted, and limited to the requested problem. Do not perform unrelated refactoring or redesign.
- Do not modify recovery artifacts unless the user explicitly approves it.
- Do not commit, push, merge, delete branches, or modify `main` without explicit user approval.
- Quote terminal errors exactly.
- Run available compilation/tests, the complete relevant diff, `git diff --check`, and final Git status.
- Firmware owns pin assignments, motor direction, stepping, homing, debounce, low-level timeout behavior, and device execution.
- Backend owns the chemical run lifecycle, high-level phase policy, route decisions, and system orchestration.
- Frontend disabled controls are not a hardware safety boundary.
- P1 and P2 are syringe pumps with separate aspiration and dispense operations, never inline pumps.
- Do not invent pins, valve ports, sensors, calibration values, or hardware capabilities.
- P1 has a confirmed physical orientation documented in `HARDWARE_CONFIRMATIONS.md`. P2 orientation remains unconfirmed until physically tested.
- Pump homing may move fluid and therefore requires a verified safe fluidic route.
