# Migration verification — 2026-10-20

## History and source integrity

- Verified three complete original `git bundle --all` backups before any copied
  history was changed. Checksums are recorded in history/integrity-verification.json.
- Imported all 318 named-history commits: UI141, backend90, firmware87. No commit
  pruning; all 125 source branch targets retained under history/<component>/.
- For every commit, original tree object equals imported component subtree object;
  messages, names, dates/timezones and mapped parent graph match. Raw message bytes
  independently match for all 318 commits. None of these source commits was signed.
- All author/committer email metadata in the new history uses the owner's GitHub
  noreply address. Original histories remain in private source repos and bundles.
- Current file comparisons: UI58, backend168, firmware205 source files unchanged.
  The only 17 changed component files are documentation/rules. No application,
  test, dependency, lockfile, firmware configuration or recovery bytes changed.
- All four protected recovery artifacts match their original blob IDs. This
  unchanged copy/integrity check is covered by the explicit migration approval.
- Live profile JSON SHA-256 remains
  `7eafee27d43855b271cda3c3c9d17834b26182108cffbfda8b866867dc06498f`.
- `git fsck --full` and diff/whitespace checks passed. New/edited Markdown links
  checked locally. Original source HEADs/worktrees remain unchanged.

## Checks run from the new checkout

| Check | Result |
| --- | --- |
| Backend complete pytest suite | 1937 passed in 129.35 s |
| Backend Ruff | Passed |
| UI tests | 51 passed, 24 actual browser fixtures, zero skipped |
| UI lint | Passed |
| TypeScript/Vite production build | Passed |
| Firmware native, `-Wall -Wextra -Werror` | 211 passed |
| Mixer pin-discovery native profile | 6 passed |
| Firmware host-tool fake unit test | 1 passed |
| Mega 2560 compile | Passed; no upload |

Mega resources: 41,056 / 253,952 flash bytes and 3,148 / 8,192 static SRAM bytes,
matching the previous recorded firmware build. UI output: JS337.13kB/gzip92.44,
CSS53.04kB/gzip10.58. Dependency installation/build outputs remain ignored.
Existing installed tool environments were reused for backend/PlatformIO checks;
UI dependencies were installed from the unchanged lockfile in this checkout.
No actual hardware transport was opened by these checks.

## Publication safeguards

Final Gitleaks 8.30.1 scans of the combined named history, staged tracked files
(including new documentation) and commit metadata each passed with zero findings.
The official pinned archive checksum was verified before scanning.
Ignore behavior retains `.env.example` while excluding credential/key, database,
sidecar, log and generated dependency/build files. No operator credential or live
state is imported. This is bounded detection, not a guarantee against all secrets.
The new GitHub repository remains private; license/public-visibility decisions
are still pending. Original repositories are not force-pushed, removed or archived.
