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
INSERT INTO "arduino_command_journal" VALUES('46c2ec8f-7a3e-4674-90c6-61ba31c771c7','v7-v8-home-90-745e60e3-c059-41ac-bb1c-737739e1158f',71,'VALVE_HOME','{"valve":"V7"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('bca54297-8c86-4064-aa9d-3e934174bc5e','v7-v8-home-90-745e60e3-c059-41ac-bb1c-737739e1158f',71,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V7"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('b30cf7d8-b0ef-44e3-8e46-2b63f53899bb','v7-v8-home-90-745e60e3-c059-41ac-bb1c-737739e1158f',71,'VALVE_HOME','{"valve":"V8"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('7ae4e77f-aad4-4cdf-89c2-68696de6bf64','v7-v8-home-90-745e60e3-c059-41ac-bb1c-737739e1158f',71,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V8"}','COMPLETED','{}',NULL,1);
COMMIT;
