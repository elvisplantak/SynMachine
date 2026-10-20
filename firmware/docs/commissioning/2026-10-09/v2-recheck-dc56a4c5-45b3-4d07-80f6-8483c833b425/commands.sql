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
INSERT INTO "arduino_command_journal" VALUES('d8092f21-c32a-47c0-81d1-b771c352b553','v2-recheck-dc56a4c5-45b3-4d07-80f6-8483c833b425',84,'VALVE_HOME','{"valve":"V2"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('592ca459-9238-4fe4-bcae-61e8629719ae','v2-recheck-dc56a4c5-45b3-4d07-80f6-8483c833b425',84,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V2"}','COMPLETED','{}',NULL,1);
COMMIT;
