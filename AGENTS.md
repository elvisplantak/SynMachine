# SynMachine repository working rules

- Communicate in Croatian/BHS; keep code, identifiers, paths and commits English.
- Before work read `docs/LABFORGE_DEVELOPMENT_GOVERNANCE.md`,
  `docs/LABFORGE_CURRENT_STATE.md` and `docs/LABFORGE_CONTEXT.md`.
- Read the relevant component `AGENTS.md` before component work.
- Governance defines approval boundaries. Software work never authorizes physical
  motion, real Serial access, firmware upload, EEPROM changes or state repair.
- Never access, search, list, diff, summarize, modify or use `firmware/recovery/`
  without explicit authorization for that exact action. Migration authorization
  covers unchanged import/integrity checks only, not future recovery work.
- UI owns interaction/visualization, backend owns lifecycle/routes/orchestration,
  firmware owns pins and low-level device execution. Do not invent hardware facts.
- Preserve existing work and historical review records. Original review commit
  IDs map to imported IDs in `docs/history/`; do not relabel migration as an
  independent acceptance of new execution behavior.
- Use component working directories for checks. Run relevant tests/lint/build
  after executable changes and diff/whitespace/status checks for docs-only work.
- Git identity for this project is Elvis with the owner's GitHub noreply address;
  never use example.com as a commit email. Do not alter global Git settings.
