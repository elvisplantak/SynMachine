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
INSERT INTO "arduino_command_journal" VALUES('a3491333-c69b-4fc9-8d52-d0a9a37b7462','p2-pump-dry-2282ffd4-54ee-4598-a071-3cd01b5dee9d',92,'VALVE_HOME','{"valve":"V3"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('7c20fb8e-98f2-405f-b156-e5f38f66cc13','p2-pump-dry-2282ffd4-54ee-4598-a071-3cd01b5dee9d',92,'VALVE_HOME','{"valve":"V7"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('85cfa468-e4de-4989-81d9-7a2cc66eb6e7','p2-pump-dry-2282ffd4-54ee-4598-a071-3cd01b5dee9d',92,'VALVE_HOME','{"valve":"V8"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('04187540-b645-4719-ba18-27174d34517d','p2-pump-dry-2282ffd4-54ee-4598-a071-3cd01b5dee9d',92,'VALVE_HOME','{"valve":"V5"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('c1d6413a-2b78-541a-90b4-1f578f712f3d','p2-pump-dry-2282ffd4-54ee-4598-a071-3cd01b5dee9d',92,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V5"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('afa36a8b-7867-585a-a1b7-bb4865ec7978','p2-pump-dry-2282ffd4-54ee-4598-a071-3cd01b5dee9d',92,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V8"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('59f01525-e7c8-5b90-8c5a-7de919e9e9a2','p2-pump-dry-2282ffd4-54ee-4598-a071-3cd01b5dee9d',92,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V7"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('d1b99609-7c6d-504f-a154-0414508ba12b','p2-pump-dry-2282ffd4-54ee-4598-a071-3cd01b5dee9d',92,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V3"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('1acc0301-cae9-4a24-b0a8-f2fb9049b032','p2-pump-dry-2282ffd4-54ee-4598-a071-3cd01b5dee9d',92,'PUMP_HOME','{"pump":"P2"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('f6a0cbd4-d9ee-4988-99fb-55c13f8bc1d9','p2-pump-dry-2282ffd4-54ee-4598-a071-3cd01b5dee9d',92,'PUMP_MOVE_ABSOLUTE_STEPS','{"pump":"P2","target_steps":1000}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('f006732a-d78d-40e3-8d7c-8522ad279ab1','p2-pump-dry-2282ffd4-54ee-4598-a071-3cd01b5dee9d',92,'PUMP_HOME','{"pump":"P2"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('bffc3769-c989-445b-8a3a-911bbd248689','p2-pump-dry-2282ffd4-54ee-4598-a071-3cd01b5dee9d',92,'PUMP_MOVE_ABSOLUTE_STEPS','{"pump":"P2","target_steps":1000}','COMPLETED','{}',NULL,1);
COMMIT;
