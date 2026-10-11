import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { executeRecipe, isRecipe, listRecipes, previewRecipe, saveRecipe } from "../src/recipeApi.ts";
import { readRun } from "../src/guidedDemoApi.ts";
const original = globalThis.fetch;
afterEach(() => { globalThis.fetch = original; });
const definition = { schema_version: 1, name: "Example", description: "", sources: { B1: "Blue", B2: "B2", S: "Water" }, steps: [{ kind: "ADD", source: "B1", volume_ml: "1.000" }] };
const saved = { recipe_id: "saved", revision: 1, content_digest: "a".repeat(64), definition };
const reply = (body, status = 200) => { globalThis.fetch = async () => new Response(JSON.stringify(body), { status }); };

test("recipe library rejects unknown schema and unsupported operations", async () => {
  assert.equal(isRecipe(saved), true);
  for (const changed of [{ ...saved, content_digest: undefined }, { ...saved, content_digest: "invalid" }, { ...saved, revision: "1" }, { ...saved, definition: { ...definition, schema_version: 2 } }, { ...saved, definition: { ...definition, steps: [{ kind: "HEAT", temperature: 30 }] } }]) {
    reply([changed]); await assert.rejects(listRecipes(), /Neispravan/);
  }
});
test("saving preserves logical parameters and expected revision without executing", async () => {
  const calls = [];
  globalThis.fetch = async (path, options) => {
    calls.push([path, JSON.parse(options.body)]);
    return new Response(JSON.stringify({ ...saved, revision: 2 }));
  };
  const result = await saveRecipe(definition, saved);
  assert.equal(result.revision, 2);
  assert.deepEqual(calls, [["/api/v1/recipes/saved", { definition, expected_revision: 1 }]]);
  assert.equal(calls[0][1].definition.steps[0].volume_ml, "1.000");
});
test("a stale save is surfaced without retry or automatic execution", async () => {
  let count = 0;
  globalThis.fetch = async () => { count++; return new Response(JSON.stringify({ detail: "recipe revision changed" }), { status: 409 }); };
  await assert.rejects(saveRecipe(definition, saved), /Recept je promijenjen/);
  assert.equal(count, 1);
});
test("execution acknowledgement belongs to the exact run", async () => {
  reply({ operation_id: "operation", run_id: "run", action: "RUN" }, 202);
  await executeRecipe(saved, "run", {});
  await assert.rejects(executeRecipe(saved, "foreign", {}), /nije potvrdio/);
});
test("preview requires the backend to describe all steps and no measured-volume claim", async () => {
  const preview = { content_digest: saved.content_digest, collection_readiness_status: "NOT_REQUIRED", collection_readiness_required: false, steps: [{ step_number: 1, phase: "P1_TRANSFER_FIRST_LIQUID_TO_REACTOR", step: definition.steps[0] }], calibrations_checked: true, volumes_are_measured: false };
  reply(preview); await previewRecipe(saved);
  reply({ ...preview, volumes_are_measured: true }); await assert.rejects(previewRecipe(saved), /nije potvrdio/);
  reply({ ...preview, steps: [{ ...preview.steps[0], step: { ...definition.steps[0], source: "B2" } }] }); await assert.rejects(previewRecipe(saved), /nije potvrdio/);
  reply({ ...preview, steps: [] }); await assert.rejects(previewRecipe(saved), /nije potvrdio/);
});
test("recipe runs have no invented demo configuration and reject invalid progress", async () => {
  const run = { run_id: "run", status: "RUNNING", phase: "P1_TRANSFER_FIRST_LIQUID_TO_REACTOR", recipe: saved, recipe_step_index: 0, configuration: null, execution_settings: null };
  reply(run); assert.deepEqual(await readRun("run"), run);
  for (const changed of [{ recipe_step_index: 1 }, { recipe_step_index: -1 }, { recipe_step_index: "0" }, { configuration: {} }, { status: "COMPLETED" }]) {
    reply({ ...run, ...changed }); await assert.rejects(readRun("run"), /progress is invalid/);
  }
});


test("execution sends the reviewed revision and content digest together exactly once", async () => {
  const calls = [];
  globalThis.fetch = async (path, options) => {
    calls.push(JSON.parse(options.body));
    return new Response(JSON.stringify({ operation_id: "operation", action: "RUN", run_id: "run" }), { status: 202 });
  };
  await executeRecipe(saved, "run", {});
  assert.equal(calls.length, 1);
  assert.equal(calls[0].expected_revision, saved.revision);
  assert.equal(calls[0].expected_content_digest, saved.content_digest);
});
test("review rejects a different content identity and invalid collection readiness", async () => {
  const preview = { content_digest: saved.content_digest, collection_readiness_status: "NOT_REQUIRED", collection_readiness_required: false, steps: [{ step_number: 1, phase: "P1_TRANSFER_FIRST_LIQUID_TO_REACTOR", step: definition.steps[0] }], calibrations_checked: true, volumes_are_measured: false };
  for (const change of [{ content_digest: "b".repeat(64) }, { content_digest: undefined }, { collection_readiness_status: undefined }, { collection_readiness_status: "FRESH_INPUT_REQUIRED" }, { collection_readiness_required: true }]) {
    reply({ ...preview, ...change }); await assert.rejects(previewRecipe(saved), /nije potvrdio/);
  }
});
