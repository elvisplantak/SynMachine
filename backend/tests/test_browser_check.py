import json
import os
import subprocess
import sys

import pytest

from app.hardware.owned_startup_inspection import inspect_owned_startup, StartupInspectionError
from app.hardware.arduino_serial import ArduinoSerialClient
from app.hardware.sf_bottom_valve import DynamixelSdkSession
from tests.browser_check import build_profile, load_bundle
from tests.test_api import ApiClient
from tests.test_owned_application_api import NOW, COMMAND, PREFIX, payload, wait_idle, maintenance


@pytest.fixture(autouse=True)
def fake_only(monkeypatch):
    monkeypatch.delenv("LABFORGE_ARDUINO_PORT", raising=False)
    monkeypatch.delenv("LABFORGE_SF_BOTTOM_VALVE_PORT", raising=False)

    def forbidden(*args, **kwargs):
        pytest.fail("browser profile attempted a real hardware transport")
    monkeypatch.setattr(ArduinoSerialClient, "_open_port", forbidden)
    monkeypatch.setattr(DynamixelSdkSession, "__init__", forbidden)


def quick_payload(run_id="browser-run"):
    data = payload(run_id)
    data["configuration"].update(reaction_duration_seconds="0.01", delay_between_additions_seconds="0.01")
    data["execution_settings"].update(sf_mixing_duration_seconds="0.01", sf_settling_duration_seconds="0.01",
        fraction_count=1, fraction_duration_seconds="0.01")
    return data


def start(client, run_id="browser-run"):
    response = client.post(PREFIX + "/runs", json=quick_payload(run_id))
    assert response.status_code == 200, response.text
    response = client.post(PREFIX + f"/runs/{run_id}/start", json=COMMAND)
    assert response.status_code == 202, response.text


def test_import_is_inert_even_with_live_port_environment(tmp_path):
    code = "import sys; import tests.browser_check; assert 'app.main' not in sys.modules"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
        env={**os.environ, "LABFORGE_ARDUINO_PORT": "must-not-open", "LABFORGE_SF_BOTTOM_VALVE_PORT": "must-not-open"})
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name", ["LABFORGE_ARDUINO_PORT", "LABFORGE_SF_BOTTOM_VALVE_PORT"])
def test_live_port_environment_is_rejected_before_creating_state(tmp_path, monkeypatch, name):
    monkeypatch.setenv(name, "must-not-open")
    directory = tmp_path / "state"
    with pytest.raises(ValueError, match="unset"):
        build_profile(directory)
    assert not directory.exists()


def test_browser_profile_full_run_preserves_events_across_restart(tmp_path):
    directory = tmp_path / "state"
    app, _ = build_profile(directory, command_delay=0)
    with ApiClient(app, lifespan="on") as client:
        start(client)
        assert wait_idle(client)["error"] is None
        events = client.get(PREFIX + "/runs/browser-run/events").json()
        assert client.get(PREFIX + "/runs/browser-run").json()["status"] == "COMPLETED"
    bundle = load_bundle(directory)
    evidence = bundle.execution_path.read_bytes()
    app, execution = build_profile(directory, command_delay=0)
    with ApiClient(app, lifespan="on") as client:
        assert execution.bundle == bundle
        assert bundle.execution_path.read_bytes() == evidence
        assert client.get(PREFIX + "/runs/browser-run/events").json() == events
        start(client, "browser-second")
        assert wait_idle(client)["error"] is None


def test_fault_profile_retains_owner_and_restart_requires_recovery_flush(tmp_path):
    directory = tmp_path / "state"
    app, execution = build_profile(directory, command_delay=0, fault_command=1)
    with ApiClient(app, lifespan="on") as client:
        start(client)
        status = wait_idle(client)
        assert "injected fake transport failure" in status["error"] and status["retained_owner_id"]
    evidence = execution.bundle.execution_path.read_bytes()
    app, execution = build_profile(directory, command_delay=0)
    with ApiClient(app, lifespan="on") as client:
        assert execution.bundle.execution_path.read_bytes() == evidence
        assert client.get(PREFIX + "/machine").json()["state"] == "RECOVERY_REQUIRED"
        assert client.post(PREFIX + "/runs", json=quick_payload("blocked")).status_code == 409
        maintenance(client, "RECOVERY", "browser-run")
        recovered = wait_idle(client)
        assert recovered["error"] is None
        assert recovered["retained_owner_id"] == status["retained_owner_id"]
        assert client.post(PREFIX + "/runs", json=quick_payload("blocked")).status_code == 409
    evidence = execution.bundle.execution_path.read_bytes()
    app, execution = build_profile(directory, command_delay=0)
    with ApiClient(app, lifespan="on") as client:
        restarted = client.get(PREFIX + "/execution").json()
        assert restarted["operation"] is None
        assert restarted["retained_owner_id"] == recovered["retained_owner_id"]
        assert client.get(PREFIX + "/machine").json()["state"] == "FLUSH_REQUIRED"
        assert execution.bundle.execution_path.read_bytes() == evidence
        assert client.post(PREFIX + "/runs", json=quick_payload("blocked")).status_code == 409
        maintenance(client, "FLUSH", "browser-run")
        assert "continuity" in wait_idle(client)["error"]
        assert execution.bundle.execution_path.read_bytes() == evidence
        maintenance(client, "RECOVERY", "browser-run")
        assert wait_idle(client)["error"] is None
        maintenance(client, "FLUSH", "browser-run")
        flushed = wait_idle(client)
        assert flushed["error"] is None and flushed["retained_owner_id"] is None
    app, _ = build_profile(directory, command_delay=0)
    with ApiClient(app, lifespan="on") as client:
        assert client.get(PREFIX + "/machine").json()["state"] == "READY"
        assert client.get(PREFIX + "/execution").json()["retained_owner_id"] is None
        start(client, "after-browser-recovery")
        assert wait_idle(client)["error"] is None


def test_unknown_or_partial_state_is_never_reset(tmp_path):
    (tmp_path / "foreign.db").write_bytes(b"preserve")
    with pytest.raises(ValueError, match="nothing will be reset"):
        load_bundle(tmp_path)
    assert list(tmp_path.iterdir()) == [tmp_path / "foreign.db"]
    assert (tmp_path / "foreign.db").read_bytes() == b"preserve"


@pytest.mark.parametrize("problem", ["missing", "foreign", "symlink"])
def test_marked_state_is_not_recreated_or_rebound(tmp_path, problem):
    bundle = load_bundle(tmp_path)
    manifest = tmp_path / "browser-check.json"
    if problem == "missing":
        bundle.execution_path.rename(tmp_path / "preserved-execution.db")
    elif problem == "foreign":
        data = json.loads(manifest.read_text())
        data["profile"] = "foreign"
        manifest.write_text(json.dumps(data))
    else:
        saved = tmp_path / "preserved-execution.db"
        bundle.execution_path.rename(saved)
        bundle.execution_path.symlink_to(saved)
    before = manifest.read_bytes()
    with pytest.raises(ValueError):
        load_bundle(tmp_path)
    assert manifest.read_bytes() == before


def test_changed_marker_cannot_rebind_database_identity(tmp_path):
    bundle = load_bundle(tmp_path)
    before = bundle.ownership_path.read_bytes()
    manifest = tmp_path / "browser-check.json"
    data = json.loads(manifest.read_text())
    data["ownership_id"] = "00000000-0000-0000-0000-000000000000"
    manifest.write_text(json.dumps(data))
    _, execution = build_profile(tmp_path, command_delay=0)
    with pytest.raises(StartupInspectionError):
        execution.start(NOW)
    assert bundle.ownership_path.read_bytes() == before
    assert inspect_owned_startup(bundle).owner_id is None
