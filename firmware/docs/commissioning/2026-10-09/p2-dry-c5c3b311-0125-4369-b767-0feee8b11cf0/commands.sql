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
INSERT INTO "arduino_command_journal" VALUES('b10cdc55-bd2d-4d56-a1e9-a73bcc1965d4','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_HOME','{"valve":"V3"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('052f3192-8b77-47a7-a8fc-0bc72eb47b28','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_HOME','{"valve":"V7"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('0670355e-1b23-4387-a1ba-9572dfbe3f35','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_HOME','{"valve":"V8"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('3eaebce0-9070-4982-a027-5aadf910774f','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_HOME','{"valve":"V5"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('3771b9ab-0e8d-515a-8701-4d989217e70b','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V3"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('d0cfe04f-600b-56cb-823c-6d6c0b4b72ae','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V7"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('46c9077f-d42b-570d-bf7f-32bc6b45eeb7','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V3"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('9408d4fe-3e2b-5e48-b8f2-2a7e0d05057d','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V3"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('8ed253b8-d842-52e1-b39f-9ae9b7999f7b','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V3"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('1dbf7e2c-ad25-5e5d-8a05-2eaa32d65d48','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V8"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('b0e9aa69-fd56-58d1-96f3-fc091619b02c','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V7"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('731b9734-7c47-5767-8200-feef4c360929','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V5"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('6fbd336e-b714-51f9-8961-60454e9c3062','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V8"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('61ceaa31-600f-520a-a572-be11ba8fe5c9','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V8"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('db244b57-e9c3-562a-a88b-dec633d64c36','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V8"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('7d6a0ad6-419e-57c5-9058-78109a3da6f6','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V3"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('ef837bb3-28d7-577a-b923-e3983dc2e9f1','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V7"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('23db4af2-f01a-5d36-a802-beac2359d58d','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V3"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('c951d8f9-94ab-5b05-b52b-a1b99631b8f1','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V5"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('8fdf26c8-e601-54aa-b900-a838e60203ab','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V7"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('e8a99b24-de2d-5055-8ee4-6045bf0b699f','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V3"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('52c891ca-94d2-5cd3-84c8-1d1caf61e03d','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V5"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('0670a4c6-e98c-5205-9ffb-d5f4d7ca13eb','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V3"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('728b810a-3ed1-540d-82b5-7aa9a6166e20','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":180,"valve":"V5"}','COMPLETED','{}',NULL,1);
INSERT INTO "arduino_command_journal" VALUES('7471bc50-79eb-5cdb-8e62-a1493e1ff975','p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0',86,'VALVE_SET_POSITION','{"position_degrees":90,"valve":"V3"}','COMPLETED','{}',NULL,1);
COMMIT;
