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
INSERT INTO "arduino_command_journal" VALUES('81d0e74d-3e43-4494-a5c3-963d36e988a6','pump-dry-fa3ce511-3f30-4170-9fed-c68eb98a897e',87,'VALVE_HOME','{"valve":"V1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('d8cee50b-8398-4206-b238-e65153576a84','pump-dry-fa3ce511-3f30-4170-9fed-c68eb98a897e',87,'VALVE_HOME','{"valve":"V2"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('ccf19dd1-89e6-513e-9c0d-eed6def2c3fc','pump-dry-fa3ce511-3f30-4170-9fed-c68eb98a897e',87,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V2"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('c7bf77a5-ab99-5a2f-8f95-0cffcae1e0a2','pump-dry-fa3ce511-3f30-4170-9fed-c68eb98a897e',87,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('a26a72bb-06cf-433e-af4a-b4bd39dce1c1','pump-dry-fa3ce511-3f30-4170-9fed-c68eb98a897e',87,'PUMP_HOME','{"pump":"P1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('b1d15165-5758-4c11-aabf-e65937f7ee92','pump-dry-fa3ce511-3f30-4170-9fed-c68eb98a897e',87,'PUMP_MOVE_ABSOLUTE_STEPS','{"pump":"P1","target_steps":1000}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('7ac89025-79f0-4ee6-a2e9-d32a3ed5c626','pump-dry-fa3ce511-3f30-4170-9fed-c68eb98a897e',87,'PUMP_HOME','{"pump":"P1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('8eb71105-aa65-4356-a35a-96c4c8b5ddec','pump-dry-fa3ce511-3f30-4170-9fed-c68eb98a897e',87,'PUMP_MOVE_ABSOLUTE_STEPS','{"pump":"P1","target_steps":20500}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('c64500b3-82b3-4fb4-bffc-78dd00ef0662','pump-dry-fa3ce511-3f30-4170-9fed-c68eb98a897e',87,'PUMP_HOME','{"pump":"P1"}','FAILED',NULL,'PUMP_MOTION_TIMEOUT',1);
COMMIT;
