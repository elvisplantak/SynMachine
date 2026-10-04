import { useEffect, useState } from "react";
import { readExecution, readMachine, readRun } from "./guidedDemoApi";
import type { DemoRun, ExecutionStatus, MachineSnapshot } from "./guidedDemoApi";

type Observation = {
  status: ExecutionStatus;
  machine: MachineSnapshot | null;
  run: DemoRun | null;
};

export function ExecutionAwareness({ onInspect }: { onInspect: () => void }) {
  const [observed, setObserved] = useState<Observation | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let next: ReturnType<typeof setTimeout>;
    let controller: AbortController;
    const poll = async () => {
      controller = new AbortController();
      const deadline = setTimeout(() => controller.abort(), 5000);
      try {
        const status = await readExecution(controller.signal);
        const machine = await readMachine(controller.signal);
        const id = machine?.interrupted_maintenance_id ? null
          : machine?.active_run_id ?? status.run_id ?? machine?.interrupted_run_id;
        const run = id ? await readRun(id, controller.signal) : null;
        if (alive) {
          setObserved({ status, machine, run });
          setError(null);
        }
      } catch (failure) {
        if (alive) setError(failure instanceof Error ? failure.message : "Backend read failed");
      } finally {
        clearTimeout(deadline);
        if (alive) next = setTimeout(poll, 1000);
      }
    };
    void poll();
    return () => { alive = false; clearTimeout(next); controller?.abort(); };
  }, []);

  const attention = observed !== null && (
    observed.status.busy || observed.status.executing || observed.status.error !== null
    || observed.status.retained_owner_id !== null
    || (observed.machine !== null && (observed.machine.state !== "READY"
      || observed.machine.active_run_id !== null || observed.machine.interrupted_run_id !== null
      || observed.machine.interrupted_maintenance_id !== null
      || observed.machine.active_execution !== null || observed.machine.active_maintenance !== null))
    || (observed.run !== null && ["RUNNING", "PAUSED", "ABORTING"].includes(observed.run.status))
  );
  const unavailable = error !== null || observed === null;
  const title = error !== null ? "Backend state unavailable"
    : observed === null ? "Checking backend execution"
      : attention ? "Backend execution needs attention" : "Backend execution status";

  return <aside className={`executionAwareness ${unavailable || attention ? "executionAttention" : ""}`}
    aria-label="Backend execution awareness" aria-live="polite">
    <div>
      <strong>{title}</strong>
      {error !== null ? <p role="alert">{error}. Current execution and readiness are unknown.</p>
        : observed === null ? <p>Current execution and readiness have not been read yet.</p>
          : <p>Machine: {observed.machine?.state ?? "Uninitialized"}
            {observed.run && ` · Run: ${observed.run.status} · Phase: ${observed.run.phase}`}
            {observed.status.busy && ` · Operation: ${observed.status.operation?.action ?? "Service / configuration"}`}
            {observed.status.retained_owner_id !== null && " · Hardware ownership retained"}
            {observed.status.error !== null && ` · Execution error: ${observed.status.error}`}</p>}
      <small>Static preview values are not current machine state. Opening execution controls sends no commands.</small>
    </div>
    <button type="button" onClick={onInspect}>Open backend execution</button>
  </aside>;
}
