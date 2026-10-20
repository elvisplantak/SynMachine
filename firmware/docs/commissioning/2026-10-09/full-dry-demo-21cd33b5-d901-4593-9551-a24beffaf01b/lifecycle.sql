BEGIN TRANSACTION;
CREATE TABLE demo_runs (
    run_id TEXT NOT NULL PRIMARY KEY,
    snapshot_json TEXT NOT NULL,
    event_sequence INTEGER NOT NULL,
    status TEXT NOT NULL,
    phase TEXT NOT NULL
);
CREATE TABLE domain_events (
    aggregate_type TEXT NOT NULL CHECK (aggregate_type IN ('RUN', 'MACHINE')),
    aggregate_id TEXT NOT NULL,
    event_sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    run_status TEXT,
    run_phase TEXT,
    machine_state TEXT,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (aggregate_type, aggregate_id, event_sequence)
);
CREATE TABLE machine_snapshot (
    singleton_id INTEGER NOT NULL PRIMARY KEY CHECK (singleton_id = 1),
    snapshot_json TEXT NOT NULL,
    event_sequence INTEGER NOT NULL,
    state TEXT NOT NULL
);
CREATE TABLE offline_lifecycle_identity (id TEXT, simulation_id TEXT);
INSERT INTO "offline_lifecycle_identity" VALUES('72b6ebe7-4d38-44dd-878f-3372e26b2bb6','8e00164b-e6ab-4f21-a4ec-b5aae2b29bc2');
COMMIT;
