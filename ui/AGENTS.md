# AGENTS.md

## Communication

- Communicate with the user in Croatian/BHS.
- Keep code, variable names, function names, CSS class names, file names, commit messages, package names, and terminal errors in English.
- Quote terminal errors exactly. Do not translate error messages.

## Project context

This is a React + Vite + TypeScript UI mockup for LabForge.
The goal is to iterate quickly on UI/UX without introducing regressions.

## Source of truth

- For now, the source of truth for the UI mockup is `src/App.tsx`, `src/App.css`, `src/index.css`, and the project context files.
- Generated build output is not source of truth.

## Working style

- Treat each user request as a narrowly scoped patch.
- Before editing code, briefly explain the plan.
- Inspect the relevant files before editing.
- Prefer small, targeted changes.
- Fix only the issue requested by the user.
- Do not make opportunistic improvements.
- Do not rewrite whole components unless explicitly asked.
- Do not rename files, move components, change architecture, or clean up unrelated code unless explicitly asked.
- Do not change unrelated layout, spacing, margins, colors, architecture, or visual design.
- Preserve the existing UI style unless the user explicitly requests a design change.
- After editing, show the diff and list changed files.
- When possible, run the relevant check/build/test and report the result.
- If the task is documentation-only, do not touch source code.

## Git hygiene

- Always check `git status --short` before editing.
- If the working tree is not clean, stop and report the existing changes before making new ones.
- Do not commit changes unless the user explicitly asks.
- After a successful change and verification, ask the user: `Promjena je spremna. Želiš li commit? (da/ne)`
- Commit only if the user explicitly confirms.
- If the user says the change is not good, ask whether to fix it or restore the previous version.
- After changes, always show `git diff` and `git status --short`.

## Generated and dependency files

- Do not commit `node_modules/`.
- Do not commit `dist/`.
- Do not edit generated build output in `dist/`; change source files instead.

## UI-specific rules

- Be careful with global CSS changes.
- Avoid changing global margins, vertical spacing, or layout unless explicitly requested.
- For bug fixes, prefer local component/CSS fixes over broad layout rewrites.
- Prefer local component/CSS changes over global CSS changes.
- Avoid broad changes in `src/index.css`.
- Keep changes small enough to review in one diff.
- If a click/hover/focus issue is reported, verify that the whole intended interactive area is clickable and focusable, including text labels and icons.

## SVG and topology protection

- The SVG physical scheme is sensitive and manually positioned.
- Do not change `viewBox`, coordinates, pipe routing, valve topology, physical flow, or component positions unless the user explicitly asks.
- Preserve the left-to-right physical process flow.
- Preserve the distinction between chemist/user mode and technical/service mode.
- Never treat syringe pumps P1/P2 as inline pumps.

## Safety

- If the requested change is ambiguous, ask a short clarification question.
- When uncertain, ask a short clarification question instead of guessing.
- If a requested change may cause regressions, explain the risk before editing.
- Before changing LabForge UI/UX, SVG diagrams, topology, hardware-flow logic, protocol screens, or service/manual-control screens, read `LABFORGE_CONTEXT.md`.

## Verification

- For code changes, run `npm run build`.
- When relevant, also run `npm run lint`.
- For documentation-only changes, no build is required, but still show the diff.
- Quote terminal errors exactly. Do not translate terminal errors.

## Final report

After every task, report:

- changed files
- what changed
- commands run
- build/lint result if applicable
- remaining risks or assumptions
- final `git status --short`
