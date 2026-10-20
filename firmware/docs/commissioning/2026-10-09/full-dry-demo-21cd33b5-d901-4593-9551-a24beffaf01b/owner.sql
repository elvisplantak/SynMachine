BEGIN TRANSACTION;
CREATE TABLE hardware_owner (
        slot INTEGER PRIMARY KEY CHECK(slot=1), sequence_id TEXT
    );
INSERT INTO "hardware_owner" VALUES(1,'dry-bootstrap-probe');
CREATE TABLE hardware_sequences (
        sequence_id TEXT PRIMARY KEY NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('ACTIVE', 'BLOCKED', 'COMPLETED'))
    );
INSERT INTO "hardware_sequences" VALUES('dry-bootstrap-probe','BLOCKED');
CREATE TABLE ownership_identity (id TEXT NOT NULL);
INSERT INTO "ownership_identity" VALUES('1c587783-414d-46f8-9996-424c580c3f0b');
COMMIT;
