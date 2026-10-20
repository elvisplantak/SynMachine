# Publication readiness verification — 2026-10-20

## Scope and authorization

The owner approved integrating the English README, supplied photograph and
Apache-2.0 license into main, completing publication checks and editing GitHub
presentation. The owner confirmed that the old code is their own. Their request
to discuss the recovery topic separately is preserved: no new recovery access or
execution was performed during this final pass, and visibility remains private
pending that conversation/final publication decision.

## Licensing and attribution

- Root LICENSE is the official unmodified Apache License 2.0 text; NOTICE
  attributes original project software/documentation to Elvis.
- The owner confirmed ownership of the old project code; absence of headers
  was not treated as ownership evidence.
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) inventories all 76 non-root UI
  lockfile entries, 21 active Python distribution dependencies and installed
  firmware library/framework/toolchain metadata. All inspected entries provide
  license information. Upstream terms remain in effect; this is not a grant to
  relicense dependencies or a complete review of future binary distributions.
- No vendored production dependency source was identified in the current
  non-recovery application source scan. No compiled firmware release or packaged
  dependency bundle is created here. Protected legacy provenance/secret evidence
  remains that of the previously authorized audit and unchanged migration.

## Secret and privacy checks

Gitleaks 8.30.1, default rules, full redaction and ignored inline allow comments:

- Named Git history excluding protected recovery paths: 320 commits with
  matching path changes scanned; zero findings.
- Exported tracked-file snapshot excluding protected recovery: 464 files at
  the initial final-pass checkpoint; zero findings.
- Author/committer/commit-message metadata across all 322 then-reachable
  commits: zero findings.
- New publication documents are included in the final refreshed snapshot scan.

This final pass deliberately excludes protected recovery content. Prior complete
source/history scans covered recovery under its earlier audit authorization;
[the migration verification](MIGRATION_VERIFICATION.md) records the unchanged
import/integrity check. These are bounded detection results, not proof against
all possible secrets or unknown credential formats. Local usernames/paths and
stable USB hardware identities remain intentional technical metadata as recorded
in the original audit; operator credentials and live databases are not imported.

Ignore checks passed for local environment files, keys, runtime DB/sidecars,
node_modules and PlatformIO outputs. `.env.example` remains eligible for tracking.
No application code, bound profile, runtime state or installed firmware changed.

## GitHub and presentation

Read-only GitHub API checks found zero Actions runs, Actions artifacts, releases,
issues/pull requests and commit comments. Wiki and Pages are disabled. No content
on those surfaces required removal; no credentials/secrets were printed.

The GitHub description and seven relevant topics are set. GitHub's Markdown API
rendered the README successfully with one descriptive prototype image. The PNG
matches the supplied file byte-for-byte. Local Markdown links, whitespace and
Git status checks passed. Root README, LICENSE, NOTICE and image are integrated
into main by the approved fast-forward; remote identity/content verification is
performed after push. No GitHub combined statuses/check runs were present on the
README checkpoint; local checks are reported as local evidence, not GitHub CI.

## Existing functional validation

This publication pass changes documentation, licensing and presentation only.
The complete unchanged-code results remain those recorded in
[MIGRATION_VERIFICATION.md](MIGRATION_VERIFICATION.md): 1937 backend tests, 51 UI
tests including 24 real-browser fixtures, firmware native/profile/host checks,
lint/build and Mega compilation passed. Rebuilding or physical execution is not
needed for this documentation-only checkpoint; no device was connected by it.

The original three repositories and their backups remain private and unchanged.
Public visibility is a separate remaining action; the current repo stays private.

## Follow-up decision — 2026-10-20

The owner resolved the separate recovery publication question: retain that
archive for public access. Ownership was already confirmed. No new recovery
reading, search, modification or execution accompanies this decision.

The approved README acknowledgment names Professor Lee Cronin and the Cronin
Group at the University of Glasgow and links to the official group site. This
follow-up changes documentation only. Publication preparation is complete;
visibility remains private until the final instruction to make it public.

## Public visibility completed — 2026-10-20

The owner explicitly authorized making `elvisplantak/SynMachine` public. The
GitHub API confirmed `private: false`, `visibility: public`, default branch main
and the detected Apache-2.0 license. Unauthenticated HTTPS requests independently
returned the repository page and public repository API. Anonymous raw requests
for README, LICENSE and the prototype PNG matched their local bytes exactly.
The original three repositories were not changed by this operation. No new
recovery access, source-code change, firmware upload or physical action occurred.
