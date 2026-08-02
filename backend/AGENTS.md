# LabForge backend working rules

- Communicate with the user in Croatian/BHS. Keep code, identifiers, paths,
  commands, commit messages, and terminal errors in English.
- Before work, read `../labforge-ui/LABFORGE_DEVELOPMENT_GOVERNANCE.md`,
  `../labforge-ui/LABFORGE_CURRENT_STATE.md`, and
  `../labforge-ui/LABFORGE_CONTEXT.md`. Governance overrides older workflow
  instructions; technical and historical documents remain sources of context.
- Follow the milestone-scoped autonomous workflow and approval boundaries in
  the governance document.
- Backend owns domain validation, lifecycle, persistence, state machines,
  high-level phase policy, route decisions, durable intent, recovery policy,
  safety enforcement, and orchestration.
- Firmware owns pins and low-level execution. Frontend-disabled controls are not
  a safety boundary. Never invent hardware facts or pin assignments.
- `P1` and `P2` are syringe pumps with separate aspiration and dispense
  operations, never inline pumps.
- Inspect and preserve existing work. Isolate changes in another branch or
  worktree when appropriate; stop only if safe isolation is impossible.
- Keep changes cohesive; do not expand into generic frameworks without a
  milestone need or perform unrelated refactoring.
- Run focused and complete relevant pytest suites and Ruff checks for code
  changes. Documentation-only work needs diff/whitespace/status verification.
- Self-review the complete local diff, but report concise changed-file,
  diff-stat, verification, risk, and final-status information unless focused
  content is requested.
