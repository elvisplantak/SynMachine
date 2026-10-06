export type DemoConfiguration = {
  b1_ratio_percent: string;
  total_mixture_volume_ml: string;
  combined_b1_b2_volume_ml: string;
  addition_order: "B1_THEN_B2" | "B2_THEN_B1";
  addition_speed_command_percent: string;
  reactor_mixing_command_percent: string;
  sf_mixing_command_percent: string;
  simulated_target_temperature_c: string;
  reaction_duration_seconds: string;
  delay_between_additions_seconds: string;
};

export type ExecutionSettings = {
  sf_mixing_duration_seconds: string;
  sf_settling_duration_seconds: string;
  fraction_count: number;
  fraction_duration_seconds: string;
};

export type OperatorInputChallenge = {
  request_id: string; purpose: "RUN" | "RECOVERY"; operator: string;
  controller_boot_id: number; connection_epoch: number; remaining_seconds: number;
};

export type OperatorReferences = {
  evidence_note: string; observed_now_confirmed: true;
  pumps: { pump_id: string; position_steps: number | null }[];
  valve_positions: { valve: string; position_degrees: number }[];
  reactor_mixer_running: boolean | null; sf_mixer_running: boolean | null;
  sf_bottom_valve: "CLOSED" | "OPEN" | null;
  column_position_degrees: number | null; carousel_position: number | null;
};

export type ExecutionStatus = {
  configured: true;
  busy: boolean;
  executing: boolean;
  operation: { operation_id: string; action: string; run_id: string | null } | null;
  error: string | null;
  retained_owner_id: string | null;
  run_id: string | null;
  automatic_resume_allowed: false;
  current_input?: OperatorInputChallenge | null;
  operator_current_input_configured?: boolean;
};

export type MachineSnapshot = {
  state: "STARTING" | "READY" | "BUSY" | "RECOVERY_REQUIRED" | "RECOVERING" | "FLUSH_REQUIRED" | "FLUSHING";
  active_run_id: string | null;
  interrupted_run_id: string | null;
  interrupted_maintenance_id: string | null;
  active_execution: { phase: string; start_committed_at: string | null } | null;
  active_maintenance: unknown | null;
};

export type DemoRun = {
  run_id: string;
  status: "CREATED" | "RUNNING" | "PAUSED" | "ABORTING" | "ABORTED" | "COMPLETED" | "FAULTED";
  phase: string;
  configuration: DemoConfiguration;
  execution_settings: ExecutionSettings;
};

export type DemoEvent = { sequence_number: number; occurred_at: string; message: string; event_type: string };

export type MaintenanceReadiness = {
  operator: string;
  evidence_note: string;
  waste_air_gap_verified: true;
  switching_sequences_verified: true;
  working_calibrations_verified: true;
  reactor_mixer_stopped: true;
  carousel_manually_aligned: true;
};

export class DemoApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request(path: string, body?: unknown, signal?: AbortSignal, credential?: string): Promise<unknown> {
  const response = await fetch(`/api/v1${path}`, {
    method: body === undefined ? "GET" : "POST",
    ...(body === undefined ? {} : { headers: { "Content-Type": "application/json", ...(credential === undefined ? {} : { Authorization: `Bearer ${credential}` }) }, body: JSON.stringify(body) }),
    signal,
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof payload?.detail === "string" ? payload.detail : `Backend returned HTTP ${response.status}`;
    throw new DemoApiError(detail, response.status);
  }
  if (!payload || typeof payload !== "object") throw new Error("Backend returned an invalid response");
  return payload;
}

const isNullableString = (value: unknown) => value === null || typeof value === "string";

export async function readExecution(signal?: AbortSignal): Promise<ExecutionStatus> {
  const data = await request("/execution", undefined, signal) as ExecutionStatus;
  if (data.configured !== true || typeof data.busy !== "boolean" || typeof data.executing !== "boolean" || data.automatic_resume_allowed !== false
    || !isNullableString(data.run_id) || !isNullableString(data.error) || !isNullableString(data.retained_owner_id)
    || (data.operation !== null && (!data.operation || typeof data.operation.operation_id !== "string"
      || typeof data.operation.action !== "string" || !isNullableString(data.operation.run_id)))) {
    throw new Error("Backend execution status is invalid");
  }
  if (data.operator_current_input_configured !== undefined && typeof data.operator_current_input_configured !== "boolean") {
    throw new Error("Backend operator input status is invalid");
  }
  const current = data.current_input;
  if (current !== undefined && current !== null && (!current || typeof current.request_id !== "string" || !current.request_id.trim()
    || !["RUN", "RECOVERY"].includes(current.purpose) || typeof current.operator !== "string" || !current.operator.trim()
    || !Number.isInteger(current.controller_boot_id) || current.controller_boot_id < 1 || current.controller_boot_id > 4294967295
    || !Number.isInteger(current.connection_epoch) || current.connection_epoch < 1
    || !Number.isFinite(current.remaining_seconds) || current.remaining_seconds < 0)) {
    throw new Error("Backend current input challenge is invalid");
  }
  return data;
}

export async function readMachine(signal?: AbortSignal): Promise<MachineSnapshot | null> {
  try {
    const data = await request("/machine", undefined, signal) as MachineSnapshot;
    if (!["STARTING", "READY", "BUSY", "RECOVERY_REQUIRED", "RECOVERING", "FLUSH_REQUIRED", "FLUSHING"].includes(data.state)
      || !isNullableString(data.active_run_id) || !isNullableString(data.interrupted_run_id)
      || !isNullableString(data.interrupted_maintenance_id)
      || data.active_execution === undefined || data.active_maintenance === undefined) {
      throw new Error("Backend machine snapshot is invalid");
    }
    return data;
  } catch (error) {
    if (error instanceof DemoApiError && error.status === 404) return null;
    throw error;
  }
}

export async function readRun(runId: string, signal?: AbortSignal): Promise<DemoRun> {
  const data = await request(`/runs/${encodeURIComponent(runId)}`, undefined, signal) as DemoRun;
  if (data.run_id !== runId || !["CREATED", "RUNNING", "PAUSED", "ABORTING", "ABORTED", "COMPLETED", "FAULTED"].includes(data.status)
    || typeof data.phase !== "string" || !data.configuration || !data.execution_settings) {
    throw new Error("Backend run snapshot is invalid or belongs to another run");
  }
  return data;
}

export function newRunBlockReason(status: ExecutionStatus | null, machine: MachineSnapshot | null): string | null {
  if (status === null) return "Connect to the backend to read current readiness.";
  if (status.busy) return "An execution is in progress.";
  if (status.retained_owner_id !== null) return "Hardware remains reserved until required maintenance finishes.";
  if (status.error !== null) return status.error;
  if (machine !== null && (machine.state !== "READY" || machine.active_execution !== null || machine.active_maintenance !== null)) {
    return "The machine must return to READY before a new run.";
  }
  return null;
}

export async function createRun(runId: string, configuration: DemoConfiguration, executionSettings: ExecutionSettings) {
  const data = await request("/runs", { run_id: runId, configuration, execution_settings: executionSettings, occurred_at: new Date().toISOString() }) as DemoRun;
  if (data.run_id !== runId || data.status !== "CREATED") throw new Error("Backend did not confirm this run configuration");
  return data;
}

export async function runCommand(runId: string, action: "start" | "stop/request" | "pause" | "resume") {
  const data = await request(`/runs/${encodeURIComponent(runId)}/${action}`, { occurred_at: new Date().toISOString() }) as {
    run_id?: string; operation_id?: string; action?: string; run?: DemoRun;
  };
  if (action === "start") {
    if (data.run_id !== runId || data.action !== "RUN" || !data.operation_id) {
      throw new Error("Backend did not confirm execution acceptance for this run");
    }
  } else if (data.run?.run_id !== runId && (data.run_id !== runId || !data.operation_id)) {
    throw new Error("Backend command response belongs to another run");
  }
  return data;
}

export async function maintenanceCommand(action: "recovery" | "flush", runId: string | null, readiness: MaintenanceReadiness) {
  const data = await request(`/machine/${action}/start`, { run_id: runId, readiness, occurred_at: new Date().toISOString() }) as {
    run_id?: string | null; operation_id?: string; action?: string;
  };
  if (data.run_id !== runId || data.action !== action.toUpperCase() || !data.operation_id) {
    throw new Error("Backend did not confirm maintenance acceptance");
  }
  return data;
}

export async function initializeMachine() {
  const data = await request("/machine/initialize", { occurred_at: new Date().toISOString() }) as MachineSnapshot;
  if (data.state !== "READY" || data.active_execution !== null || data.active_maintenance !== null) {
    throw new Error("Backend did not confirm initial readiness");
  }
  return data;
}

export async function stopOperation(operationId: string, runId: string | null = null) {
  const data = await request(`/execution/${encodeURIComponent(operationId)}/stop`, { occurred_at: new Date().toISOString() }) as {
    operation_id?: string; run?: DemoRun;
  };
  if (data.operation_id !== operationId && (runId === null || data.run?.run_id !== runId)) {
    throw new Error("Backend did not confirm Stop for this operation");
  }
  return data;
}

export async function readEvents(runId: string, signal?: AbortSignal): Promise<DemoEvent[]> {
  const data = await request(`/runs/${encodeURIComponent(runId)}/events`, undefined, signal);
  if (!Array.isArray(data) || data.some((event) => !Number.isInteger(event.sequence_number)
    || typeof event.occurred_at !== "string" || typeof event.message !== "string" || typeof event.event_type !== "string")) {
    throw new Error("Backend event history is invalid");
  }
  return data as DemoEvent[];
}

export async function readMachineEvents(signal?: AbortSignal): Promise<DemoEvent[]> {
  const data = await request("/machine/events", undefined, signal);
  if (!Array.isArray(data) || data.some((event) => !Number.isInteger(event.sequence_number)
    || typeof event.occurred_at !== "string" || typeof event.message !== "string" || typeof event.event_type !== "string")) {
    throw new Error("Backend machine event history is invalid");
  }
  return data as DemoEvent[];
}


export async function submitCurrentInput(requestId: string, references: OperatorReferences, credential: string) {
  const data = await request(`/execution/current-input/${encodeURIComponent(requestId)}`, references, undefined, credential) as {
    request_id?: string; declaration_received?: boolean;
  };
  if (data.request_id !== requestId || data.declaration_received !== true) {
    throw new Error("Backend did not acknowledge this current declaration");
  }
  return data;
}

export async function cancelCurrentInput(requestId: string, credential: string) {
  const data = await request(`/execution/current-input/${encodeURIComponent(requestId)}/cancel`, {}, undefined, credential) as {
    request_id?: string; cancelled?: boolean;
  };
  if (data.request_id !== requestId || data.cancelled !== true) {
    throw new Error("Backend did not acknowledge this current cancellation");
  }
  return data;
}
