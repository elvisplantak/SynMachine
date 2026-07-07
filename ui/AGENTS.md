# AGENTS.md

## Communication

- Communicate with the user in Croatian/BHS.
- Keep code, variable names, function names, CSS class names, file names, commit messages, package names, and terminal errors in English.
- Quote terminal errors exactly. Do not translate error messages.

## Project context

This is a React + Vite + TypeScript UI mockup for LabForge.
The goal is to iterate quickly on UI/UX without introducing regressions.

## Working style

- Before editing code, briefly explain the plan.
- Prefer small, targeted changes.
- Fix only the issue requested by the user.
- Do not rewrite whole components unless explicitly asked.
- Do not change unrelated layout, spacing, margins, colors, architecture, or visual design.
- Preserve the existing UI style unless the user explicitly requests a design change.
- After editing, show the diff and list changed files.
- When possible, run the relevant check/build/test and report the result.

## UI-specific rules

- Be careful with global CSS changes.
- Avoid changing global margins, vertical spacing, or layout unless explicitly requested.
- For bug fixes, prefer local component/CSS fixes over broad layout rewrites.
- If a click/hover/focus issue is reported, verify that the whole intended interactive area is clickable and focusable, including text labels and icons.

## Safety

- If the requested change is ambiguous, ask a short clarification question.
- If a requested change may cause regressions, explain the risk before editing.
- Before changing LabForge UI/UX, SVG diagrams, topology, hardware-flow logic, protocol screens, or service/manual-control screens, read `LABFORGE_CONTEXT.md`.