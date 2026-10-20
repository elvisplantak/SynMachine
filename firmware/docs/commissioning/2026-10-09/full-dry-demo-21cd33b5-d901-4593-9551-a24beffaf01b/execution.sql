BEGIN TRANSACTION;
CREATE TABLE arduino_command_journal (
    operation_command_id TEXT NOT NULL PRIMARY KEY,
    phase_execution_id TEXT NOT NULL,
    controller_boot_id INTEGER NOT NULL CHECK (controller_boot_id >= 0),
    command TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN (
        'INTENT_PERSISTED', 'COMPLETED', 'REJECTED', 'FAILED', 'OUTCOME_UNKNOWN'
    )),
    result_json TEXT,
    error_code TEXT,
    execution_started INTEGER CHECK (execution_started IN (0, 1))
);
CREATE TABLE execution_carousel_projection (
 phase_id TEXT PRIMARY KEY NOT NULL, position INTEGER CHECK(position BETWEEN 1 AND 40)
);
CREATE TABLE execution_identity (
 id TEXT NOT NULL, ownership_id TEXT NOT NULL
);
INSERT INTO "execution_identity" VALUES('8e00164b-e6ab-4f21-a4ec-b5aae2b29bc2','1c587783-414d-46f8-9996-424c580c3f0b');
CREATE TABLE execution_waits (
 phase_id TEXT NOT NULL, operation_number INTEGER NOT NULL,
 duration_seconds TEXT NOT NULL, state TEXT NOT NULL
 CHECK(state IN ('INTENT_PERSISTED', 'COMPLETED', 'STOP_REQUESTED', 'OUTCOME_UNKNOWN')),
 operation_completed INTEGER NOT NULL DEFAULT 0 CHECK(operation_completed IN (0, 1)),
 PRIMARY KEY(phase_id, operation_number)
);
CREATE TABLE prepared_command_plans (
    phase_execution_id TEXT NOT NULL PRIMARY KEY,
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
);
CREATE TABLE sf_action_journal (
 action_id TEXT PRIMARY KEY NOT NULL, phase_id TEXT NOT NULL,
 session_id TEXT NOT NULL, target TEXT NOT NULL CHECK(target IN ('OPEN', 'CLOSED')),
 state TEXT NOT NULL CHECK(state IN ('INTENT_PERSISTED', 'COMPLETED', 'OUTCOME_UNKNOWN')),
 error TEXT
);
COMMIT;
