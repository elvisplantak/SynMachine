"""Live entry point tested only with fake Serial/DYNAMIXEL factories."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import socket
from time import monotonic, sleep

import pytest

from app.hardware.operator_current_input import OperatorReferenceInput
from app.live_execution import build_live_app, load_bundle, load_profile, main, provision, _credential
from tests.test_adapter_application import ConnectingPort
from tests.test_api import ApiClient
from tests.test_owned_application_api import COMMAND, PREFIX, wait_idle
from tests.test_prepared_adapter_execution import FollowingSession
from tests.test_recipes import definition, readiness

KEY = "test-only-live-entry-point-credential-123456"
PROFILE = Path(__file__).parents[1] / "docs/LIVE_RECIPES_PROFILE.json"


def refs():
    return OperatorReferenceInput(
        evidence_note="Fresh fake fixture only; no real observation", observed_now_confirmed=True,
        pumps=[dict(pump_id=pump, position_steps=20500) for pump in ("P1", "P2")],
        valve_positions=[dict(valve=f"V{i}", position_degrees=0) for i in range(1, 9)],
        reactor_mixer_running=False, sf_mixer_running=False, sf_bottom_valve="CLOSED",
        column_position_degrees=4, carousel_position=1,
    )


def await_input(execution):
    end = monotonic() + 3
    while monotonic() < end:
        challenge = execution.status().current_input
        if challenge is not None:
            return challenge
        sleep(.002)
    raise AssertionError("Fresh operator challenge not exposed")


def fake_app(tmp_path, **options):
    profile = load_profile(PROFILE)
    bundle = provision(tmp_path / "live-state", profile)
    ports, sessions = [], []

    def port(configuration):
        value = ConnectingPort()
        ports.append(value)
        if options.get("before_command"):
            value.before_command = options["before_command"]
        return value

    def sf(configuration):
        value = FollowingSession()
        from app.hardware.sf_bottom_valve import REGISTERS
        value.values[REGISTERS["torque_enable"]] = 0
        sessions.append(value)
        return value

    app, execution = build_live_app(profile, bundle, operator="Offline operator", credential=KEY,
        arduino_port_factory=port, sf_session_factory=sf,
        arduino_sleep=lambda _: None, sf_sleep=lambda _: None)
    return app, execution, bundle, ports, sessions


def test_profile_and_provision_are_inert_and_preserve_bound_history(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("A device was opened during offline preparation")
    import serial
    import app.hardware.sf_bottom_valve as sf
    monkeypatch.setattr(serial, "Serial", forbidden)
    monkeypatch.setattr(sf, "DynamixelSdkSession", forbidden)
    assert main(["validate", "--profile", str(PROFILE)]) is None
    profile = load_profile(PROFILE)
    directory = tmp_path / "state"
    bundle = provision(directory, profile)
    assert len(_credential(directory)) >= 32
    assert (directory / "operator.key").stat().st_mode & 0o077 == 0
    assert load_bundle(directory, profile) == bundle
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    with pytest.raises(FileExistsError):
        provision(directory, profile)
    changed = profile.model_copy(update={"profile_id": "different"})
    with pytest.raises(ValueError, match="identity mismatch"):
        load_bundle(directory, changed)
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before


@pytest.mark.parametrize("problem", ["duplicate", "fake-port", "same-device", "missing-setting", "maintenance-mismatch"])
def test_invalid_profile_rejected_before_provision(tmp_path, problem):
    data = json.loads(PROFILE.read_text())
    if problem == "fake-port":
        data["arduino"]["port"] = "/dev/fake"
    elif problem == "same-device":
        data["sf"]["port"] = data["arduino"]["port"]
    elif problem == "missing-setting":
        del data["sf"]["position_tolerance"]
    elif problem == "maintenance-mismatch":
        from tests.test_adapter_configuration import profile
        data["flush_plan"] = profile().flush_plan.model_dump(mode="json")
    path = tmp_path / "invalid.json"
    path.write_text('{"profile_id":"first",' + json.dumps(data)[1:] if problem == "duplicate" else json.dumps(data))
    with pytest.raises(ValueError):
        load_profile(path)
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("problem", ["missing-connect", "occupied-port", "legacy-environment", "corrupt-state"])
def test_serve_refuses_invalid_setup_without_device_open(tmp_path, monkeypatch, problem):
    from app import live_execution
    monkeypatch.setattr(live_execution, "build_live_app", lambda *a, **kw: pytest.fail("Unexpected live construction"))
    directory = tmp_path / "state"
    provision(directory, load_profile(PROFILE))
    args = ["serve", "--profile", str(PROFILE), "--state-dir", str(directory), "--operator", "Elvis"]
    listener = socket.socket()
    try:
        if problem != "missing-connect":
            args.append("--connect-real-devices")
        if problem == "occupied-port":
            listener.bind(("127.0.0.1", 0))
            args += ["--port", str(listener.getsockname()[1])]
        elif problem == "legacy-environment":
            monkeypatch.setenv("LABFORGE_ARDUINO_PORT", "/dev/forbidden")
        elif problem == "corrupt-state":
            (directory / "live-state.json").write_text('{"profile":"fake"}')
        with pytest.raises(SystemExit):
            main(args)
    finally:
        listener.close()


def test_live_composition_recipe_requires_fresh_input_and_repeats_without_replay(tmp_path):
    app, execution, bundle, ports, sessions = fake_app(tmp_path)
    assert ports == sessions == []
    with ApiClient(app, lifespan="on") as client:
        assert [json.loads(value)["type"] for value in ports[0].writes] == ["HELLO"]
        status = client.get(PREFIX + "/execution").json()
        assert status["transport_mode"] == "LIVE" and status["profile_id"] == "labforge-supervised-recipes-v1"
        assert status["maintenance_actions"] == [] and status["flow_activity"] is None
        value = definition([
            {"kind": "ADD", "source": "S", "volume_ml": "2"},
            {"kind": "TRANSFER", "route": "REACTOR_TO_SF", "volume_ml": "2"},
            {"kind": "SF_MIX", "duration_seconds": "0.001"},
            {"kind": "SF_SETTLE", "duration_seconds": "0.001"},
            {"kind": "TRANSFER", "route": "SF_TO_COLUMN", "volume_ml": "2"},
            {"kind": "COLLECT", "fraction_count": 2, "fraction_duration_seconds": "0.001"},
        ])
        saved = client.post(PREFIX + "/recipes", json={"definition": value.model_dump(mode="json")}).json()
        with ThreadPoolExecutor() as pool:
            future = pool.submit(client.post, PREFIX + "/machine/initialize", json=COMMAND)
            challenge = await_input(execution)
            assert len(ports[0].writes) == 1
            declared = client.post(PREFIX + f"/execution/current-input/{challenge.request_id}",
                json=refs().model_dump(mode="json"), headers={"Authorization": "Bearer " + KEY})
            # Use the actual operator declaration endpoint, not a test-only callback.
            assert declared.status_code == 200, declared.text
            assert future.result(3).status_code == 200
        for number in range(2):
            response = client.post(PREFIX + f"/recipes/{saved['recipe_id']}/execute", json={
                "run_id": f"live-fixture-{number}", "expected_revision": saved["revision"],
                "expected_content_digest": saved["content_digest"],
                "readiness": readiness().model_dump(mode="json"), **COMMAND})
            assert response.status_code == 202, response.text
            if number == 0:
                challenge = await_input(execution)
                assert len(ports[0].writes) == 1
                execution.submit_current_input(challenge.request_id, refs(), KEY)
            wait_idle(client)
            run = client.get(PREFIX + f"/runs/live-fixture-{number}").json()
            assert run["status"] == "COMPLETED", execution.status()
            assert run["recipe"] == saved
        assert execution.status().retained_owner_id is None
        assert execution.status().flow_activity is None
        assert sessions
    restarted_app, restarted = build_live_app(load_profile(PROFILE), load_bundle(tmp_path / "live-state", load_profile(PROFILE)),
        operator="Offline operator", credential=KEY, arduino_port_factory=lambda _: ConnectingPort(),
        sf_session_factory=lambda _: pytest.fail("SF opened on restart"), arduino_sleep=lambda _: None)
    with ApiClient(restarted_app, lifespan="on") as client:
        assert restarted.status().current_input is None and restarted.status().flow_activity is None
        assert restarted.status().retained_owner_id is None
        assert client.get(PREFIX + "/recipes").json() == [saved]


def test_stop_keeps_required_maintenance_without_fabricated_plan(tmp_path):
    app, execution, _, ports, _ = fake_app(tmp_path)
    with ApiClient(app, lifespan="on") as client:
        # Initialize without commands, through a fresh attributable declaration.
        with ThreadPoolExecutor() as pool:
            pending = pool.submit(client.post, PREFIX + "/machine/initialize", json=COMMAND)
            challenge = await_input(execution)
            execution.submit_current_input(challenge.request_id, refs(), KEY)
            assert pending.result(3).status_code == 200
        saved = client.post(PREFIX + "/recipes", json={"definition": definition([
            {"kind": "WAIT", "duration_seconds": "30"}]).model_dump(mode="json")}).json()
        result = client.post(PREFIX + f"/recipes/{saved['recipe_id']}/execute", json={
            "run_id": "stop-fixture", "expected_revision": 1, "expected_content_digest": saved["content_digest"],
            "readiness": readiness().model_dump(mode="json"), **COMMAND})
        assert result.status_code == 202, result.text
        challenge = await_input(execution)
        execution.submit_current_input(challenge.request_id, refs(), KEY)
        end = monotonic() + 3
        while monotonic() < end:
            machine = client.get(PREFIX + "/machine").json()
            if machine["active_execution"] and machine["active_execution"]["start_committed_at"]:
                break
            sleep(.002)
        assert client.post(PREFIX + "/runs/stop-fixture/stop/request", json=COMMAND).status_code == 200
        wait_idle(client)
        assert client.get(PREFIX + "/machine").json()["state"] == "FLUSH_REQUIRED"
        assert execution.status().retained_owner_id is not None
        before = len(ports[0].writes)
        from app.demo.maintenance_plan import MaintenanceKind
        from app.hardware.simulated_p1_runner import SimulationBlocked
        with pytest.raises(SimulationBlocked, match="explicit maintenance plan"):
            execution.start_maintenance(MaintenanceKind.FLUSH, "stop-fixture", readiness(), COMMAND["occurred_at"])
        assert len(ports[0].writes) == before
        maintenance_body = {"operator": "Offline operator", "evidence_note": "Fresh fixture statement",
            "waste_air_gap_verified": True, "switching_sequences_verified": True,
            "working_calibrations_verified": True, "reactor_mixer_stopped": True,
            "carousel_manually_aligned": True}
        refused = client.post(PREFIX + "/machine/flush/start", json={
            "run_id": "stop-fixture", "readiness": maintenance_body, **COMMAND})
        assert refused.status_code == 409, refused.text
        assert len(ports[0].writes) == before


@pytest.mark.parametrize("problem", ["fake-marker", "symlink-marker", "permissive-key", "missing-database"])
def test_live_state_and_private_credential_refuse_unsafe_reuse(tmp_path, problem):
    profile = load_profile(PROFILE)
    directory = tmp_path / "state"
    bundle = provision(directory, profile)
    if problem == "fake-marker":
        (directory / "live-state.json").write_text('{"profile":"labforge-browser-check-fake-v1"}')
    elif problem == "symlink-marker":
        backup = directory / "saved-marker.json"
        (directory / "live-state.json").rename(backup)
        (directory / "live-state.json").symlink_to(backup)
    elif problem == "permissive-key":
        (directory / "operator.key").chmod(0o644)
    else:
        bundle.lifecycle_path.unlink()
    with pytest.raises((ValueError, OSError)):
        if problem == "permissive-key":
            _credential(directory)
        else:
            load_bundle(directory, profile)
    if problem == "missing-database":
        assert not bundle.lifecycle_path.exists()


def test_live_arduino_uses_exclusive_port_without_changing_serial_timing(monkeypatch):
    import serial
    from app.live_execution import _exclusive_port
    calls = []
    monkeypatch.setattr(serial, "Serial", lambda **kwargs: calls.append(kwargs) or "fake-serial")
    configuration = load_profile(PROFILE).arduino.adapter_configuration()
    assert _exclusive_port(configuration) == "fake-serial"
    assert calls == [dict(port=configuration.port, baudrate=115200,
                         timeout=.05, write_timeout=1.0, exclusive=True)]
