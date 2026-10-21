# SynMachine current development state

- Checkpoint date: 2026-10-21
- Repository: `elvisplantak/SynMachine` (public consolidated repository)
- Local checkout: `/home/elvis/Documents/SynMachine`
- Branch: `commissioning/full-stroke-wet-test` (wet startup failed; owner retained; diagnostics pending);
  imported histories under `history/ui/`, `history/backend/`,
  `history/firmware/`.

## Repository consolidation

The user explicitly authorized one repository and corrected historical commit
authorship. All 318 source-history commits were imported and verified against
original file trees, dates, messages, parent graph and branch targets. Author
metadata now uses Elvis and the owner's GitHub noreply address. The original
repositories/remotes/worktrees remain untouched and private. Verified full bundles
are retained locally outside the new repo. See MIGRATION.md and docs/history/.

The root README and component instructions describe the agreed colored-liquid
mechatronic scope, existing silicone/medical-plastic parts and planned PTFE/glass
upgrades. Runtime code, SVG geometry, tests, dependency/build inputs and bound live
profile JSON are unchanged. The protected recovery artifacts were copied and
verified unchanged under the migration authorization; future access remains gated.

## Existing software and physical boundaries

Recipes, command-driven flow animation and explicit live Recipes preparation
retain their original independently reviewed scopes. The original review records
remain under ui/docs/reviews/; resolve their original IDs using docs/history maps.
Migration validation does not extend those reviews to new execution behavior.

The existing live profile remains nominal, with no configured automatic Recovery/
Flush. Stop/fault can retain mandatory maintenance and block a subsequent run.
Existing state/credentials are outside this checkout and are neither copied nor
reprovisioned. The migration does not connect to devices, start or stop an old
server, initialize references, issue motion, upload firmware or change EEPROM.
Old UI snapshots contain historical session IDs and are not live-state evidence.

Installed firmware is now the verified dc7a53f artifact recorded below. Physical
readiness and current references need fresh explicit operator confirmation before
any future real-device action. The liquid test has been requested; execution
awaits completion of the wet plan and fresh operator readiness.

## Verification and next steps

Migration checks passed: 1937 backend, 51 UI (24 browser), 211 native firmware,
6 mixer-profile and 1 host-tool unit test; lint/build passed. Mega uses 41056 flash
and 3148 static SRAM bytes, unchanged. Details: MIGRATION_VERIFICATION.md.

On 2026-10-20 the owner selected Apache-2.0, approved the English README and
provided a prototype photograph. LICENSE, NOTICE, README/photo and dependency
license/publication verification records are integrated into main. The owner
confirmed ownership of the old code. GitHub description/topics are configured;
GitHub Markdown rendering, image identity, local links, ignore rules and redacted
secret scans passed within the documented scope. No new recovery access was
performed: the owner requested a separate discussion; prior full-audit and
unchanged-import evidence remain applicable.

Follow-up on 2026-10-20: the owner decided to retain the recovery archive for
public access and approved a README acknowledgment of Professor Lee Cronin and
the Cronin Group at the University of Glasgow. The acknowledgment links to the
official group site and describes SynMachine as independent. The recovery
publication question is resolved without new recovery access or modification.

Only documentation/licensing/image/presentation changed; runtime behavior and
physical state are unchanged. On 2026-10-20 the owner explicitly authorized public
visibility; `elvisplantak/SynMachine` is now public. Anonymous repository/API and
README/LICENSE/photo access were verified, including exact raw-file contents.
The original component repositories remain private and unchanged. Publication is
complete; no further publication approval is pending. Future physical/liquid tests
still require fresh operator readiness and authorization. See PUBLICATION.md and
PUBLICATION_VERIFICATION.md.

## Supervised wet test preparation — 2026-10-21

The owner requested B1 colored water -> Reactor (one nominal full-stroke 20 mL)
-> SF -> 20 s mixing -> P2 -> Waste, excluding Column/carousel and deferring
flushing. B2 is ordinary water. The owner now confirms S filled, intake submerged
and Reactor empty, and approves two 5 mL Reactor-to-P2-to-Reactor priming cycles
after filling, alongside the two approved 5 mL S-to-P1-to-Waste cycles. SF empty, mixer
free, Waste clear and USB connected were reported; motor power is OFF.

On this feature branch, firmware adds explicit PUMP_ASPIRATE_FULL_STROKE only
from trusted empty20500, with stable HOME, bounded20500 pulse count and early-HOME
failure. Ordinary move-zero remains invalid; Recipes' ordinary planner remains
unchanged. SF interval is prepared at1667us (~600 pulses/s), explicitly approved
as a trial. Host capability limit is10 to accept the updated HELLO, without
implicit command fallback on older firmware. No live profile/state binding,
existing journal, installed firmware, device connection or physical motion is
changed by preparation. Verification:220 native +6 mixer-profile tests,1937
complete backend tests plus two additional host cases (131 focused), Ruff and
Mega build passed. Mega41570 flash/3176 SRAM (+514/+28); prepared HEX SHA256
61feb4425fddee73799191faf5a1bf98bb684db601a598712b30a7fe8a1c0d45.
Previous installed HEX matched its recorded hash and is preserved separately.
Upload completed with explicit owner approval and motor power OFF: exact
dc7a53fcdd93315965bf82ba143bf4def17688e7 HEX, signature 0x1e9801, all 41570 flash
bytes verified, exit 0. No actuator command, application Serial monitor, EEPROM
provisioning or wet test. New stroke/speed remain physically unverified.
The fixed supervised runner is prepared at backend/app/wet_reactor_sf.py with
71 fake regressions and unchanged existing live profile/bundle binding. It uses
a single retained owner and the existing Arduino/SF/wait journals; no Column
reference is invented. Exact plan, bootstrap, follow-ups and single-use boundary:
firmware/docs/commissioning/2026-10-21/WET_TEST_PLAN.md. Verification: all 2010
backend tests passed (71 new), full Ruff check and whitespace checks passed.
Firmware source/HEX is unchanged since the approved upload. Next: fresh powered readiness, Waste air-gap/free-mixer checks
and explicit execution approval for this concrete plan. No new application
connection or actuator command has occurred. Preparation/flash verification
are not physical test acceptance. Evidence:
firmware/docs/commissioning/2026-10-21/README.md.

## Wet startup failed; read-only diagnostic preparation

The explicitly approved first attempt in boot 111 stopped on ordinary P1
PUMP_HOME with PUMP_MOTION_TIMEOUT, execution_started=true: 12 Arduino commands
completed, 1 failed, SF CLOSE completed. No priming, liquid transfer, P2 motion
or mixer START occurred. Both ports closed; existing live owner remains
BLOCKED at generation 1. No retry, re-home, owner release or reprovisioning.

Operator correction: P1 may only be near HOME, replacing the earlier pressed
assertion. Motor power last confirmed ON; OFF was requested, not confirmed.
Do not continue the fixed runner or manufacture a trusted pump zero. Exact
evidence: firmware/docs/commissioning/2026-10-21/wet-01-result.json.

Read-only QUERY_STATUS fields p1_home_active/p2_home_active are prepared to
distinguish input level from a physical proximity guess. They do not change
motion limits/timing, HOME semantics or reference trust. Diagnostic firmware
is not installed; dc7a53f remains installed. Verification passed: 224 native,
6 mixer-profile, 2025 complete backend (112 focused), Ruff and Mega. Image:
42062 flash/3184 static SRAM; metadata in commissioning pump-home-diagnostics-artifact.json.
Mega warnings are 4 upstream Arduino unused parameters, zero project warnings.
Next: explicit upload approval with motor power OFF and
permission for read-only observation are required before any new real access.
A subsequent full cycle still needs deliberate reconciliation of the retained
owner, confirmed HOME/reference and fresh powered readiness; never clear its
history or select a new bundle to bypass this failed attempt.
