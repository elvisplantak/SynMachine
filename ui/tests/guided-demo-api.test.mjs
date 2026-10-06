import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import {
  createRun, maintenanceCommand, newRunBlockReason, readExecution, readMachine,
  readRun, runCommand, readEvents, stopOperation, initializeMachine, submitCurrentInput, cancelCurrentInput,
} from "../src/guidedDemoApi.ts";

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });
const execution = {
  configured: true, busy: false, executing: false, operation: null, error: null,
  retained_owner_id: null, run_id: null, automatic_resume_allowed: false,
};
const machine = {
  state: "READY", active_run_id: null, interrupted_run_id: null,
  interrupted_maintenance_id: null,
  active_execution: null, active_maintenance: null,
};
function reply(body, status = 200) {
  globalThis.fetch = async () => new Response(JSON.stringify(body), { status });
}

test("missing executor does not fall back to domain-only start", async () => {
  reply({ detail: "owned application execution is not configured" }, 503);
  await assert.rejects(readExecution(), /not configured/);
  assert.ok(newRunBlockReason(null, null));
});

test("retained owner and every active intent block a new run even in READY", () => {
  assert.equal(newRunBlockReason(execution, machine), null);
  assert.ok(newRunBlockReason({ ...execution, retained_owner_id: "owner" }, machine));
  assert.ok(newRunBlockReason(execution, { ...machine, active_maintenance: {} }));
  assert.ok(newRunBlockReason(execution, { ...machine, active_execution: {} }));
  assert.ok(newRunBlockReason(execution, { ...machine, state: "FLUSH_REQUIRED" }));
  assert.ok(newRunBlockReason({ ...execution, busy: true }, machine));
  assert.equal(newRunBlockReason({ ...execution, error: "transport unknown" }, machine), "transport unknown");
});

test("invalid booleans and resume permission cannot be treated as readiness", async () => {
  for (const changed of [{ busy: "false" }, { automatic_resume_allowed: true }, { retained_owner_id: false }]) {
    reply({ ...execution, ...changed });
    await assert.rejects(readExecution(), /invalid/);
  }
});

test("only machine-not-found means uninitialized; server failures remain errors", async () => {
  reply({ detail: "Machine not found" }, 404);
  assert.equal(await readMachine(), null);
  reply({ detail: "database unavailable" }, 503);
  await assert.rejects(readMachine(), /database unavailable/);
});

test("foreign run response cannot replace current run state", async () => {
  reply({ run_id: "other", status: "RUNNING", phase: "REACTION_HOLD", configuration: {}, execution_settings: {} });
  await assert.rejects(readRun("expected"), /another run/);
});

test("start is sent once and must acknowledge this run and the executor", async () => {
  const calls = [];
  globalThis.fetch = async (path, options) => {
    calls.push([path, options]);
    return new Response(JSON.stringify({ run_id: "expected", operation_id: "operation", action: "RUN" }), { status: 202 });
  };
  await runCommand("expected", "start");
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "/api/v1/runs/expected/start");
  assert.equal(calls[0][1].method, "POST");
  assert.ok(JSON.parse(calls[0][1].body).occurred_at);
  reply({ run: { run_id: "expected" }, machine });
  await assert.rejects(runCommand("expected", "start"), /execution acceptance/);
});

test("failed command is never automatically retried", async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; throw new Error("connection lost after send"); };
  await assert.rejects(runCommand("expected", "start"), /connection lost/);
  assert.equal(calls, 1);
});

test("decimal strings and explicit SF duration are preserved", async () => {
  let sent;
  globalThis.fetch = async (_, options) => {
    sent = JSON.parse(options.body);
    return new Response(JSON.stringify({ run_id: "expected", status: "CREATED" }));
  };
  await createRun("expected", { total_mixture_volume_ml: "10.000000000000000001" }, { sf_mixing_duration_seconds: "2.5" });
  assert.equal(sent.configuration.total_mixture_volume_ml, "10.000000000000000001");
  assert.equal(sent.execution_settings.sf_mixing_duration_seconds, "2.5");
});

test("maintenance acknowledgement must match requested action and run", async () => {
  reply({ run_id: "expected", operation_id: "operation", action: "RECOVERY" }, 202);
  await maintenanceCommand("recovery", "expected", {});
  await assert.rejects(maintenanceCommand("flush", "expected", {}), /maintenance acceptance/);
});

test("machine-only maintenance preserves null run scope and supports operation Stop", async () => {
  const accepted = { run_id: null, operation_id: "maintenance", action: "FLUSH" };
  reply(accepted, 202);
  assert.deepEqual(await maintenanceCommand("flush", null, {}), accepted);
  assert.deepEqual(await stopOperation("maintenance"), accepted);
  await assert.rejects(stopOperation("foreign"), /confirm Stop/);
  reply({ run: { run_id: "expected" } });
  await assert.rejects(stopOperation("maintenance"), /confirm Stop/);
  await assert.rejects(stopOperation("run-operation", "foreign"), /confirm Stop/);
  await stopOperation("run-operation", "expected");
  reply({ ...execution, operation: accepted });
  assert.equal((await readExecution()).operation.run_id, null);
});

test("initialization accepts only backend-confirmed idle READY", async () => {
  reply(machine);
  assert.deepEqual(await initializeMachine(), machine);
  reply({ ...machine, state: "STARTING" });
  await assert.rejects(initializeMachine(), /initial readiness/);
});

test("backend events are used directly and malformed history is rejected", async () => {
  const event = { sequence_number: 1, occurred_at: "2026-10-03T10:00:00Z", message: "Run created", event_type: "RUN_CREATED" };
  reply([event]);
  assert.deepEqual(await readEvents("expected"), [event]);
  reply([{ ...event, message: null }]);
  await assert.rejects(readEvents("expected"), /event history is invalid/);
});

test("current confirmation challenge rejects malformed identity, purpose and time", async () => {
  const current = { request_id: "current-request", purpose: "RECOVERY", operator: "fixture operator",
    controller_boot_id: 58, connection_epoch: 1, remaining_seconds: 20 };
  reply({ ...execution, current_input: current });
  assert.equal((await readExecution()).current_input.request_id, "current-request");
  for (const changed of [{ request_id: "" }, { operator: "" }, { purpose: "FLUSH" },
    { remaining_seconds: -1 }, { remaining_seconds: "20" }, { controller_boot_id: 0 }, { connection_epoch: 0 }]) {
    reply({ ...execution, current_input: { ...current, ...changed } });
    await assert.rejects(readExecution(), /challenge is invalid/);
  }
});

test("operator credential is scoped to a single explicit declaration header", async () => {
  const credential = "fake-only-credential";
  const references = { evidence_note: "fresh fixture statement", observed_now_confirmed: true };
  const calls = [];
  globalThis.fetch = async (path, options) => {
    calls.push([path, options]);
    return new Response(JSON.stringify(path.endsWith("/cancel")
      ? { request_id: "current-request", cancelled: true }
      : { request_id: "current-request", declaration_received: true }));
  };
  await submitCurrentInput("current-request", references, credential);
  assert.equal(calls[0][1].headers.Authorization, `Bearer ${credential}`);
  assert.equal(calls[0][0], "/api/v1/execution/current-input/current-request");
  assert.equal(JSON.parse(calls[0][1].body).operator, undefined);
  assert.equal(JSON.parse(calls[0][1].body).observed_at_monotonic, undefined);
  assert.ok(!calls[0][1].body.includes(credential));
  await cancelCurrentInput("current-request", credential);
  assert.equal(calls[1][0], "/api/v1/execution/current-input/current-request/cancel");
  reply({ request_id: "other", declaration_received: true });
  await assert.rejects(submitCurrentInput("current-request", references, credential), /this current declaration/);
});

test("failed operator declaration never retries or sends another action", async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; throw new Error("declaration connection lost"); };
  await assert.rejects(submitCurrentInput("current-request", {}, "fake-only-credential"), /connection lost/);
  assert.equal(calls, 1);
});
