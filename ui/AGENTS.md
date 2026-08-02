# LabForge UI working rules

- Communicate with the user in Croatian/BHS. Keep code, identifiers, paths,
  commands, commit messages, and terminal errors in English.
- Before work, read `LABFORGE_DEVELOPMENT_GOVERNANCE.md`,
  `LABFORGE_CURRENT_STATE.md`, and `LABFORGE_CONTEXT.md`. Governance overrides
  older workflow instructions; technical and historical documents remain
  sources of context and confirmed facts.
- Follow the milestone-scoped autonomous workflow and approval boundaries in
  the governance document.
- Preserve chemist/user mode versus Service/Manual mode, real topology, and the
  left-to-right process flow.
- Never treat `P1` or `P2` as inline pumps; aspiration and dispense are separate.
- Do not broadly redesign the manually positioned SVG, global layout, or CSS
  unless the approved milestone requires it.
- Inspect and preserve existing work. Isolate changes in another branch or
  worktree when appropriate; stop only if safe isolation is impossible.
- Keep changes cohesive and avoid unrelated refactoring or generated/dependency
  files such as `dist/` and `node_modules/`.
- For code changes run `npm run build` and relevant lint/tests. Documentation-only
  changes require diff/whitespace/status verification, not an application build.
- Self-review the complete local diff, but report concise changed-file, diff-stat,
  verification, risk, and final-status information unless focused content is
  requested.
