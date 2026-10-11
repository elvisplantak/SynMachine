import { ExecutionFlowView } from "./ExecutionFlowView";
import { useEffect, useRef, useState } from "react";
import { OperatorCurrentInput } from "./OperatorCurrentInput";
import {
  createRun, maintenanceCommand, newRunBlockReason, readEvents, readExecution,
  readMachine, readMachineEvents, readRun, runCommand, initializeMachine, stopOperation,
} from "./guidedDemoApi";
import type {
  DemoConfiguration, DemoEvent, DemoRun, ExecutionSettings, ExecutionStatus,
  MachineSnapshot, MaintenanceReadiness,
} from "./guidedDemoApi";

import { stepLabel } from "./recipeApi";

const phaseLabels: Record<string, string> = {
  READY: "Ready", P1_TRANSFER_S_TO_REACTOR: "Transfer solvent to Reactor",
  P1_TRANSFER_FIRST_LIQUID_TO_REACTOR: "Transfer first liquid to Reactor",
  DELAY_BETWEEN_ADDITIONS: "Delay between additions",
  P1_TRANSFER_SECOND_LIQUID_TO_REACTOR: "Transfer second liquid to Reactor",
  REACTION_HOLD: "Reaction hold", P2_TRANSFER_REACTOR_TO_SF: "Transfer Reactor contents to SF",
  SF_MIXING: "SF mixing", SF_SETTLING: "SF settling",
  P2_TRANSFER_SF_TO_COLUMN: "Transfer SF contents to Column",
  COLUMN_FRACTION_COLLECTION: "Column fraction collection", COMPLETED: "Completed",
};

const readinessLabels = {
  waste_air_gap_verified: "Waste air gap is verified",
  switching_sequences_verified: "Valve switching sequences are verified",
  working_calibrations_verified: "Working pump calibrations are verified",
  reactor_mixer_stopped: "Reactor mixer is stopped",
  carousel_manually_aligned: "Carousel is manually aligned for this attempt",
};
type ReadinessKey = keyof typeof readinessLabels;

export function OwnedDemoControls({ configuration, configurationValid, onLock, showLog, hideDemoSettings = false, onBlockReason }: {
  configuration?: DemoConfiguration; configurationValid: boolean;
  onLock: (locked: boolean) => void; showLog: boolean;
  hideDemoSettings?: boolean; onBlockReason?: (reason: string | null) => void;
}) {
  const [status, setStatus] = useState<ExecutionStatus | null>(null);
  const [machine, setMachine] = useState<MachineSnapshot | null>(null);
  const [run, setRun] = useState<DemoRun | null>(null);
  const [events, setEvents] = useState<DemoEvent[]>([]);
  const [machineEvents, setMachineEvents] = useState<DemoEvent[]>([]);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const [awaitingRefresh, setAwaitingRefresh] = useState(false);
  const [settings, setSettings] = useState({ mixing: "", settling: "", count: "", collection: "" });
  const [operator, setOperator] = useState("");
  const [evidence, setEvidence] = useState("");
  const [checks, setChecks] = useState<Partial<Record<ReadinessKey, boolean>>>({});
  const generation = useRef(0);
  const refreshRequested = useRef(false);

  useEffect(() => {
    let alive = true;
    let timeout: ReturnType<typeof setTimeout>;
    const abort = new AbortController();
    const poll = async () => {
      const observedGeneration = generation.current;
      try {
        const currentStatus = await readExecution(abort.signal);
        const currentMachine = await readMachine(abort.signal);
        const id = currentMachine?.interrupted_maintenance_id ? null
          : currentMachine?.active_run_id ?? currentStatus.run_id ?? currentMachine?.interrupted_run_id;
        const currentRun = id ? await readRun(id, abort.signal) : null;
        const currentEvents = id ? await readEvents(id, abort.signal) : [];
        const currentMachineEvents = await readMachineEvents(abort.signal);
        if (alive && observedGeneration === generation.current) {
          setStatus(currentStatus); setMachine(currentMachine); setRun(currentRun);
          setEvents(currentEvents); setMachineEvents(currentMachineEvents); setConnectionError(null);
          setAwaitingRefresh(false);
        }
      } catch (error) {
        if (alive && !abort.signal.aborted) {
          setConnectionError(error instanceof Error ? error.message : "Backend connection failed");
        }
      } finally {
        if (alive) {
          const delay = refreshRequested.current ? 0 : 500;
          refreshRequested.current = false;
          timeout = setTimeout(poll, delay);
        }
      }
    };
    void poll();
    return () => { alive = false; abort.abort(); clearTimeout(timeout); };
  }, []);

  const active = status?.busy === true;
  const runUnresolved = run !== null && ["RUNNING", "PAUSED", "ABORTING"].includes(run.status);
  useEffect(() => {
    onLock(active || runUnresolved || pending || awaitingRefresh || (status !== null && connectionError !== null));
  }, [active, runUnresolved, pending, awaitingRefresh, status, connectionError, onLock]);

  const settingValues = Object.values(settings).map(Number);
  const settingsValid = Object.values(settings).every((value) => value.trim() !== "")
    && settingValues.every(Number.isFinite) && Number(settings.mixing) > 0
    && Number(settings.settling) >= 0 && Number(settings.collection) > 0
    && Number.isInteger(Number(settings.count)) && Number(settings.count) >= 1;
  const blockReason = connectionError ?? newRunBlockReason(status, machine);
  const runId = run?.run_id ?? status?.run_id ?? null;
  const idle = status !== null && !status.busy && !pending && !awaitingRefresh && connectionError === null;
  const unresolvedIntent = machine?.active_execution != null || machine?.active_maintenance != null;
  const canRecover = idle && !!status.retained_owner_id && !unresolvedIntent
    && (!!runId || !!machine?.interrupted_maintenance_id);
  const recipeAttemptNotStarted = idle && status?.operator_current_input_configured === true
    && run?.recipe != null && run.status === "CREATED" && status.retained_owner_id === null
    && !unresolvedIntent && (machine === null || machine.state === "READY");
  const recipeBlockReason = recipeAttemptNotStarted
    ? newRunBlockReason({ ...status!, error: null }, machine) : blockReason;
  useEffect(() => { onBlockReason?.(recipeBlockReason); }, [recipeBlockReason, onBlockReason]);
  const cleanStop = status?.operation?.action === "RUN" && run?.status === "ABORTED" && status.error === null;
  const recovered = status?.operation?.action === "RECOVERY" && status.error === null;
  const canFlush = idle && !unresolvedIntent && (
    (machine?.state === "READY" && status.retained_owner_id === null && status.error === null)
    || (machine?.state === "FLUSH_REQUIRED" && (cleanStop || recovered))
  );
  const readinessValid = operator.trim() !== "" && evidence.trim() !== ""
    && (Object.keys(readinessLabels) as ReadinessKey[]).every((key) => checks[key] === true);
  const startedWait = machine?.active_execution?.start_committed_at != null
    && ["DELAY_BETWEEN_ADDITIONS", "REACTION_HOLD"].includes(run?.phase ?? "");

  const command = async (callback: () => Promise<unknown>, acceptedMessage: string) => {
    setPending(true); generation.current += 1;
    try {
      await callback();
      setMessage(acceptedMessage);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Backend command failed");
    } finally {
      generation.current += 1; refreshRequested.current = true; setAwaitingRefresh(true); setPending(false);
    }
  };

  const start = () => command(async () => {
    if (!configuration) throw new Error("Guided Demo configuration is missing");
    const id = crypto.randomUUID();
    const executionSettings: ExecutionSettings = {
      sf_mixing_duration_seconds: settings.mixing, sf_settling_duration_seconds: settings.settling,
      fraction_count: Number(settings.count), fraction_duration_seconds: settings.collection,
    };
    await createRun(id, configuration, executionSettings);
    await runCommand(id, "start");
  }, "Run accepted. Follow the backend phase and status below.");

  const maintain = (action: "recovery" | "flush") => command(async () => {
    const readiness: MaintenanceReadiness = {
      operator, evidence_note: evidence, waste_air_gap_verified: true,
      switching_sequences_verified: true, working_calibrations_verified: true,
      reactor_mixer_stopped: true, carousel_manually_aligned: true,
    };
    setChecks({}); setEvidence("");
    await maintenanceCommand(action, runId, readiness);
  }, `${action === "recovery" ? "Recovery" : "Flushing"} accepted. Completion is reported by the backend.`);

  return <section className="ownedDemoControls demoControlTray" aria-label="Backend Guided Demo">
    {hideDemoSettings && <div className="demoPanel"><ExecutionFlowView /></div>}
    <section className="demoPanel">
      <div className="demoSectionHeading"><span>Backend state</span><h2>{run?.recipe ? (run.status === "COMPLETED" ? "Procedure completed" : `Step ${(run.recipe_step_index ?? 0) + 1}: ${stepLabel(run.recipe.definition.steps[run.recipe_step_index ?? 0], run.recipe.definition.sources)}`) : run ? phaseLabels[run.phase] ?? run.phase : "No run started"}</h2></div>
      {run?.recipe && <p>{run.recipe.definition.name} · version {run.recipe.revision} · step {Math.min((run.recipe_step_index ?? 0) + 1, run.recipe.definition.steps.length)} / {run.recipe.definition.steps.length}</p>}
      <dl className="demoReviewSettings">
        <div><dt>Machine</dt><dd>{machine?.state ?? (status ? "Uninitialized" : "Unavailable")}</dd></div>
        <div><dt>Run</dt><dd>{run?.status ?? "None"}</dd></div>
        <div><dt>Current operation</dt><dd>{status?.busy ? (status.executing ? status.operation?.action : "Service / configuration") : status?.error ? "Blocked" : "Idle"}</dd></div>
      </dl>
      {connectionError && <p role="alert">{connectionError}. Current state could not be refreshed.</p>}
      {status?.error && <p role="alert">Execution stopped: {status.error}</p>}
      <p aria-live="polite">{connectionError ? "Backend state could not be refreshed."
        : message ? `Last request: ${message}`
          : status ? "Backend state connected." : "Reading backend state…"}</p>
      <div className="demoPreviewActions">
        <button type="button" disabled={!status?.executing || !status.operation || pending || run?.status === "ABORTING"}
          onClick={() => void command(() => stopOperation(status!.operation!.operation_id, status!.operation!.run_id), "Stop requested. The current atomic operation finishes first.")}>Stop execution</button>
        <button type="button" disabled={!startedWait || run?.status !== "RUNNING" || pending || awaitingRefresh || connectionError !== null}
          onClick={() => void command(() => runCommand(runId!, "pause"), "Pause requested.")}>Pause wait</button>
        <button type="button" disabled={!startedWait || run?.status !== "PAUSED" || pending || awaitingRefresh || connectionError !== null}
          onClick={() => void command(() => runCommand(runId!, "resume"), "Resume requested for the current wait.")}>Resume wait</button>
      </div>
      {blockReason && <p className="demoLockedNote">{blockReason}</p>}
      {recipeAttemptNotStarted && <p>The previous procedure attempt did not start. Review the recipe again and provide fresh confirmations for a new attempt. The previous record is preserved.</p>}
      {machine?.state === "FLUSH_REQUIRED" && canRecover && !canFlush
        && <p>Flushing requires a successful recovery in the current backend session. Repeat recovery after a backend restart.</p>}
      {(machine === null || machine.state === "STARTING") && <button type="button" disabled={!idle || status.retained_owner_id !== null || status.error !== null}
        onClick={() => void command(initializeMachine, "Initial backend state confirmed.")}>Initialize configured system</button>}
      {(unresolvedIntent || runUnresolved || (status?.retained_owner_id && !canRecover && machine?.state !== "FLUSH_REQUIRED")) && !active
        && <p>The interrupted operation requires backend restart and reconciliation before recovery.</p>}
      {status?.operator_current_input_configured && idle && !run?.recipe && run?.status === "CREATED"
        && status.retained_owner_id === null && !unresolvedIntent && (machine === null || machine.state === "READY")
        && <button type="button" onClick={() => void command(() => runCommand(run.run_id, "start"),
          "Current run requested again with a new confirmation attempt.")}>Retry current run with fresh confirmation</button>}
      <p>Phase completion describes command results. Volumes, cleaning and physical movement are not measured by this display.</p>
    </section>

    {connectionError === null && status?.current_input && <OperatorCurrentInput
      key={status.current_input.request_id} challenge={status.current_input} available={true} />}

    {!showLog && <>
      {!hideDemoSettings && <section className="demoPanel">
        <div className="demoSectionHeading"><span>Before starting</span><h2>Execution settings</h2></div>
        <p>SF mixing duration is applied by the executor using the fixed ON/OFF mixing profile. Stored mixing percentages do not set speed.</p>
        <fieldset disabled={active || pending || awaitingRefresh} className="ownedDemoFields demoMainSettings">
          <label>SF mixing duration (s)<input type="number" min="0" step="any" value={settings.mixing} onChange={(e) => setSettings({ ...settings, mixing: e.target.value })} /></label>
          <label>SF settling duration (s)<input type="number" min="0" step="any" value={settings.settling} onChange={(e) => setSettings({ ...settings, settling: e.target.value })} /></label>
          <label>Fraction count<input type="number" min="1" step="1" value={settings.count} onChange={(e) => setSettings({ ...settings, count: e.target.value })} /></label>
          <label>Duration per fraction (s)<input type="number" min="0" step="any" value={settings.collection} onChange={(e) => setSettings({ ...settings, collection: e.target.value })} /></label>
        </fieldset>
        <button className="demoPrimaryButton" type="button" disabled={blockReason !== null || pending || awaitingRefresh || !configurationValid || !settingsValid} onClick={() => void start()}>Start configured run</button>
        {(!settingsValid || !configurationValid) && <p>Review the configured volumes and enter all execution settings before starting.</p>}
        {run?.configuration && run.execution_settings && <p>Started run: total {run.configuration.total_mixture_volume_ml} ml; SF mixing {run.execution_settings.sf_mixing_duration_seconds} s. These are configured values.</p>}
      </section>}
      <section className="demoPanel">
        <div className="demoSectionHeading"><span>Local operator</span><h2>Recovery and Flush system</h2></div>
        <fieldset disabled={active || pending || awaitingRefresh} className="ownedDemoFields">
          <label>Operator<input value={operator} onChange={(e) => setOperator(e.target.value)} /></label>
          <label>Evidence for this attempt<textarea value={evidence} onChange={(e) => setEvidence(e.target.value)} /></label>
          {(Object.keys(readinessLabels) as ReadinessKey[]).map((key) => <label className="ownedDemoCheck" key={key}><input type="checkbox" checked={checks[key] ?? false} onChange={(e) => setChecks({ ...checks, [key]: e.target.checked })} /><span>{readinessLabels[key]}</span></label>)}
        </fieldset>
        <p>These confirmations are operator statements. Each attempt needs fresh confirmations.</p>
        <div className="demoPreviewActions">
          <button type="button" disabled={!canRecover || !readinessValid} onClick={() => void maintain("recovery")}>Start recovery</button>
          <button type="button" disabled={!canFlush || !readinessValid} onClick={() => void maintain("flush")}>Flush system</button>
        </div>
      </section>
    </>}

    <section className="demoPanel">
      <div className="demoSectionHeading"><span>Persisted backend events</span><h2>Current run log</h2></div>
      {events.length === 0 ? <p>No run events are available.</p> : <ol className="ownedDemoEvents">{events.map((event) => <li key={`${run?.run_id}:${event.sequence_number}`}><time>{new Date(event.occurred_at).toLocaleTimeString()}</time><span>{event.message}</span></li>)}</ol>}
    </section>
    <section className="demoPanel">
      <div className="demoSectionHeading"><span>Persisted backend events</span><h2>Machine and maintenance log</h2></div>
      {machineEvents.length === 0 ? <p>No machine events are available.</p> : <ol className="ownedDemoEvents">{machineEvents.map((event) => <li key={event.sequence_number}><time>{new Date(event.occurred_at).toLocaleTimeString()}</time><span>{event.message}</span></li>)}</ol>}
    </section>
  </section>;
}
