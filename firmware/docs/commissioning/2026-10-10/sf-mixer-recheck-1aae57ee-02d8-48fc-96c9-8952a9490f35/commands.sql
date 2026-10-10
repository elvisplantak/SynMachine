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
INSERT INTO "arduino_command_journal" VALUES('05fd3dcb-7789-46ef-bb09-5a6363522bb8','sf-mixer-recheck-bd9fc153-aaf4-44b1-93ca-bf1ed7ebed61',96,'SF_MIXER_SET_STATE','{"running":false}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('62409b24-0388-46a5-8fcc-ca39ae16cd38','sf-mixer-recheck-bd9fc153-aaf4-44b1-93ca-bf1ed7ebed61',96,'SF_MIXER_SET_STATE','{"running":true}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('07d440d1-0199-4e50-aba0-db09fccb73dd','sf-mixer-recheck-bd9fc153-aaf4-44b1-93ca-bf1ed7ebed61',96,'SF_MIXER_SET_STATE','{"running":false}','COMPLETED','{}',NULL,1);
COMMIT;
