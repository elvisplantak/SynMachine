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
COMMIT;
