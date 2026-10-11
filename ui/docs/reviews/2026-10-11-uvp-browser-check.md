# Recipe browser checks and UI polish — 2026-10-11

Scope: user-led localhost checks of the UVP software using only the existing
hardwired fake-transports browser composition. No live hardware, firmware upload,
production activation or main change. Independent acceptance remains pinned at
backend 8e22fd5d305d46d128f0aedc78bf2a0e36be8fa2 and UI
bf986cbb983b4d664070c6474627a62074d9584a; this subsequent UI polish is self-verified.

## Manual observations

The same marked fake bundle was retained at
/tmp/labforge-uvp-browser-20261011-CCY0PI. UI localhost 127.0.0.1:5173;
fake backend 127.0.0.1:8000. Screenshots in the user conversation establish:

- Test recipe version 1: ADD S 2 mL, WAIT 5 s. Save and review did not execute;
  explicit Start completed run a69bc477-4cd1-429d-8396-aadd0e997d28.
- Refresh/reopen retained the saved steps and completed run; current preparation
  fields/checks were blank and Start remained disabled until fresh preparation.
- A second explicit Start completed e462bda7-ebd3-4816-9777-775ebd1ad2bf with the
  same version 1, a distinct run ID and fresh preparation.
- Saving WAIT 30 s produced version 2 while the old completed run retained version 1.
- Version 2 run 871d4e70-d947-45b9-b3c4-1573d60bf233 showed BUSY/PAUSED/RUN during
  WAIT, then RUNNING after Resume and READY/COMPLETED/Idle at completion.
- Version 2 run 71094e52-28bb-4232-b554-d239be55deca stopped during WAIT:
  FLUSH_REQUIRED/ABORTED/Idle. Fresh five maintenance confirmations and Flush
  returned Machine READY; the old run remained ABORTED.
- Adding Reactor to SF 3 mL after ADD S 2 mL was saved as version 3. Review rejected
  step 3 for requesting more liquid than the preceding configured contents.
  The initial expectation that saving would reject this was corrected: save is
  structural validation; preview and execute enforce flow validation. No software
  bypass was found and no change to backend policy is needed.

Read-only final API checks confirmed Machine READY, busy/executing false,
error null, retained owner null; version 2 completed/aborted snapshots unchanged.
Latest saved recipe ae85cb11-b9db-477f-9717-1e231beb54fa is intentionally invalid
version 3, preserved rather than rewritten or deleted. The user can later edit it
and save a new version; it cannot pass review in its current form.

These checks do not establish physical movement, delivered volume, wet behavior,
or new manual acceptance of the full SF/Column/COLLECT procedure.

## Approved UI changes

- Recipes navigation, Procedure Builder heading and My Recipes library; internal
  UVP identifiers stay stable. All recipe UI text/errors/progress now English.
- CSS gives preparation/maintenance checkboxes fixed width and places them on the
  left next to wrapping label text. Span-wrapped text retains native label toggling.
- Existing browser and API expectations follow English text. Two new real DOM
  geometry/label-toggle regressions cover nine confirmation rows on wide/narrow
  screens. No executor, API contract, persistence or device setting changes.
- User guide explains separate Save / Review / Start checks.

## Verification

43 UI tests passed, including 20 actual headless Chrome cases, zero skipped.
UI lint, TypeScript/Vite build and complete diff/whitespace checks passed.
JS 330.39 kB (gzip 90.71); CSS 52.62 kB (gzip 10.47).
Backend and firmware are unchanged; their prior accepted test results remain
historical, not claimed as newly rerun. Fake bundle and saved recipes are preserved.
