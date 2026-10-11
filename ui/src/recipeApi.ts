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
      const prefix = index >= 0 && typeof loc[index + 1] === "number" ? `Korak ${Number(loc[index + 1]) + 1}: ` : "";
      const field = String(loc.at(-1));
      const labels: Record<string, string> = { name: "naziv recepta", volume_ml: "pozitivan volumen u mL", duration_seconds: "pozitivno trajanje u sekundama", fraction_duration_seconds: "pozitivno vrijeme po frakciji", fraction_count: "broj frakcija od 1 do 40", steps: "barem jedan korak procedure" };
      return `${prefix}Provjeri ${labels[field] ?? "unesene parametre"}.`;
    }).join(" ");
  }
  if (typeof detail !== "string") return "Zahtjev za recept nije uspio.";
  if (detail.includes("content identity")) return "Sadržaj recepta ne odgovara pregledanoj verziji. Osvježi biblioteku i ponovno provjeri recept.";
  if (detail.includes("revision changed")) return "Recept je promijenjen. Osvježi biblioteku, otvori recept i ponovno provjeri proceduru.";
  if (detail.includes("whole steps")) return "Odabrani volumen nije izvediv u sadašnjem profilu pumpe. Odaberi drugi volumen.";
  if (detail.includes("HOME is not a transfer")) return "Odabrani volumen zahtijeva HOME u sadašnjem profilu. Odaberi drugi volumen za prijenos.";
  if (detail.includes("not configured")) return "Izvršni sustav nije konfiguriran. Recept možeš spremiti i provjeriti bez pokretanja.";
  const step = detail.match(/^Step (\d+): (.*)$/);
  if (step) {
    const message = step[2].includes("exceeds") ? "Traži se više tekućine nego što je prethodnim koracima zadano u izvornoj posudi."
      : step[2].includes("final step") ? "Vremensko skupljanje frakcija mora biti posljednji korak."
      : "Prethodnim koracima prvo treba dodati tekućinu u ovu posudu.";
    return `Korak ${step[1]}: ${message}`;
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
  if (!Array.isArray(result) || !result.every(isRecipe)) throw new Error("Neispravan odgovor biblioteke recepata.");
  return result;
}
export async function saveRecipe(definition: RecipeDefinition, previous: SavedRecipe | null): Promise<SavedRecipe> {
  const result = await request(previous ? `/${encodeURIComponent(previous.recipe_id)}` : "", {
    definition, expected_revision: previous?.revision ?? 0,
  });
  if (!isRecipe(result) || (previous && (result.recipe_id !== previous.recipe_id || result.revision !== previous.revision + 1))) {
    throw new Error("Backend nije potvrdio spremanje ove verzije recepta.");
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
    throw new Error("Backend nije potvrdio pregled ove procedure.");
  }
  return result;
}
export async function executeRecipe(recipe: SavedRecipe, runId: string, readiness: RecipeReadiness) {
  const result = await request(`/${encodeURIComponent(recipe.recipe_id)}/execute`, {
    run_id: runId, expected_revision: recipe.revision, expected_content_digest: recipe.content_digest, readiness, occurred_at: new Date().toISOString(),
  }) as { action?: string; operation_id?: string; run_id?: string };
  if (result?.action !== "RUN" || result.run_id !== runId || typeof result.operation_id !== "string" || !result.operation_id) {
    throw new Error("Backend nije potvrdio izvršavanje ove procedure.");
  }
  return result;
}
export function stepLabel(step: RecipeStep, sources?: RecipeDefinition["sources"]): string {
  if (step.kind === "ADD") return `Dodaj ${step.volume_ml} mL iz ${step.source}${sources?.[step.source] && sources[step.source] !== step.source ? ` (${sources[step.source]})` : ""} u reaktor`;
  if (step.kind === "TRANSFER") return `Prenesi ${step.volume_ml} mL: ${step.route === "REACTOR_TO_SF" ? "reaktor → SF" : "SF → kolona"}`;
  if (step.kind === "COLLECT") return `Skupi ${step.fraction_count} frakcija, ${step.fraction_duration_seconds} s po frakciji`;
  return `${{ WAIT: "Čekaj", SF_MIX: "Miješaj u SF-u", SF_SETTLE: "Taloži u SF-u" }[step.kind]} ${step.duration_seconds} s`;
}
