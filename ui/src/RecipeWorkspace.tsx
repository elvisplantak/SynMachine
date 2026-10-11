import { useCallback, useEffect, useState } from "react";
import { OwnedDemoControls } from "./OwnedDemoControls";
import { executeRecipe, listRecipes, previewRecipe, saveRecipe, stepLabel } from "./recipeApi";
import type { RecipeDefinition, RecipePreview, RecipeStep, SavedRecipe } from "./recipeApi";
import "./RecipeWorkspace.css";

const empty = (): RecipeDefinition => ({ schema_version: 1, name: "", description: "", sources: { B1: "B1", B2: "B2", S: "S" }, steps: [] });
const kinds = { ADD: "Dodavanje u reaktor", WAIT: "Čekanje / reakcija", TRANSFER: "Prijenos tekućine", SF_MIX: "Miješanje u SF-u", SF_SETTLE: "Taloženje u SF-u", COLLECT: "Skupljanje frakcija" };
function newStep(kind: RecipeStep["kind"]): RecipeStep {
  if (kind === "ADD") return { kind, source: "B1", volume_ml: "" };
  if (kind === "TRANSFER") return { kind, route: "REACTOR_TO_SF", volume_ml: "" };
  if (kind === "COLLECT") return { kind, fraction_count: 1, fraction_duration_seconds: "" };
  return { kind, duration_seconds: "" };
}
const preparation = {
  sources_match_recipe: "Sadržaj boca B1, B2 i S odgovara receptu.",
  reactor_sf_column_empty_clean: "Reaktor, SF i kolona prazni su i pripremljeni za ovu proceduru.",
  waste_capacity_available: "Otpad ima dovoljno slobodnog kapaciteta.",
  collection_tubes_ready: "Posude za frakcije su pripremljene i karusel je poravnat na posudu 1.",
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
  const [blockReason, setBlockReason] = useState<string | null>("Čitam stanje backenda…");
  const [operator, setOperator] = useState("");
  const [evidence, setEvidence] = useState("");
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  const [kind, setKind] = useState<RecipeStep["kind"]>("ADD");
  const dirty = saved === null || JSON.stringify(draft) !== JSON.stringify(saved.definition);
  const clearAttempt = () => { setReview(null); setChecks({}); setEvidence(""); };
  const update = (value: RecipeDefinition) => { setDraft(value); clearAttempt(); setMessage(""); };
  const loadLibrary = async () => {
    try { setLibrary(await listRecipes()); setLibraryError(""); }
    catch (error) { setLibraryError(error instanceof Error ? error.message : "Biblioteka nije dostupna."); }
  };
  useEffect(() => { void loadLibrary(); }, []);
  const operation = async (callback: () => Promise<void>) => {
    setPending(true); setMessage("");
    try { await callback(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Zahtjev nije uspio."); }
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
    <header className="uvpHeader"><div><span className="panelEyebrow">LabForge · UVP</span><h1>Unos vlastite procedure</h1><p>Sastavi korake, spremi recept i pregledaj ga prije zasebnog pokretanja.</p></div>
      <button type="button" onClick={onExit}>Natrag na početnu</button></header>
    <p>UVP koristi postojeće radnje demo sustava. Svaki run počinje s praznim, pripremljenim reaktorom, SF-om i kolonom. Čekanje je pasivno; SF miješanje koristi fiksni profil.</p>
    <div className="uvpLayout"><aside className="demoPanel uvpLibrary" aria-label="Spremljeni recepti"><h2>Moji recepti</h2>
      <button type="button" disabled={pending} onClick={() => { setSaved(null); update(empty()); }}>Novi recept</button>
      <button type="button" disabled={pending} onClick={() => void loadLibrary()}>Osvježi biblioteku</button>
      {libraryError && <p role="alert">{libraryError}</p>}
      {!libraryError && library.length === 0 && <p>Još nema spremljenih recepata.</p>}
      <ul>{library.map((recipe) => <li key={recipe.recipe_id}><button type="button" disabled={pending} aria-pressed={saved?.recipe_id === recipe.recipe_id}
        onClick={() => { setSaved(recipe); update(recipe.definition); }}>{recipe.definition.name}<small>Verzija {recipe.revision} · {recipe.definition.steps.length} koraka</small></button></li>)}</ul>
      <p>Svako spremanje stvara novu verziju. Pokrenuta procedura čuva vlastitu kopiju.</p>
    </aside><section className="demoPanel uvpEditor" aria-label="Uređivanje procedure"><h2>Recept</h2>
      <fieldset disabled={pending}>
        <label>Naziv recepta<input maxLength={120} value={draft.name} onChange={(e) => update({ ...draft, name: e.target.value })} placeholder="Npr. priprema i razdvajanje demo smjese" /></label>
        <label>Bilješka<textarea maxLength={2000} value={draft.description} onChange={(e) => update({ ...draft, description: e.target.value })} /></label>
        <div className="uvpSources">{(["B1", "B2", "S"] as const).map((source) => <label key={source}>Sadržaj boce {source}<input maxLength={120} value={draft.sources[source]} onChange={(e) => update({ ...draft, sources: { ...draft.sources, [source]: e.target.value } })} /></label>)}</div>
        <p>Ovi nazivi opisuju boce na postojećim priključcima. Provjeri sadržaj prije pokretanja.</p>
        <ol className="uvpSteps">{draft.steps.map((step, index) => <li key={index} className="uvpStep">
          <div className="uvpStepHeading"><h3>{index + 1}. {kinds[step.kind]}</h3><div>
            <button type="button" aria-label={`Pomakni korak ${index + 1} gore`} disabled={index === 0} onClick={() => move(index, -1)}>↑</button>
            <button type="button" aria-label={`Pomakni korak ${index + 1} dolje`} disabled={index === draft.steps.length - 1} onClick={() => move(index, 1)}>↓</button>
            <button type="button" disabled={draft.steps.length >= 100} onClick={() => update({ ...draft, steps: [...draft.steps.slice(0, index + 1), { ...step }, ...draft.steps.slice(index + 1)] })}>Dupliciraj</button>
            <button type="button" onClick={() => update({ ...draft, steps: draft.steps.filter((_, i) => i !== index) })}>Ukloni</button></div></div>
          <div className="uvpStepFields">
            {step.kind === "ADD" && <label>Iz boce<select value={step.source} onChange={(e) => changeStep(index, { ...step, source: e.target.value as "B1" | "B2" | "S" })}>{(["B1", "B2", "S"] as const).map((s) => <option key={s} value={s}>{s} · {draft.sources[s]}</option>)}</select></label>}
            {step.kind === "TRANSFER" && <label>Prijenos<select value={step.route} onChange={(e) => changeStep(index, { ...step, route: e.target.value as "REACTOR_TO_SF" | "SF_TO_COLUMN" })}><option value="REACTOR_TO_SF">Reaktor → SF</option><option value="SF_TO_COLUMN">SF → kolona</option></select></label>}
            {"volume_ml" in step && <label>Volumen (mL)<input type="number" min="0" step="any" value={step.volume_ml} onChange={(e) => changeStep(index, { ...step, volume_ml: e.target.value })} /></label>}
            {"duration_seconds" in step && <label>Trajanje (s)<input type="number" min="0" step="any" value={step.duration_seconds} onChange={(e) => changeStep(index, { ...step, duration_seconds: e.target.value })} /></label>}
            {step.kind === "COLLECT" && <><label>Broj frakcija<input type="number" min="1" max="40" step="1" value={step.fraction_count} onChange={(e) => changeStep(index, { ...step, fraction_count: Number(e.target.value) })} /></label><label>Vrijeme po frakciji (s)<input type="number" min="0" step="any" value={step.fraction_duration_seconds} onChange={(e) => changeStep(index, { ...step, fraction_duration_seconds: e.target.value })} /></label></>}
          </div>
          {step.kind === "WAIT" && <p>Čekanje bez upravljanja grijanjem ili reaktorskom miješalicom. Može se pauzirati.</p>}
          {step.kind === "SF_MIX" && <p>Koristi postojeći fiksni profil miješanja; nema unosa brzine.</p>}
          {step.kind === "COLLECT" && <p>Skupljanje je vremensko, bez mjerenja volumena. To mora biti posljednji korak.</p>}
        </li>)}</ol>
        {draft.steps.length === 0 && <p>Dodaj prvu radnju u proceduru.</p>}
        <div className="uvpActions"><label>Nova radnja<select value={kind} onChange={(e) => setKind(e.target.value as RecipeStep["kind"])}>{Object.entries(kinds).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          <button type="button" disabled={draft.steps.length >= 100} onClick={() => update({ ...draft, steps: [...draft.steps, newStep(kind)] })}>Dodaj korak</button></div>
        <div className="uvpActions"><button type="button" disabled={!draft.name.trim() || draft.steps.length === 0 || !dirty} onClick={() => void operation(async () => {
          const result = await saveRecipe(draft, saved); setSaved(result); setDraft(result.definition); clearAttempt(); await loadLibrary(); setMessage(`Spremljena verzija ${result.revision}. Stroj nije pokrenut.`);
        })}>Spremi recept</button>
          {saved && <button type="button" onClick={() => { setSaved(null); update({ ...draft, name: `${draft.name} — kopija`.slice(0, 120) }); }}>Napravi kopiju recepta</button>}
          <button type="button" disabled={dirty} onClick={() => void operation(async () => { setReview(null); setChecks({}); setEvidence(""); setReview(await previewRecipe(saved!)); setMessage("Pregled potvrđen. Izvršavanje traži zaseban klik i svježe potvrde."); })}>Provjeri proceduru</button></div>
      </fieldset>
      <p aria-live="polite">{message}</p>
      {saved && <p>{dirty ? "Postoje nespremljene promjene." : `Spremljena verzija ${saved.revision}.`}</p>}
    </section></div>
    {review && saved && !dirty && <section className="demoPanel uvpReview" aria-label="Pregled procedure"><h2>Pregled: {saved.definition.name} · verzija {saved.revision}</h2>
      <ol>{review.steps.map((item) => <li key={item.step_number}>{stepLabel(item.step, saved.definition.sources)}</li>)}</ol>
      <p>Volumeni su zadani, bez senzorskog mjerenja. Nakon vremenskog skupljanja ostatak u koloni nije poznat.</p>
      {!review.calibrations_checked && <p>Izvršni profil nije spojen; pregled zasad provjerava samo redoslijed i količine.</p>}
      {review.collection_readiness_status === "FRESH_INPUT_REQUIRED" && <p>Prije prve radnje zatražit će se svježe reference kolone i karusela. Bez poznatih referenci procedura neće početi.</p>}
      {review.collection_readiness_status === "UNAVAILABLE" && <p>Skupljanje frakcija nije dostupno: izvršni sustav nema potvrđene reference kolone i karusela niti unos svježih referenci.</p>}
      <fieldset disabled={pending || locked}>
        <legend>Priprema za ovaj pokušaj</legend><label>Operater<input value={operator} onChange={(e) => setOperator(e.target.value)} /></label><label>Bilješka o sadašnjoj pripremi<textarea value={evidence} onChange={(e) => setEvidence(e.target.value)} /></label>
        {Object.entries(preparation).map(([key, label]) => <label key={key} className="uvpCheck"><input type="checkbox" checked={checks[key] ?? false} onChange={(e) => setChecks({ ...checks, [key]: e.target.checked })} />{label}</label>)}
        <button type="button" disabled={!ready || blockReason !== null || !review.calibrations_checked || review.collection_readiness_status === "UNAVAILABLE"} onClick={() => void operation(async () => {
          const statement = { operator, evidence_note: evidence, sources_match_recipe: true as const, reactor_sf_column_empty_clean: true as const, waste_capacity_available: true as const, collection_tubes_ready: true as const };
          setChecks({}); setEvidence(""); setReview(null);
          const accepted = await executeRecipe(saved, crypto.randomUUID(), statement);
          setMessage(`Procedura je prihvaćena. Prati stanje izvršavanja ispod. Run: ${accepted.run_id}`);
        })}>Pokreni pregledanu proceduru</button>
      </fieldset>{blockReason && <p>{blockReason}</p>}
    </section>}
    <OwnedDemoControls configurationValid={false} onLock={setLocked} showLog={false} hideDemoSettings={true} onBlockReason={onState} />
  </main>;
}
