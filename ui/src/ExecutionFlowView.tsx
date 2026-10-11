import { useEffect, useState } from "react";
import { readExecution } from "./guidedDemoApi";
import { FluidicScheme } from "./FluidicScheme";
import { flowPresentation } from "./executionFlow";
import type { FlowActivity } from "./executionFlow";

// Fast, read-only status sampling is independent of slower run-history reads.
// No replay, optimistic phase inference or commands; old backends stay static.
export function ExecutionFlowView() {
  const [activity, setActivity] = useState<FlowActivity | null>(null);
  const [state, setState] = useState("Reading current activity…");
  useEffect(() => {
    let alive = true;
    let next: ReturnType<typeof setTimeout>;
    let expiry: ReturnType<typeof setTimeout>;
    let controller: AbortController | undefined;
    const clear = () => { setActivity(null); setState("Current activity unavailable"); };
    const poll = async () => {
      const attempt = new AbortController();
      controller = attempt;
      const deadline = setTimeout(() => attempt.abort(), 1000);
      try {
        const status = await readExecution(attempt.signal);
        if (!alive) return;
        if (attempt.signal.aborted) throw new Error("Expired activity response");
        clearTimeout(expiry);
        const flow = status.flow_activity ?? null;
        const current = status.busy && status.executing && status.error === null
          && status.operation?.action === "RUN" && flow !== null
          && flow.run_id === status.run_id && flow.run_id === status.operation.run_id;
        setActivity(current && !document.hidden ? flow : null);
        setState(status.flow_activity === undefined ? "Live activity is not available from this backend" : "");
        expiry = setTimeout(clear, 1500);
      } catch {
        if (alive) clear();
      } finally {
        clearTimeout(deadline);
        if (alive) next = setTimeout(poll, 200);
      }
    };
    const visibility = () => { if (document.hidden) clear(); };
    document.addEventListener("visibilitychange", visibility);
    void poll();
    return () => {
      alive = false; controller?.abort(); clearTimeout(next); clearTimeout(expiry);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, []);
  const display = flowPresentation(activity);
  return <figure className="executionFlowView" aria-label="Commanded process flow">
    <FluidicScheme directions={display.segments} valves={display.valves} />
    <figcaption><strong>{state || display.label}</strong><span>Command-driven paths; fluid flow is not measured. Vessel fills are schematic.</span></figcaption>
  </figure>;
}
