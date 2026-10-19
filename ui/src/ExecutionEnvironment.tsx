import type { ExecutionStatus } from "./guidedDemoApi";

export function ExecutionEnvironment({ status }: { status: ExecutionStatus | null }) {
  const mode = status?.transport_mode;
  return <section className="demoPanel" aria-label="Execution connection">
    <strong>{mode === "LIVE" ? "Real devices" : mode === "FAKE" ? "Test devices — no physical movement" : "Device connection not identified"}</strong>
    {status?.profile_id && <p>Profile: {status.profile_id}</p>}
    <p>{mode === "LIVE" ? "Start requests physical execution. Check the recipe, current references and preparation before every attempt."
      : mode === "FAKE" ? "Recipes run on fake transports. Pumps and valves on the machine will not move."
      : "The current backend has not identified its transport mode. Do not assume that it is a simulation."}</p>
    {status?.maintenance_actions && status.maintenance_actions.length < 2 && <p>
      Some maintenance actions are not configured. After Stop or a fault, retained ownership and required maintenance still block a new run.
    </p>}
  </section>;
}
