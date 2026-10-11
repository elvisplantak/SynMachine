export type FlowKind = "ASPIRATE" | "DISPENSE" | "COLLECT";
export type FlowRoute = keyof typeof routes;
export type FlowActivity = {
  phase_execution_id: string; run_id: string; operation_number: number;
  operation_command_id: string | null; kind: FlowKind; route: FlowRoute;
};
export type FlowDirection = "forward" | "reverse";
export type FlowValveState = "k1k2" | "k1k3";
// Directions follow each manually drawn SVG path, not its alphabetical ID.
const routes = {
  S_TO_P1: { kind: "ASPIRATE", label: "S → P1", segments: { "s-v6": "forward", "v6-v1": "forward", "v1-p1": "forward" }, valves: { V6: "k1k2", V1: "k1k3" } },
  B1_TO_P1: { kind: "ASPIRATE", label: "B1 → P1", segments: { "b1-v4": "forward", "v4-v6": "forward", "v6-v1": "forward", "v1-p1": "forward" }, valves: { V4: "k1k2", V6: "k1k3", V1: "k1k3" } },
  B2_TO_P1: { kind: "ASPIRATE", label: "B2 → P1", segments: { "b2-v4": "forward", "v4-v6": "forward", "v6-v1": "forward", "v1-p1": "forward" }, valves: { V4: "k1k3", V6: "k1k3", V1: "k1k3" } },
  P1_TO_REACTOR: { kind: "DISPENSE", label: "P1 → Reactor", segments: { "v1-p1": "reverse", "v1-v2": "forward", "v2-reactor": "forward" }, valves: { V1: "k1k2", V2: "k1k3" } },
  REACTOR_TO_P2: { kind: "ASPIRATE", label: "Reactor → P2", segments: { "reactor-v3": "forward", "v3-p2": "forward" }, valves: { V3: "k1k3" } },
  P2_TO_SF_TOP: { kind: "DISPENSE", label: "P2 → SF", segments: { "v3-p2": "reverse", "v3-v7": "forward", "v7-sf": "forward" }, valves: { V3: "k1k2", V7: "k1k2" } },
  SF_BOTTOM_TO_P2: { kind: "ASPIRATE", label: "SF → P2", segments: { "sf-v8": "reverse", "v7-v8": "reverse", "v3-v7": "reverse", "v3-p2": "forward" }, valves: { V8: "k1k2", V7: "k1k3", V3: "k1k2" } },
  P2_TO_COLUMN: { kind: "DISPENSE", label: "P2 → Column", segments: { "v3-p2": "reverse", "v3-v7": "forward", "v7-v8": "forward", "v8-v5": "forward", "v5-column": "forward" }, valves: { V3: "k1k2", V7: "k1k3", V8: "k1k3", V5: "k1k3" } },
  COLUMN_TO_FRACTIONS: { kind: "COLLECT", label: "Column → Fractions", segments: { "column-bottom": "reverse", "bottom-fractions": "forward" }, valves: {} },
} as const;

const nonempty = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;
export function isFlowActivity(value: unknown): value is FlowActivity {
  if (!value || typeof value !== "object") return false;
  const flow = value as FlowActivity;
  const keys = ["phase_execution_id", "run_id", "operation_number", "operation_command_id", "kind", "route"];
  if (Object.keys(value).length !== keys.length || !Object.keys(value).every((key) => keys.includes(key))
    || !nonempty(flow.phase_execution_id) || !nonempty(flow.run_id)
    || !Number.isInteger(flow.operation_number) || flow.operation_number < 1
    || !Object.hasOwn(routes, flow.route)) return false;
  return flow.kind === routes[flow.route].kind
    && (flow.kind === "COLLECT" ? flow.operation_command_id === null : nonempty(flow.operation_command_id));
}

export function flowPresentation(flow: FlowActivity | null): {
  segments: Partial<Record<string, FlowDirection>>;
  valves: Partial<Record<string, FlowValveState>>; label: string;
} {
  if (!flow) return { segments: {}, valves: {}, label: "No active transfer or collection" };
  const route = routes[flow.route];
  const action = flow.kind === "ASPIRATE" ? "Aspirating" : flow.kind === "DISPENSE" ? "Dispensing" : "Collecting";
  return { segments: route.segments, valves: route.valves, label: `${action}: ${route.label}` };
}
