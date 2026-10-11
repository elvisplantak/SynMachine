export type RecipeStep =
  | { kind: "ADD"; source: "B1" | "B2" | "S"; volume_ml: string }
  | { kind: "TRANSFER"; route: "REACTOR_TO_SF" | "SF_TO_COLUMN"; volume_ml: string }
  | { kind: "WAIT" | "SF_MIX" | "SF_SETTLE"; duration_seconds: string }
  | { kind: "COLLECT"; fraction_count: number; fraction_duration_seconds: string };
export type RecipeDefinition = {
  schema_version: 1; name: string; description: string;
  sources: { B1: string; B2: string; S: string }; steps: RecipeStep[];
};
export type SavedRecipe = { recipe_id: string; revision: number; content_digest: string; definition: RecipeDefinition };
export type RecipePreview = {
  steps: { step_number: number; phase: string; step: RecipeStep; operation_count?: number }[];
  configured_contents_ml: Record<string, string>; calibrations_checked: boolean;
  content_digest: string;
  collection_readiness_status: "NOT_REQUIRED" | "STATIC_CONFIRMED" | "FRESH_INPUT_REQUIRED" | "UNAVAILABLE";
  collection_readiness_required: boolean; volumes_are_measured: false;
};
export type RecipeReadiness = {
  operator: string; evidence_note: string; sources_match_recipe: true;
  reactor_sf_column_empty_clean: true; waste_capacity_available: true; collection_tubes_ready: true;
};

export function isRecipe(value: unknown): value is SavedRecipe {
  if (typeof value !== "object" || value === null) return false;
  const recipe = value as SavedRecipe;
  const d = recipe.definition;
  return typeof recipe.recipe_id === "string" && recipe.recipe_id.length > 0
    && typeof recipe.content_digest === "string" && /^[0-9a-f]{64}$/.test(recipe.content_digest)
    && Number.isInteger(recipe.revision) && recipe.revision > 0 && !!d && d.schema_version === 1
    && typeof d.name === "string" && typeof d.description === "string"
    && !!d.sources && [d.sources.B1, d.sources.B2, d.sources.S].every((s) => typeof s === "string")
    && Array.isArray(d.steps) && d.steps.length > 0 && d.steps.every(isStep);
}
function isStep(value: unknown): value is RecipeStep {
  if (typeof value !== "object" || value === null) return false;
  const s = value as RecipeStep;
  const amount = (v: unknown) => typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v)) && Number(v) > 0;
  if (s.kind === "ADD") return ["B1", "B2", "S"].includes(s.source) && amount(s.volume_ml);
  if (s.kind === "TRANSFER") return ["REACTOR_TO_SF", "SF_TO_COLUMN"].includes(s.route) && amount(s.volume_ml);
  if (s.kind === "COLLECT") return Number.isInteger(s.fraction_count) && s.fraction_count >= 1 && s.fraction_count <= 40 && amount(s.fraction_duration_seconds);
  return ["WAIT", "SF_MIX", "SF_SETTLE"].includes(s.kind) && "duration_seconds" in s && amount(s.duration_seconds);
}
function humanError(detail: unknown): string {
  if (Array.isArray(detail)) {
    return detail.map((issue: { loc?: (string | number)[] }) => {
      const loc = issue.loc ?? [];
      const index = loc.indexOf("steps");
      const prefix = index >= 0 && typeof loc[index + 1] === "number" ? `Step ${Number(loc[index + 1]) + 1}: ` : "";
      const field = String(loc.at(-1));
      const labels: Record<string, string> = { name: "recipe name", volume_ml: "a positive volume in mL", duration_seconds: "a positive duration in seconds", fraction_duration_seconds: "a positive time per fraction", fraction_count: "a fraction count from 1 to 40", steps: "at least one procedure step" };
      return `${prefix}Check ${labels[field] ?? "the entered parameters"}.`;
    }).join(" ");
  }
  if (typeof detail !== "string") return "The recipe request failed.";
  if (detail.includes("content identity")) return "Recipe content does not match the reviewed version. Refresh the library and review the recipe again.";
  if (detail.includes("revision changed")) return "The recipe has changed. Refresh the library, open the recipe and review it again.";
  if (detail.includes("whole steps")) return "This volume cannot be delivered with the current pump profile. Choose another volume.";
  if (detail.includes("HOME is not a transfer")) return "This volume requires HOME with the current pump profile. Choose another transfer volume.";
  if (detail.includes("not configured")) return "The execution system is not configured. You can save and review a recipe without starting it.";
  const step = detail.match(/^Step (\d+): (.*)$/);
  if (step) {
    const message = step[2].includes("exceeds") ? "This transfer requests more liquid than previous steps placed in the source vessel."
      : step[2].includes("final step") ? "Timed fraction collection must be the last step."
      : "Earlier steps must first add liquid to this vessel.";
    return `Step ${step[1]}: ${message}`;
  }
  return detail;
}
async function request(path: string, body?: unknown): Promise<unknown> {
  const abort = new AbortController();
  const timeout = setTimeout(() => abort.abort(), 15000);
  try {
    const response = await fetch(`/api/v1/recipes${path}`, { method: body === undefined ? "GET" : "POST",
      headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body), signal: abort.signal });
    const result = await response.json();
    if (!response.ok) {
      const detail = result?.detail;
      throw new Error(humanError(detail));
    }
    return result;
  } finally { clearTimeout(timeout); }
}
export async function listRecipes(): Promise<SavedRecipe[]> {
  const result = await request("");
  if (!Array.isArray(result) || !result.every(isRecipe)) throw new Error("Invalid recipe library response.");
  return result;
}
export async function saveRecipe(definition: RecipeDefinition, previous: SavedRecipe | null): Promise<SavedRecipe> {
  const result = await request(previous ? `/${encodeURIComponent(previous.recipe_id)}` : "", {
    definition, expected_revision: previous?.revision ?? 0,
  });
  if (!isRecipe(result) || (previous && (result.recipe_id !== previous.recipe_id || result.revision !== previous.revision + 1))) {
    throw new Error("The backend did not confirm saving this recipe version.");
  }
  return result;
}
export async function previewRecipe(recipe: SavedRecipe): Promise<RecipePreview> {
  const definition = recipe.definition;
  const result = await request("/preview", definition) as RecipePreview;
  if (!result || !Array.isArray(result.steps) || result.steps.length !== definition.steps.length
    || result.steps.some((step, i) => step.step_number !== i + 1 || !isStep(step.step)
      || Object.entries(definition.steps[i]).some(([key, value]) => (step.step as unknown as Record<string, unknown>)[key] !== value))
    || result.content_digest !== recipe.content_digest
    || typeof result.collection_readiness_required !== "boolean"
    || result.collection_readiness_required !== definition.steps.some((step) => step.kind === "COLLECT")
    || !(result.collection_readiness_required ? ["STATIC_CONFIRMED", "FRESH_INPUT_REQUIRED", "UNAVAILABLE"] : ["NOT_REQUIRED"]).includes(result.collection_readiness_status)
    || typeof result.calibrations_checked !== "boolean" || result.volumes_are_measured !== false) {
    throw new Error("The backend did not confirm the procedure review.");
  }
  return result;
}
export async function executeRecipe(recipe: SavedRecipe, runId: string, readiness: RecipeReadiness) {
  const result = await request(`/${encodeURIComponent(recipe.recipe_id)}/execute`, {
    run_id: runId, expected_revision: recipe.revision, expected_content_digest: recipe.content_digest, readiness, occurred_at: new Date().toISOString(),
  }) as { action?: string; operation_id?: string; run_id?: string };
  if (result?.action !== "RUN" || result.run_id !== runId || typeof result.operation_id !== "string" || !result.operation_id) {
    throw new Error("The backend did not confirm executing this procedure.");
  }
  return result;
}
export function stepLabel(step: RecipeStep, sources?: RecipeDefinition["sources"]): string {
  if (step.kind === "ADD") return `Add ${step.volume_ml} mL from ${step.source}${sources?.[step.source] && sources[step.source] !== step.source ? ` (${sources[step.source]})` : ""} to reactor`;
  if (step.kind === "TRANSFER") return `Transfer ${step.volume_ml} mL: ${step.route === "REACTOR_TO_SF" ? "reactor → SF" : "SF → column"}`;
  if (step.kind === "COLLECT") return `Collect ${step.fraction_count} fractions, ${step.fraction_duration_seconds} s per fraction`;
  return `${{ WAIT: "Wait", SF_MIX: "Mix in SF for", SF_SETTLE: "Settle in SF for" }[step.kind]} ${step.duration_seconds} s`;
}
