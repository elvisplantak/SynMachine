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
INSERT INTO "arduino_command_journal" VALUES('1be14827-2b28-424e-8b60-1ef0a44d83ec','p1-span-dry-521e41d1-4885-4972-bb46-00ddea2d05f5',90,'VALVE_HOME','{"valve":"V1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('355622ef-4173-4efc-a0fe-b8f0d2ea028b','p1-span-dry-521e41d1-4885-4972-bb46-00ddea2d05f5',90,'VALVE_HOME','{"valve":"V2"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('bce0b27b-05b7-55df-9426-97cf80e590a4','p1-span-dry-521e41d1-4885-4972-bb46-00ddea2d05f5',90,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V2"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('52e60a3c-e183-530d-9757-92d656c2b297','p1-span-dry-521e41d1-4885-4972-bb46-00ddea2d05f5',90,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('f9c8ca96-ab5f-456e-8c4f-d0d6c9e7abfd','p1-span-dry-521e41d1-4885-4972-bb46-00ddea2d05f5',90,'PUMP_HOME','{"pump":"P1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('f9827650-9d2b-41e3-9cec-14620f0d5084','p1-span-dry-521e41d1-4885-4972-bb46-00ddea2d05f5',90,'PUMP_MOVE_ABSOLUTE_STEPS','{"pump":"P1","target_steps":20500}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('048ed2b7-201e-4bdf-b2d1-8df46989461d','p1-span-dry-521e41d1-4885-4972-bb46-00ddea2d05f5',90,'PUMP_HOME','{"pump":"P1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('d0456d81-0f3b-49ba-b1a1-0b4f4f44d170','p1-span-dry-521e41d1-4885-4972-bb46-00ddea2d05f5',90,'PUMP_MOVE_ABSOLUTE_STEPS','{"pump":"P1","target_steps":1000}','COMPLETED','{}',NULL,1);
COMMIT;
