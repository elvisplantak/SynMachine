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
INSERT INTO "arduino_command_journal" VALUES('a54f50e1-c65c-4ddb-a84c-4b72fc4d80c4','v2-recheck-0f4ddec5-05d1-49b4-baa9-dca4229a4a12',81,'VALVE_HOME','{"valve":"V2"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('77fedf8a-8c86-454b-a810-bbcd4192c279','v2-recheck-0f4ddec5-05d1-49b4-baa9-dca4229a4a12',81,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V2"}','COMPLETED','{}',NULL,1);
COMMIT;
