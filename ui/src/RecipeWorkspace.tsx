import { useCallback, useEffect, useState } from "react";
import { OwnedDemoControls } from "./OwnedDemoControls";
import { executeRecipe, listRecipes, previewRecipe, saveRecipe, stepLabel } from "./recipeApi";
import type { RecipeDefinition, RecipePreview, RecipeStep, SavedRecipe } from "./recipeApi";
import "./RecipeWorkspace.css";

const empty = (): RecipeDefinition => ({ schema_version: 1, name: "", description: "", sources: { B1: "B1", B2: "B2", S: "S" }, steps: [] });
const kinds = { ADD: "Add to reactor", WAIT: "Wait / reaction", TRANSFER: "Transfer liquid", SF_MIX: "Mix in SF", SF_SETTLE: "Settle in SF", COLLECT: "Collect fractions" };
function newStep(kind: RecipeStep["kind"]): RecipeStep {
  if (kind === "ADD") return { kind, source: "B1", volume_ml: "" };
  if (kind === "TRANSFER") return { kind, route: "REACTOR_TO_SF", volume_ml: "" };
  if (kind === "COLLECT") return { kind, fraction_count: 1, fraction_duration_seconds: "" };
  return { kind, duration_seconds: "" };
}
const preparation = {
  sources_match_recipe: "The contents of bottles B1, B2 and S match the recipe.",
  reactor_sf_column_empty_clean: "The reactor, SF and column are empty and prepared for this procedure.",
  waste_capacity_available: "The waste container has enough free capacity.",
  collection_tubes_ready: "Fraction tubes are ready and the carousel is aligned with tube 1.",
};
export function RecipeWorkspace({ onExit }: { onExit: () => void }) {
  const [library, setLibrary] = useState<SavedRecipe[]>([]);
  const [draft, setDraft] = useState<RecipeDefinition>(empty);
  const [saved, setSaved] = useState<SavedRecipe | null>(null);
  const [review, setReview] = useState<RecipePreview | null>(null);
  const [message, setMessage] = useState("");
  const [libraryError, setLibraryError] = useState("");
  const [pending, setPending] = useState(false);
  const [locked, setLocked] = useState(false);
  const [blockReason, setBlockReason] = useState<string | null>("Reading backend state…");
  const [operator, setOperator] = useState("");
  const [evidence, setEvidence] = useState("");
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  const [kind, setKind] = useState<RecipeStep["kind"]>("ADD");
  const dirty = saved === null || JSON.stringify(draft) !== JSON.stringify(saved.definition);
  const clearAttempt = () => { setReview(null); setChecks({}); setEvidence(""); };
  const update = (value: RecipeDefinition) => { setDraft(value); clearAttempt(); setMessage(""); };
  const loadLibrary = async () => {
    try { setLibrary(await listRecipes()); setLibraryError(""); }
    catch (error) { setLibraryError(error instanceof Error ? error.message : "The recipe library is unavailable."); }
  };
  useEffect(() => { void loadLibrary(); }, []);
  const operation = async (callback: () => Promise<void>) => {
    setPending(true); setMessage("");
    try { await callback(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "The request failed."); }
    finally { setPending(false); }
  };
  const changeStep = (index: number, step: RecipeStep) => update({ ...draft, steps: draft.steps.map((s, i) => i === index ? step : s) });
  const move = (index: number, offset: number) => {
    const steps = [...draft.steps]; [steps[index], steps[index + offset]] = [steps[index + offset], steps[index]];
    update({ ...draft, steps });
  };
  const onState = useCallback((reason: string | null) => { setBlockReason(reason); }, []);
  const ready = operator.trim() !== "" && evidence.trim() !== "" && Object.keys(preparation).every((key) => checks[key]);
  return <main className="appShell uvpWorkspace">
    <header className="uvpHeader"><div><span className="panelEyebrow">LabForge · Recipes</span><h1>Procedure Builder</h1><p>Build the steps, save your recipe and review it before starting.</p></div>
      <button type="button" onClick={onExit}>Back to home</button></header>
    <p>Use the existing demo operations to build your procedure. Each run starts with an empty, prepared reactor, SF and column. Waiting is passive; SF mixing uses a fixed profile.</p>
    <div className="uvpLayout"><aside className="demoPanel uvpLibrary" aria-label="Saved recipes"><h2>My Recipes</h2>
      <button type="button" disabled={pending} onClick={() => { setSaved(null); update(empty()); }}>New recipe</button>
      <button type="button" disabled={pending} onClick={() => void loadLibrary()}>Refresh library</button>
      {libraryError && <p role="alert">{libraryError}</p>}
      {!libraryError && library.length === 0 && <p>No saved recipes yet.</p>}
      <ul>{library.map((recipe) => <li key={recipe.recipe_id}><button type="button" disabled={pending} aria-pressed={saved?.recipe_id === recipe.recipe_id}
        onClick={() => { setSaved(recipe); update(recipe.definition); }}>{recipe.definition.name}<small>Version {recipe.revision} · {recipe.definition.steps.length} steps</small></button></li>)}</ul>
      <p>Each save creates a new version. Each run keeps its own copy.</p>
    </aside><section className="demoPanel uvpEditor" aria-label="Procedure editor"><h2>Recipe</h2>
      <fieldset disabled={pending}>
        <label>Recipe name<input maxLength={120} value={draft.name} onChange={(e) => update({ ...draft, name: e.target.value })} placeholder="e.g. Prepare and separate a demo mixture" /></label>
        <label>Notes<textarea maxLength={2000} value={draft.description} onChange={(e) => update({ ...draft, description: e.target.value })} /></label>
        <div className="uvpSources">{(["B1", "B2", "S"] as const).map((source) => <label key={source}>Bottle {source} contents<input maxLength={120} value={draft.sources[source]} onChange={(e) => update({ ...draft, sources: { ...draft.sources, [source]: e.target.value } })} /></label>)}</div>
        <p>These names describe bottles on the existing connections. Check their contents before starting.</p>
        <ol className="uvpSteps">{draft.steps.map((step, index) => <li key={index} className="uvpStep">
          <div className="uvpStepHeading"><h3>{index + 1}. {kinds[step.kind]}</h3><div>
            <button type="button" aria-label={`Move step ${index + 1} up`} disabled={index === 0} onClick={() => move(index, -1)}>↑</button>
            <button type="button" aria-label={`Move step ${index + 1} down`} disabled={index === draft.steps.length - 1} onClick={() => move(index, 1)}>↓</button>
            <button type="button" disabled={draft.steps.length >= 100} onClick={() => update({ ...draft, steps: [...draft.steps.slice(0, index + 1), { ...step }, ...draft.steps.slice(index + 1)] })}>Duplicate</button>
            <button type="button" onClick={() => update({ ...draft, steps: draft.steps.filter((_, i) => i !== index) })}>Remove</button></div></div>
          <div className="uvpStepFields">
            {step.kind === "ADD" && <label>From bottle<select value={step.source} onChange={(e) => changeStep(index, { ...step, source: e.target.value as "B1" | "B2" | "S" })}>{(["B1", "B2", "S"] as const).map((s) => <option key={s} value={s}>{s} · {draft.sources[s]}</option>)}</select></label>}
            {step.kind === "TRANSFER" && <label>Transfer<select value={step.route} onChange={(e) => changeStep(index, { ...step, route: e.target.value as "REACTOR_TO_SF" | "SF_TO_COLUMN" })}><option value="REACTOR_TO_SF">Reactor → SF</option><option value="SF_TO_COLUMN">SF → column</option></select></label>}
            {"volume_ml" in step && <label>Volume (mL)<input type="number" min="0" step="any" value={step.volume_ml} onChange={(e) => changeStep(index, { ...step, volume_ml: e.target.value })} /></label>}
            {"duration_seconds" in step && <label>Duration (s)<input type="number" min="0" step="any" value={step.duration_seconds} onChange={(e) => changeStep(index, { ...step, duration_seconds: e.target.value })} /></label>}
            {step.kind === "COLLECT" && <><label>Fraction count<input type="number" min="1" max="40" step="1" value={step.fraction_count} onChange={(e) => changeStep(index, { ...step, fraction_count: Number(e.target.value) })} /></label><label>Time per fraction (s)<input type="number" min="0" step="any" value={step.fraction_duration_seconds} onChange={(e) => changeStep(index, { ...step, fraction_duration_seconds: e.target.value })} /></label></>}
          </div>
          {step.kind === "WAIT" && <p>Wait without controlling heating or the reactor mixer. This step can be paused.</p>}
          {step.kind === "SF_MIX" && <p>Uses the existing fixed mixing profile; speed cannot be adjusted.</p>}
          {step.kind === "COLLECT" && <p>Collection is timed, without volume measurement. This must be the last step.</p>}
        </li>)}</ol>
        {draft.steps.length === 0 && <p>Add the first step to your procedure.</p>}
        <div className="uvpActions"><label>New action<select value={kind} onChange={(e) => setKind(e.target.value as RecipeStep["kind"])}>{Object.entries(kinds).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          <button type="button" disabled={draft.steps.length >= 100} onClick={() => update({ ...draft, steps: [...draft.steps, newStep(kind)] })}>Add step</button></div>
        <div className="uvpActions"><button type="button" disabled={!draft.name.trim() || draft.steps.length === 0 || !dirty} onClick={() => void operation(async () => {
          const result = await saveRecipe(draft, saved); setSaved(result); setDraft(result.definition); clearAttempt(); await loadLibrary(); setMessage(`Version ${result.revision} saved. The machine has not started.`);
        })}>Save recipe</button>
          {saved && <button type="button" onClick={() => { setSaved(null); update({ ...draft, name: `${draft.name} — copy`.slice(0, 120) }); }}>Copy recipe</button>}
          <button type="button" disabled={dirty} onClick={() => void operation(async () => { setReview(null); setChecks({}); setEvidence(""); setReview(await previewRecipe(saved!)); setMessage("Review confirmed. Starting requires a separate click and fresh confirmations."); })}>Review procedure</button></div>
      </fieldset>
      <p aria-live="polite">{message}</p>
      {saved && <p>{dirty ? "There are unsaved changes." : `Saved version ${saved.revision}.`}</p>}
    </section></div>
    {review && saved && !dirty && <section className="demoPanel uvpReview" aria-label="Procedure review"><h2>Review: {saved.definition.name} · version {saved.revision}</h2>
      <ol>{review.steps.map((item) => <li key={item.step_number}>{stepLabel(item.step, saved.definition.sources)}</li>)}</ol>
      <p>Volumes are configured values, without sensor measurement. After timed collection, the amount remaining in the column is unknown.</p>
      {!review.calibrations_checked && <p>No execution profile is connected; this review checks only the sequence and amounts.</p>}
      {review.collection_readiness_status === "FRESH_INPUT_REQUIRED" && <p>Fresh column and carousel references will be requested before the first operation. The procedure cannot begin without known references.</p>}
      {review.collection_readiness_status === "UNAVAILABLE" && <p>Fraction collection is unavailable: the execution system has neither confirmed column and carousel references nor a way to acquire fresh references.</p>}
      <fieldset disabled={pending || locked}>
        <legend>Preparation for this attempt</legend><label>Operator<input value={operator} onChange={(e) => setOperator(e.target.value)} /></label><label>Current preparation notes<textarea value={evidence} onChange={(e) => setEvidence(e.target.value)} /></label>
        {Object.entries(preparation).map(([key, label]) => <label key={key} className="uvpCheck"><input type="checkbox" checked={checks[key] ?? false} onChange={(e) => setChecks({ ...checks, [key]: e.target.checked })} /><span>{label}</span></label>)}
        <button type="button" disabled={!ready || blockReason !== null || !review.calibrations_checked || review.collection_readiness_status === "UNAVAILABLE"} onClick={() => void operation(async () => {
          const statement = { operator, evidence_note: evidence, sources_match_recipe: true as const, reactor_sf_column_empty_clean: true as const, waste_capacity_available: true as const, collection_tubes_ready: true as const };
          setChecks({}); setEvidence(""); setReview(null);
          const accepted = await executeRecipe(saved, crypto.randomUUID(), statement);
          setMessage(`Procedure accepted. Follow execution status below. Run: ${accepted.run_id}`);
        })}>Start reviewed procedure</button>
      </fieldset>{blockReason && <p>{blockReason}</p>}
    </section>}
    <OwnedDemoControls configurationValid={false} onLock={setLocked} showLog={false} hideDemoSettings={true} onBlockReason={onState} />
  </main>;
}
