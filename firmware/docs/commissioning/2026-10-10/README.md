# SF mixer cable-repair recheck — 2026-10-10

User requested only this test today and corrected yesterday's physical SF mixer
observation: the motor cable was damaged and the mixer had not rotated. The user
reports cable repaired today. Boot94 full physical mixing acceptance is withdrawn;
original confirmation retained as history, raw journals/SQL/software outcomes intact.

Fresh user confirmation: empty SF, element free in existing direction, motor power
ON. Authorized scope: SF_MIXER_SET_STATE false -> true -> wait 3 s -> false.
Existing DIR=LOW/500 pulses per second profile; no other actuator, upload, reconnect,
retry or production activation. Existing Serial, durable executor, HardwareOwnership,
OwnedHardware required STOP followup and timer reused. Default preview opens no port;
real execution requires conditions-confirmed and RUN_BLOCK before opening USB.

Verification: 6 new fake checks plus existing shared ownership suite, 44 passed.
Checks cover durable intent before send, ownership through the timed interval,
required STOP on START/wait failure, retained BLOCKED owner and no-port cancellation.
Three initial existing socket tests failed only in sandbox; identical escalated suite
passed. No firmware code change; firmware remains e2e9d3c, no rebuild/upload needed.

Boot96: all 3 commands COMPLETED, 3 s timed wait, 2 completed owned sequences,
owner idle, exit0, connection closed. The user reports abnormal physical operation;
physical test NOT accepted: twitching and buzzing with an unpleasant sound.
User switched motor power OFF. Root cause not established; no repeat or further
movement attempted. Bundle:
sf-mixer-recheck-1aae57ee-02d8-48fc-96c9-8952a9490f35/ contains events.jsonl,
commands.sql, owner.sql and result-verification.json; SQLite originals retained locally.
Runner and fake-check snapshots adjacent. Command completion proves applied GPIO
profile, not sensor-measured rotation, RPM, mixing quality or wet acceptance.
A separate successful recheck cannot retroactively establish boot94 physical mixing.
