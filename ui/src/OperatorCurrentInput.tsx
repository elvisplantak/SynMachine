import { useState } from "react";
import { cancelCurrentInput, submitCurrentInput } from "./guidedDemoApi";
import type { OperatorInputChallenge, OperatorReferences } from "./guidedDemoApi";

export function OperatorCurrentInput({ challenge, available }: {
  challenge: OperatorInputChallenge; available: boolean;
}) {
  const [credential, setCredential] = useState("");
  const [evidence, setEvidence] = useState("");
  const [observed, setObserved] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState("");
  const change = (key: string, value: string) => setValues((previous) => ({ ...previous, [key]: value }));
  const number = (key: string) => values[key]?.trim() ? Number(values[key]) : null;
  const flag = (key: string) => values[key] === "stopped" ? false : values[key] === "running" ? true : null;
  const recovery = challenge.purpose === "RECOVERY";
  const carousel = number("carousel");
  const validCarousel = carousel !== null && Number.isInteger(carousel) && carousel >= 1 && carousel <= 40;
  const validPumps = ["P1", "P2"].every((key) => number(key) === null
    || (Number.isInteger(number(key)) && number(key)! >= 0 && number(key)! <= 20500));
  const enabled = available && challenge.remaining_seconds > 0 && !sending;
  const valid = credential.trim() !== "" && evidence.trim() !== "" && observed
    && validCarousel && validPumps && values.reactor === "stopped";

  const send = async (cancel: boolean) => {
    setSending(true); setMessage("");
    const authorization = credential;
    setCredential("");
    try {
      if (cancel) {
        await cancelCurrentInput(challenge.request_id, authorization);
        setMessage("Confirmation cancelled. Read the backend result.");
      } else {
        const references: OperatorReferences = {
          evidence_note: evidence, observed_now_confirmed: true,
          pumps: ["P1", "P2"].map((pump_id) => ({ pump_id, position_steps: recovery ? null : number(pump_id) })),
          valve_positions: recovery ? [] : Array.from({ length: 8 }, (_, i) => `V${i + 1}`)
            .filter((key) => ["0", "90", "180"].includes(values[key]))
            .map((valve) => ({ valve, position_degrees: Number(values[valve]) })),
          reactor_mixer_running: flag("reactor"), sf_mixer_running: recovery ? null : flag("sfMixer"),
          sf_bottom_valve: recovery ? null : values.sfValve === "CLOSED" ? "CLOSED" : values.sfValve === "OPEN" ? "OPEN" : null,
          column_position_degrees: recovery || !["0", "4", "94"].includes(values.column) ? null : Number(values.column),
          carousel_position: carousel,
        };
        await submitCurrentInput(challenge.request_id, references, authorization);
        setObserved(false); setEvidence(""); setValues({});
        setMessage("Declaration received. Read the backend result; this does not confirm physical completion.");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Confirmation failed");
    } finally { setSending(false); }
  };

  const mixer = (key: string, label: string) => <label>{label}
    <select value={values[key] ?? ""} onChange={(event) => change(key, event.target.value)}>
      <option value="">Choose current state</option><option value="unknown">Unknown</option>
      <option value="stopped">Stopped</option><option value="running">Running</option>
    </select>
  </label>;

  return <section className="demoPanel" aria-label="Fresh operator confirmation">
    <div className="demoSectionHeading"><span>Current operator declaration</span><h2>Fresh references for {recovery ? "recovery" : "initialization / run"}</h2></div>
    <p>Operator: {challenge.operator}. Controller boot: {challenge.controller_boot_id}.
      Time remaining: {Math.ceil(challenge.remaining_seconds)} s.</p>
    <p>Confirm observations made for this request. Historical logs, preview values and visual estimates
      of raw pump coordinates cannot establish current references. Leave uncertain references unknown.</p>
    <p>Submitting permits the original requested action to continue if backend checks pass.
      These are operator statements; they do not prove safe routes, calibration or physical movement.</p>
    {recovery && <p>Pump, valve, Column and SF references remain unknown here. The requested recovery
      must establish them through its existing command sequence and still requires verified safe routing.</p>}
    <fieldset disabled={!enabled} className="ownedDemoFields demoMainSettings">
      <label>Operator access credential<input type="password" autoComplete="off" value={credential}
        onChange={(event) => setCredential(event.target.value)} /></label>
      <label>Current reference evidence<textarea value={evidence} maxLength={2000}
        onChange={(event) => setEvidence(event.target.value)} /></label>
      {mixer("reactor", "Current Reactor mixer state")}
      <label>Current manually aligned carousel position<input type="number" min="1" max="40" step="1"
        value={values.carousel ?? ""} onChange={(event) => change("carousel", event.target.value)} /></label>
      {!recovery && <>
        {["P1", "P2"].map((key) => <label key={key}>Current {key} raw position (blank = unknown)
          <input type="number" min="0" max="20500" step="1" value={values[key] ?? ""}
            onChange={(event) => change(key, event.target.value)} /></label>)}
        {Array.from({ length: 8 }, (_, i) => `V${i + 1}`).map((key) => <label key={key}>Current {key} reference
          <select value={values[key] ?? ""} onChange={(event) => change(key, event.target.value)}>
            <option value="">Unknown</option>{[0, 90, 180].map((value) => <option key={value} value={value}>{value} degrees</option>)}
          </select></label>)}
        {mixer("sfMixer", "Current SF mixer state")}
        <label>Current SF bottom valve state<select value={values.sfValve ?? ""}
          onChange={(event) => change("sfValve", event.target.value)}>
          <option value="">Unknown</option><option value="CLOSED">Closed</option><option value="OPEN">Open</option>
        </select></label>
        <label>Current Column reference<select value={values.column ?? ""}
          onChange={(event) => change("column", event.target.value)}>
          <option value="">Unknown</option><option value="0">HOME</option><option value="4">Closed</option><option value="94">Open</option>
        </select></label>
      </>}
      <label className="ownedDemoCheck"><input type="checkbox" checked={observed}
        onChange={(event) => setObserved(event.target.checked)} />I independently checked these references for this request.</label>
      <div className="demoPreviewActions">
        <button type="button" disabled={!valid} onClick={() => void send(false)}>Confirm and continue requested action</button>
        <button type="button" disabled={!credential.trim()} onClick={() => void send(true)}>Cancel current confirmation</button>
      </div>
    </fieldset>
    <p aria-live="polite">{message}</p>
  </section>;
}
