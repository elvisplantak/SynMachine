BEGIN TRANSACTION;
CREATE TABLE hardware_owner (
        slot INTEGER PRIMARY KEY CHECK(slot=1), sequence_id TEXT
    );
INSERT INTO "hardware_owner" VALUES(1,NULL);
CREATE TABLE hardware_sequences (
        sequence_id TEXT PRIMARY KEY NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('ACTIVE', 'BLOCKED', 'COMPLETED'))
    );
INSERT INTO "hardware_sequences" VALUES('service.arduino.cd73e48e-3d56-4d59-8486-779caaba9cac','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('sf-mixer-recheck-f64b3230-0085-4ba3-88a4-91c657f2b423','COMPLETED');
CREATE TABLE ownership_identity (id TEXT NOT NULL);
INSERT INTO "ownership_identity" VALUES('6fe0c940-65f4-46ff-9f4e-c0b9536d9ffc');
COMMIT;
