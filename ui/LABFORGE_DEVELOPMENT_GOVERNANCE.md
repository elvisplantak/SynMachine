# LabForge Development Governance and Independent Review Workflow

This document is the authoritative and overriding source for the current
LabForge development workflow, agent roles, approval boundaries, and review
process. If it conflicts with older workflow instructions, this document takes
precedence. Other project documents remain useful as historical context and
technical information, but may contain outdated implementation status or
superseded workflow decisions.

## Roles

- Codex is the primary implementation agent and leads development.
- ChatGPT is the independent architectural, safety, protocol, recovery, and
  integration reviewer.
- The user owns product intent, unconfirmed physical facts, meaningful competing
  product choices, risky actions, and physical-execution authorization.

## Autonomous development scope

The user has granted Codex standing authorization to inspect, design,
implement, test, build, diagnose, self-review, update implementation-status
documentation, create feature branches, stage, create local commits, and push
Codex feature branches within the currently approved development phase.

Codex may autonomously complete all safe, non-blocked software milestones
inside that approved phase. It should not stop for review or approval after
every file edit, test, correction, commit, or other mechanical step.

Before entering a materially different or riskier phase, Codex recommends the
next phase and obtains concise user approval. In particular, completing
no-motion protocol foundations does not authorize actuator implementation,
firmware upload, or physical execution.

## Normal workflow

Within the approved phase, Codex normally:

1. inspects canonical context, code, tests, and Git state;
2. protects unrelated work and isolates overlapping work in another branch or
   worktree when needed;
3. defines and implements the smallest cohesive slice;
4. adds or updates tests;
5. runs focused and complete relevant verification;
6. reviews the complete local diff and resource impact;
7. updates implementation-status documentation;
8. commits and pushes the verified feature branch; and
9. provides a concise checkpoint report for the user and independent reviewer.

A dirty tree is not an automatic stop. Existing work must be inspected and
preserved. Stop only when safe isolation is impossible or changes overlap the
authorized scope in a way that cannot be resolved safely.

## Actions requiring explicit user approval

Codex must ask before:

- merging or directly modifying `main`;
- deleting branches or rewriting shared history;
- destructive or difficult-to-recover operations;
- creating or changing a PR when its publication or final scope needs a user
  decision;
- clearing, repairing, migrating, or provisioning EEPROM;
- uploading firmware or opening a Serial monitor against real hardware;
- homing or moving any physical actuator;
- running no-load, liquid, or other physical tests;
- selecting unconfirmed wiring, pins, switch contact mode, electrical polarity,
  motor/valve direction, angles, steps, calibration, or safe fluidic routes; or
- resolving a meaningful product or safety choice with competing alternatives.

Software authorization never implies physical authorization.

## Canonical sources and repository ownership

- `LABFORGE_CONTEXT.md` is canonical for system-level context.
- `LABFORGE_CURRENT_STATE.md` is canonical for the concise current development
  checkpoint.
- Firmware `HARDWARE_CONFIRMATIONS.md` is canonical for confirmed physical
  hardware facts.
- Firmware `docs/LABFORGE_SERIAL_PROTOCOL_V1.md` is canonical for software
  communication semantics.
- Current code and passing tests establish actual implementation state.

Frontend owns visualization and user interaction. Backend owns lifecycle,
planning, durable intent, route decisions, recovery policy, and orchestration.
Firmware owns pins, motor direction, stepping, homing, debounce, low-level
timeouts, and device execution. Arduino must not contain the complete Guided
Demo workflow. Frontend-disabled controls are not a safety boundary. Symbolic
backend routes do not authorize physical execution, and software completion is
not proof of physical movement.

## Physical and safety boundaries

- Never invent unconfirmed wiring, pins, polarity, direction, angle, step count,
  calibration, sensor capability, or safe physical behavior.
- `P1` and `P2` are syringe pumps, not inline pumps.
- Aspiration and dispense are separate operations.
- Pump homing can move fluid and requires a physically verified safe route.
- Topology, actuation, leak testing, calibration, and end-to-end execution are
  separate confirmation levels.

If a physical fact blocks one task, Codex asks the user a concrete question and
continues unrelated safe work where possible.

## Independent review checkpoints

Meaningful independent review gates include framing/parsing/serialization,
EEPROM boot identity, handshake/session behavior, status queries, command
lifecycle and duplicate caching, first dispatch, first Service actuator,
homing/limit behavior, backend serial integration, fault injection, upload
readiness, first no-load test, first liquid-route test, and end-to-end Guided
Demo execution.

Reviews use focused evidence: relevant commits or diffs, specific source files,
test results, and build/resource metadata. Passing tests alone do not prove
physical readiness. Large review bundles and repeated review of mechanical
substeps are avoided.

## Protected firmware recovery artifacts

Never access, search, list, diff, summarize, modify, or use anything under
`~/Documents/labforge-firmware/recovery/` unless the user explicitly authorizes
that exact action. Recovery artifacts are not current production behavior.

## Reporting and continuity

Codex keeps reports concise: branch/HEAD, changed files, functional result,
tests/build/lint, relevant resource usage, `git diff --check`, final Git status,
limitations, and real decisions requiring user input.

`LABFORGE_CURRENT_STATE.md` is updated at meaningful checkpoints so a new
session can determine what is complete, what is in progress, what comes next,
and which physical decisions remain unresolved. Detailed history remains in Git
and technical documents rather than being duplicated there.
