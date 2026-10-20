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
INSERT INTO "arduino_command_journal" VALUES('d289fd6c-42a9-4374-94e1-acc149239df7','valve-park-dry-88a0ba90-c9df-4aab-9929-28d27acc954a',91,'VALVE_HOME','{"valve":"V1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('826b8c5d-c14f-449f-b076-c149f6618c60','valve-park-dry-88a0ba90-c9df-4aab-9929-28d27acc954a',91,'VALVE_HOME','{"valve":"V2"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('c6300d51-53d0-4aa3-98aa-1d72d21cf2c2','valve-park-dry-88a0ba90-c9df-4aab-9929-28d27acc954a',91,'VALVE_HOME','{"valve":"V4"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('ba8a9d50-9fa6-411b-83c4-4328c2a2f430','valve-park-dry-88a0ba90-c9df-4aab-9929-28d27acc954a',91,'VALVE_HOME','{"valve":"V6"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('b508fcd2-3979-4438-8a08-1c5c3770b2cf','valve-park-dry-88a0ba90-c9df-4aab-9929-28d27acc954a',91,'VALVE_HOME','{"valve":"V3"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('1f69b802-c86a-4c7d-8885-98254437e3b5','valve-park-dry-88a0ba90-c9df-4aab-9929-28d27acc954a',91,'VALVE_HOME','{"valve":"V7"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('06476d59-4e3f-447a-9a55-9aecafe25ce2','valve-park-dry-88a0ba90-c9df-4aab-9929-28d27acc954a',91,'VALVE_HOME','{"valve":"V8"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('aeb861fc-9b64-4306-88d1-48ca82c38011','valve-park-dry-88a0ba90-c9df-4aab-9929-28d27acc954a',91,'VALVE_HOME','{"valve":"V5"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('ba23b8ba-d751-40eb-8413-e817e77d1ad7','valve-park-dry-88a0ba90-c9df-4aab-9929-28d27acc954a',91,'VALVE_SET_POSITION','{"position_degrees":5,"valve":"V1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('45a3be51-a19f-453b-8d23-8c5b7b489e2a','valve-park-dry-88a0ba90-c9df-4aab-9929-28d27acc954a',91,'VALVE_SET_POSITION','{"position_degrees":5,"valve":"V2"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('83be682c-2919-42c6-ab54-55685c05f64c','valve-park-dry-88a0ba90-c9df-4aab-9929-28d27acc954a',91,'VALVE_SET_POSITION','{"position_degrees":5,"valve":"V4"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('5df74559-11dc-4b65-881e-99822cd64fb3','valve-park-dry-88a0ba90-c9df-4aab-9929-28d27acc954a',91,'VALVE_SET_POSITION','{"position_degrees":5,"valve":"V6"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('2811545e-fe26-4e4b-beb3-cc0a3d7d6d54','valve-park-dry-88a0ba90-c9df-4aab-9929-28d27acc954a',91,'VALVE_SET_POSITION','{"position_degrees":5,"valve":"V3"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('e59f208b-3b8b-497e-98c9-6fbeeb493a17','valve-park-dry-88a0ba90-c9df-4aab-9929-28d27acc954a',91,'VALVE_SET_POSITION','{"position_degrees":5,"valve":"V7"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('680474dd-28a2-4749-8cc8-3deaad7c44f3','valve-park-dry-88a0ba90-c9df-4aab-9929-28d27acc954a',91,'VALVE_SET_POSITION','{"position_degrees":5,"valve":"V8"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('38628a0c-48bb-4c41-b80e-68a94e8e4ee5','valve-park-dry-88a0ba90-c9df-4aab-9929-28d27acc954a',91,'VALVE_SET_POSITION','{"position_degrees":5,"valve":"V5"}','COMPLETED','{}',NULL,1);
COMMIT;
