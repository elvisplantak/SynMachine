import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { readExecution } from "../src/guidedDemoApi.ts";
import { isFlowActivity, flowPresentation } from "../src/executionFlow.ts";

const original = globalThis.fetch;
afterEach(() => { globalThis.fetch = original; });
const flow = { phase_execution_id: "phase", run_id: "run", operation_number: 2,
  operation_command_id: "command", kind: "ASPIRATE", route: "B1_TO_P1" };
const status = { configured: true, busy: true, executing: true, operation: { operation_id: "owned", action: "RUN", run_id: "run" },
  error: null, retained_owner_id: null, run_id: "run", automatic_resume_allowed: false };

test("flow status accepts optional legacy absence but rejects malformed, unsupported or contradictory activity", async () => {
  const reply = (value) => { globalThis.fetch = async () => new Response(JSON.stringify(value)); };
  for (const value of [undefined, null, flow]) {
    reply({ ...status, flow_activity: value });
    assert.deepEqual((await readExecution()).flow_activity, value);
  }
  for (const patch of [{ route: "UNKNOWN" }, { route: "P1_TO_REACTOR" }, { kind: "STARTED" }, { run_id: "" },
    { phase_execution_id: null }, { operation_command_id: null }, { operation_number: 0 }, { operation_number: "2" }, { arbitrary: true }]) {
    reply({ ...status, flow_activity: { ...flow, ...patch } });
    await assert.rejects(readExecution(), /flow activity is invalid/);
  }
  assert.equal(isFlowActivity({ ...flow, route: "COLUMN_TO_FRACTIONS", kind: "COLLECT", operation_command_id: null }), true);
});

test("syringe aspiration never lights the later dispense route and dispense reverses the pump connector", () => {
  const input = flowPresentation(flow).segments;
  assert.deepEqual(Object.keys(input).sort(), ["b1-v4", "v4-v6", "v6-v1", "v1-p1"].sort());
  assert.equal(input["v2-reactor"], undefined);
  const output = flowPresentation({ ...flow, route: "P1_TO_REACTOR", kind: "DISPENSE" }).segments;
  assert.equal(output["v1-p1"], "reverse");
  assert.equal(output["v2-reactor"], "forward");
  assert.equal(output["b1-v4"], undefined);
});

test("P2 separates reactor aspiration, SF filling, protected SF aspiration and column filling", () => {
  const make = (route, kind) => flowPresentation({ ...flow, route, kind }).segments;
  const reactor = make("REACTOR_TO_P2", "ASPIRATE");
  assert.equal(reactor["v3-p2"], "forward"); assert.equal(reactor["v7-sf"], undefined);
  const sfIn = make("P2_TO_SF_TOP", "DISPENSE");
  assert.equal(sfIn["v3-p2"], "reverse"); assert.equal(sfIn["v7-sf"], "forward"); assert.equal(sfIn["sf-v8"], undefined);
  const sfOut = make("SF_BOTTOM_TO_P2", "ASPIRATE");
  // The sf-v8 SVG path runs from V8.k2 toward the SF outlet, opposite to aspiration.
  assert.deepEqual(sfOut, {
    "sf-v8": "reverse", "v7-v8": "reverse", "v3-v7": "reverse", "v3-p2": "forward",
  });
  const column = make("P2_TO_COLUMN", "DISPENSE");
  assert.equal(column["v3-p2"], "reverse"); assert.equal(column["v7-v8"], "forward"); assert.equal(column["v5-column"], "forward");
  assert.equal(column["sf-v8"], undefined); assert.equal(column["bottom-fractions"], undefined);
  assert.deepEqual(Object.keys(make("COLUMN_TO_FRACTIONS", "COLLECT")).sort(), ["column-bottom", "bottom-fractions"].sort());
  assert.deepEqual(flowPresentation(null).segments, {}); assert.deepEqual(flowPresentation(null).valves, {});
});
