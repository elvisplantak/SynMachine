import { useState } from "react";
import { exportXdl, importXdl, inspectXdl } from "./recipeApi";
import type { RecipeDefinition, XdlInspection } from "./recipeApi";

type Props = {
  definition: RecipeDefinition; fake: boolean; pending: boolean;
  run: (action: () => Promise<void>) => Promise<void>;
  onBegin: () => void; onImport: (definition: RecipeDefinition) => void;
};
const selected = (values: Record<string, string>) => Object.fromEntries(Object.entries(values).filter(([, v]) => v));

export function XdlExchange({ definition, fake, pending, run, onBegin, onImport }: Props) {
  const [xml, setXml] = useState("");
  const [document, setDocument] = useState<XdlInspection | null>(null);
  const [name, setName] = useState("");
  const [reagents, setReagents] = useState<Record<string, string>>({});
  const [vessels, setVessels] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");

  return <details className="uvpXdl"><summary>XDL 2 import / export</summary>
    <p>Supports liquid Add, Transfer and passive Wait. Import creates a new unsaved draft; save and review it before starting.</p>
    {!fake && <p>Connect a fake execution profile to use XDL interchange.</p>}
    <fieldset disabled={pending || !fake}>
      <label>XDL file<input type="file" accept=".xdl,.xml" onChange={(event) => {
        const file = event.target.files?.[0]; event.target.value = "";
        if (!file) return;
        onBegin(); setDocument(null); setXml(""); setMessage(""); setReagents({}); setVessels({});
        void run(async () => {
          if (file.size > 131072) throw new Error("Choose an XDL file no larger than 128 KiB.");
          let source: string;
          try { source = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer()); }
          catch { throw new Error("XDL files must contain valid UTF-8 XML."); }
          const inspected = await inspectXdl(source);
          setXml(source); setDocument(inspected); setName(inspected.suggested_name);
        });
      }} /></label>
      {document && <>
        <p>{document.step_count} supported XDL steps found. Assign reagent bottles and vessel roles explicitly. Import replaces the current draft.</p>
        <label>Imported recipe name<input value={name} maxLength={120} onChange={(event) => setName(event.target.value)} /></label>
        <div className="uvpSources">{["B1", "B2", "S"].map((bottle) => <label key={bottle}>XDL reagent for {bottle}
          <select value={reagents[bottle] ?? ""} onChange={(event) => setReagents({ ...reagents, [bottle]: event.target.value })}>
            <option value="">Not assigned</option>{document.reagents.map((reagent) => <option key={reagent} value={reagent}>{reagent}</option>)}
          </select></label>)}</div>
        <div className="uvpSources">{["REACTOR", "SF", "COLUMN"].map((role) => <label key={role}>XDL vessel for {role}
          <select value={vessels[role] ?? ""} onChange={(event) => setVessels({ ...vessels, [role]: event.target.value })}>
            <option value="">Not assigned</option>{document.vessels.map((vessel) => <option key={vessel.id} value={vessel.id}>{vessel.id} ({vessel.type})</option>)}
          </select></label>)}</div>
        <button type="button" disabled={!name.trim()} onClick={() => void run(async () => {
          onBegin();
          const imported = await importXdl(xml, name, selected(reagents), selected(vessels));
          onImport(imported); setDocument(null); setXml("");
          setMessage(`Imported ${imported.steps.length} steps as a new draft. Save and review before starting.`);
        })}>Import as new draft</button>
      </>}
      <button type="button" disabled={!definition.name.trim() || !definition.steps.length} onClick={() => void run(async () => {
        setMessage("");
        const output = await exportXdl(definition);
        const url = URL.createObjectURL(new Blob([output], { type: "application/xml" }));
        const link = window.document.createElement("a");
        link.href = url; link.download = "synmachine-recipe.xdl"; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 0);
        setMessage("XDL file exported.");
      })}>Export draft as XDL</button>
    </fieldset><p aria-live="polite">{message}</p>
  </details>;
}
