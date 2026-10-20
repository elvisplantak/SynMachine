# Verified repository consolidation — 2026-10-20

The owner authorized combining the three repositories and correcting the
placeholder author email. Work was performed in separate copies. Original local
repositories, original GitHub repositories, runtime state and installed hardware
were not rewritten, removed, renamed, moved or activated.

## Inputs and imported checkpoints

| Component | Original selected HEAD | Imported selected HEAD | Verified commits |
| --- | --- | --- | ---: |
| ui | `57a2f5c020ee26240c43cfbea5f548bb2df4ecc1` | `3c9cedb4b78f1f54bb7aa5082052d00ac6c7c2c1` | 141 |
| backend | `155d0c597b24c6fe80f6589178b130bb9d4f9918` | `6da60322c91b52c11c6d3a455376d954f27256fc` | 90 |
| firmware | `05ad24703f5fec350f04a67f0c14a9bb1b3af90d` | `77c7295153fdf3eedc5e4bc9234db713fbc95ab8` | 87 |

All named local branches plus fetched origin branches were imported under
`history/<component>/<original-branch>`. There were no source tags. No commit was
pruned. `main` joins the three selected current histories in their own component
directories. Legacy `main` tips and any side branches remain separately reachable;
their differing work consists of historical governance/context documents, whose
current rules are consolidated under `docs/`.

## Integrity and attribution

For every one of the 318 imported commits, verification matched the original
file tree to the imported component subtree and checked commit messages, names,
timestamps/timezones, parent graph and branch targets. A further raw-message-byte
check and final source-file/blob comparison are recorded in the verification
report. File modes and binary bytes are preserved by tree-object equality.

Only the matching `Elvis <elvis@example.com>` author/committer identity is mapped
to `Elvis <310644594+elvisplantak@users.noreply.github.com>` during import. Imported
commits retain their original dates/messages. New commit IDs result from corrected
metadata and the component path prefix; original review records are not rewritten
to pretend an independent review of this migration occurred.

Private editor/session refs were retained in the backups but are not publication
branches. The original repositories remain available privately for exact original
IDs. [Commit and branch maps](history/README.md) resolve those IDs in this repo.

## Backups and rollback

Verified full `git bundle --all` backups and SHA-256 checksums are stored locally
under `/home/elvis/Documents/synmachine-migration-backups/2026-10-20/`. Each bundle
passed `git bundle verify` before any rewrite of a copy. The backup and migration
manifests record source refs, selected heads, bundle checksums and complete maps.
The backup directory is owner-only; it is not committed or published.

Rollback requires no alteration of the old repositories: continue using their
unchanged worktrees/remotes. The new repository can be kept separately. Never
delete databases or reset device state as part of a repository rollback.

## Deliberate current-tree documentation changes

The root README and component READMEs now describe the current system and agreed
material scope. Root governance/current-state/context files replace sibling-path
assumptions, component AGENTS files point to them, and old UI state/context files
are labelled historical. Runtime source, frontend geometry, tests, dependency
manifests/lockfiles, firmware build configuration, live profile JSON and recovery
artifacts remain byte-identical to the selected original heads.

No project license is selected by this migration. Old repositories remain
private and unchanged; the new repository is private pending publication decisions.
