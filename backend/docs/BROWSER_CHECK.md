# Guided Demo browser check with fake transports

This development-only launcher reuses the existing FastAPI application, owned
executor, adapter composition and test fixture Serial/DYNAMIXEL transports. It
adds no production endpoint, diagnostic layer or device configuration. Both fake
transport factories are hardwired; no live adapter is selected by a CLI flag.
Fixture route order, calibration, readiness and current context are not physical
facts. Real devices, original project databases and production activation are
outside this check.

## Start

From the active backend checkout, using its existing development virtualenv:

```bash
cd /home/elvis/Documents/labforge-backend-multiphase
env -u LABFORGE_ARDUINO_PORT -u LABFORGE_SF_BOTTOM_VALVE_PORT \
  /home/elvis/Documents/labforge-backend/.venv/bin/python -m tests.browser_check \
  --state-dir /tmp/labforge-browser-check --port 8000
```

The launcher rejects nonempty live-port environment settings before importing
`app.main` or creating state. The `env -u` command clears only this process's two
port settings. Importing the launcher itself is inert. It prints
`FAKE TRANSPORTS ONLY`, its state directory and PID. It runs one worker on
127.0.0.1 without automatic reload. An occupied port is an error; do not terminate
an unrelated server to make room.

In another terminal, start the existing UI:

```bash
cd /home/elvis/Documents/labforge-ui-multiphase
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open http://127.0.0.1:5173/ and select Open Guided Demo, then Connect to backend.
The existing Vite proxy targets 127.0.0.1:8000. Initial system initialization is
optional before a run and required for a first standalone flush.

## State, timing and restarts

The first launch provisions a new fake bundle in an empty state directory and
writes `browser-check.json` with its explicit fake-profile marker and database
identities. Restart reopens the same three files with those identities. It never
repairs, resets or migrates an existing directory. Unknown/nonempty directories,
missing files, changed profile markers and symlinks are rejected. A partially
created fixture is preserved; use a new directory for an independent scenario.
Do not delete/recreate state to bypass a retained owner during a restart check.

Waits use the existing real monotonic timer, making Pause/Resume/Stop observable.
Each fake Arduino command adds 0.15 seconds of artificial latency by default;
`--command-delay` may set 0..1 seconds. This is test pacing, not physical timing.
Serial/SF adapter sessions, journals and lifecycle remain the actual code paths.
The fake fixture is freshly supplied after restart; old commands are not replayed
or promoted to physical trust.

Ctrl+C requests orderly shutdown/Stop. For an actual process-death scenario,
deliberately stop only the identified fake launcher's process and restart using
the same state directory. Graceful shutdown and process death are separate tests.

## Browser scenarios

Use explicit nonzero SF mixing and fraction durations and a delay/reaction hold
long enough to click controls. Reaction duration in the UI is entered in minutes;
SF, settling, delay and fraction durations are seconds. All values are test data.

- Complete a run and verify COMPLETED/READY, backend event history and a second run.
- Pause/Resume a started delay or reaction wait; Stop while running or paused.
- After clean Stop verify ABORTED/FLUSH_REQUIRED, blocked new-run entry, then
  explicit per-attempt maintenance confirmations, successful flush and a new run.
- Attempt competing Service work while running; backend exclusion must reject it.
- Refresh the page or interrupt UI connectivity; read current backend state on
  return, without automatic resubmission of Start or other commands.
- Stop during flushing, restart the same fixture and verify explicit recovery
  followed by mandatory flushing before a new run.

To inject a transport error, stop the fake server and restart it with the same
command plus `--fault-command N`. The Nth fake Arduino COMMAND in that process
raises an injected transport error. It is not a retry or alternate transport.
After the error, restart without that flag using the same state directory.
Historical unknown outcome evidence must remain; recovery/flush must be deliberate.

Manual browser results remain pending until those interactions are actually
performed and observed. The launcher's automated tests verify environment
rejection, complete HTTP execution with wall-clock waits, persistence across
restart, failure/recovery/flush/new run and refusal to reset/rebind foreign state.
