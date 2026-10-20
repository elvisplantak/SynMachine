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
INSERT INTO "arduino_command_journal" VALUES('47d83bbf-3f70-4ecb-88d9-58ab69e32832','p1-dry-b2f322e1-1736-4dd4-8613-696cd38bea3c',80,'VALVE_HOME','{"valve":"V1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('5d1278ab-f602-409c-a3fb-22dcc04dbb9e','p1-dry-b2f322e1-1736-4dd4-8613-696cd38bea3c',80,'VALVE_HOME','{"valve":"V2"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('15522c61-9c1c-4f59-be0e-d9960231efac','p1-dry-b2f322e1-1736-4dd4-8613-696cd38bea3c',80,'VALVE_HOME','{"valve":"V4"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('b3eb293d-7de0-452e-8548-da56b9fa980d','p1-dry-b2f322e1-1736-4dd4-8613-696cd38bea3c',80,'VALVE_HOME','{"valve":"V6"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('f1273245-90a6-5b7b-9792-e084e42d2068','p1-dry-b2f322e1-1736-4dd4-8613-696cd38bea3c',80,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V6"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('1ea9d6c6-8212-5175-993e-192bf00d2b15','p1-dry-b2f322e1-1736-4dd4-8613-696cd38bea3c',80,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('72bc0fcd-658d-5853-9587-5c01baf96dd2','p1-dry-b2f322e1-1736-4dd4-8613-696cd38bea3c',80,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V2"}','FAILED',NULL,'VALVE_HOME_SWITCH_UNEXPECTED',1);
COMMIT;
