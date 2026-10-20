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
INSERT INTO "arduino_command_journal" VALUES('d547861a-a017-40b1-b304-a43693229d16','p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf',85,'VALVE_HOME','{"valve":"V1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('c938d808-00e9-4e3a-9f23-378c84610bd0','p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf',85,'VALVE_HOME','{"valve":"V2"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('dff76eb8-a9d2-4f25-bb5e-bd6539e960ed','p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf',85,'VALVE_HOME','{"valve":"V4"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('4df9534f-1fa2-4e18-aa86-0e139bb96f34','p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf',85,'VALVE_HOME','{"valve":"V6"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('0bfb7055-66be-52df-82d5-28a5c3594e2f','p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf',85,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V6"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('c8374401-fdca-5468-b010-90cdd6832944','p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf',85,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('1e9f5f70-abfd-511a-9743-2162bb116d32','p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf',85,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V2"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('360c7733-bca9-5e3e-85e2-8277e972a897','p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf',85,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('2f1e7b3d-ee5d-552d-8eb4-83fb234e36b3','p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf',85,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('9b38de8d-ff6f-5a80-910e-4e8d0cb8acb8','p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf',85,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('8ea2751e-387b-5098-9c27-6f008ef006a6','p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf',85,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V4"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('d6663d6b-1d94-53ab-afc0-dc906cdd0a00','p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf',85,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V6"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('1b773678-e55f-5907-8480-09cbdca1b1ea','p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf',85,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('e04c0c0b-fd10-55e2-ad2c-e4e14bf3ba82','p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf',85,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('c52c3257-1a1c-5c8f-988f-c3bbf9826048','p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf',85,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V4"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('b176c4da-7a35-5891-a0f9-202bea7ab997','p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf',85,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('e974b9e3-83f2-5b29-91c0-5ca9f1947758','p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf',85,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V1"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('9a23e075-f1d7-57d1-8254-cacdda4cfdf0','p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf',85,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V2"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('2bd04dfa-f01e-525c-9c52-e9f908212f4d','p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf',85,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V2"}','COMPLETED','{}',NULL,1);
COMMIT;
