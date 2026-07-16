# LabForge backend working rules

- Communicate with the user in Croatian/BHS. Keep code and technical identifiers in English.
- Before backend work, read `../labforge-ui/LABFORGE_CONTEXT.md`; it is currently the canonical LabForge system source of truth.
- Inspect Git status and the current branch before edits.
- Use a separate, clearly named branch for each experiment.
- Keep changes small and targeted. Do not perform unrelated refactoring.
- Do not commit, push, merge, delete branches, or modify `main` without explicit user approval.
- Quote terminal errors exactly.
- Run relevant tests, lint, the full relevant diff, and final Git status.
- The backend owns domain validation, run state, phase permissions, route planning, and safety decisions.
- Arduino firmware owns pin assignments and low-level device execution.
- Disabled frontend controls are not a safety boundary.
- P1 and P2 are syringe pumps with separate aspiration and dispense phases, never inline pumps.
- Do not invent hardware capabilities or pin assignments.
