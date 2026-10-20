> Historical pre-migration preparation document. Current publication state is in
> [../../docs/PUBLICATION.md](../../docs/PUBLICATION.md) and the current project
> description is in [../../README.md](../../README.md).

# SynMachine public-release preparation — 2026-10-19

Status: inspection and protective ignore rules completed; publication decisions
remain open. All repositories remain private. No default branch, shared history,
repository visibility, active profile, database, recipe, device or runtime changed.
The owner explicitly authorized reading/searching firmware recovery artifacts for
this publication audit; those artifacts were inspected but not modified.

## Audited source checkpoints

| Repository | Source HEAD | Reachable commits | Reachable blobs |
| --- | --- | ---: | ---: |
| UI | `6e052c9e9e98f43fba4d5631dc38bf75839e6f70` | 140 | 325 |
| Backend | `fa3bb9f8336ffed6ba814a208397a88b3add7971` | 89 | 457 |
| Firmware | `da9ca15a3fb211e449653810d5656dec4577ee50` | 86 | 508 |

Remote heads/tags were fetched without pruning. Each repository is non-shallow.
All 37 UI, 32 backend and 26 firmware advertised remote heads/tags resolved to
locally available objects covered by the inspection.
At audit time every local commit was reachable from a fetched origin ref, including
branches without an explicitly configured upstream. Current source worktrees were
clean. The older UI worktree was clean; the older backend worktree contains two
untracked runtime databases, `labforge.db` and `labforge-arduino-commands.db`.
Those databases were not added, deleted or treated as missing source code.

GitHub default `main` is not the current implementation: relative to the audited
source it has 2 unique commits versus 125 on UI, 1 versus 85 on backend, and 1
versus 79 on firmware. Publishing requires deciding how to present/integrate the
current feature branches; this audit does not merge or change the default branch.

## Credential and history checks

Gitleaks 8.30.1 was obtained from the official gitleaks/gitleaks release; the
Linux archive SHA-256 matched the release checksum file. Default detection rules
were used with full redaction and no repository ignore list. Git scans used
`--all --full-history` and ignored inline gitleaks allow comments. Separate scans
covered exported current tracked files and Git author/committer/message metadata.
All nine scans completed successfully with zero detected secrets. Supplemental
inspection enumerated reachable blobs and scanned printable strings from binary
blobs; a targeted long literal credential-assignment search found zero candidates.
This is a bounded detection result, not proof that no undiscovered secret exists.
Opaque/compressed/binary content and unknown credential formats remain limitations.

No tracked private-key, environment-secret or runtime database file was found at
the audited HEADs. The private live operator credential is outside the repositories;
its value was not printed, copied or committed. Test credential labels are test
inputs, not evidence of a deployed credential. Local raw audit metadata/logs are
kept in a private `/tmp` directory and are not publication inputs.

Ignore rules now cover local .env files (preserving .env.example), key files,
SQLite/DB runtime files and logs, including sidecars. These rules do not remove
files already in history; no history rewriting was performed or found necessary
by the secret scans.

## Other GitHub publication surfaces

Read-only GitHub API checks reported all three repositories private, no detected
project license, zero workflow runs, zero Actions artifacts, zero releases, zero
issues/pull requests and zero commit comments. Wikis and Pages are disabled.
There were no corresponding logs or release attachments to inspect. No GitHub
settings, secrets or permissions were changed.

## Public metadata and provenance

Source/history contain a consistent author identity, local user paths and stable
USB adapter identifiers. Those are identifying technical metadata, not login
credentials. They remain intact, especially in bound live profiles and historical
commissioning evidence; anonymizing a live profile silently would invalidate its
profile/state binding. Historical review refs remain exact.

No project LICENSE/NOTICE file or in-source copyright/license marker was found.
This does not establish ownership of recovered/legacy code. Confirm source
provenance and choose the project license before making an open-source claim.
Direct installed dependency metadata reports MIT for most UI tools/React, Apache-2.0
for TypeScript and Dynamixel SDK, BSD-family licensing for pyserial/uvicorn, and
MIT for FastAPI/Pydantic/pytest/Ruff. This is a direct dependency inventory, not a
complete transitive license audit or a license for this project's own code.
Firmware build dependencies/frameworks also retain their upstream terms; any
future redistributed binary bundle needs its own notice/obligation review.

## Prepared changes and remaining decisions

- Added protective ignore rules in all three repositories.
- Prepared component README discussion drafts; root README text awaits agreement.
- Recorded the owner's present material scope in HARDWARE_CONFIRMATIONS.md:
  PTFE valves/tubing not installed and chemical compatibility not established.
- Choose a license and confirm provenance of reused/recovered source.
- Agree the final README and presentation of the current implementation branch.
- Review this concrete result before any public visibility change. No visibility
  change is authorized by the existence of this report or a draft license section.

The prior software test results remain those of the unchanged source checkpoint:
51 UI and 1937 backend tests, lint/build/Ruff passed. This preparation changes only
documentation and ignore rules; verification uses diff/whitespace/status, ignore
behavior checks and repeat secret scans, without starting devices or rebuilding
firmware. Ignore behavior checks passed in all three repositories, including the
.env.example exception. Final worktree scans including the new documents each
completed with zero findings. No raw secret or personal database content is
included in this report.
