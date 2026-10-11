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
INSERT INTO "arduino_command_journal" VALUES('cd73e48e-3d56-4d59-8486-779caaba9cac','sf-mixer-recheck-f64b3230-0085-4ba3-88a4-91c657f2b423',98,'SF_MIXER_SET_STATE','{"running":false}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('4ec70e4f-1cf2-4b98-9c8e-70b7012d0235','sf-mixer-recheck-f64b3230-0085-4ba3-88a4-91c657f2b423',98,'SF_MIXER_SET_STATE','{"running":true}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('afa094bb-92b6-4f26-a0d6-991c8d13fac5','sf-mixer-recheck-f64b3230-0085-4ba3-88a4-91c657f2b423',98,'SF_MIXER_SET_STATE','{"running":false}','COMPLETED','{}',NULL,1);
COMMIT;
