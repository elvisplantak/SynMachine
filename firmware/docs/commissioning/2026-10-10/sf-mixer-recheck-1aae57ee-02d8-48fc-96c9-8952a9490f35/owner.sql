BEGIN TRANSACTION;
CREATE TABLE hardware_owner (
        slot INTEGER PRIMARY KEY CHECK(slot=1), sequence_id TEXT
    );
INSERT INTO "hardware_owner" VALUES(1,NULL);
CREATE TABLE hardware_sequences (
        sequence_id TEXT PRIMARY KEY NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('ACTIVE', 'BLOCKED', 'COMPLETED'))
    );
INSERT INTO "hardware_sequences" VALUES('service.arduino.05fd3dcb-7789-46ef-bb09-5a6363522bb8','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('sf-mixer-recheck-bd9fc153-aaf4-44b1-93ca-bf1ed7ebed61','COMPLETED');
CREATE TABLE ownership_identity (id TEXT NOT NULL);
INSERT INTO "ownership_identity" VALUES('df91ef84-658e-4b08-89a7-d5d3361836bc');
COMMIT;
