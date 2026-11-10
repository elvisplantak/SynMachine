"""XDL 2 interchange: strict semantics, hostile XML and the existing fake executor."""

from decimal import Decimal
from pathlib import Path
import os
import sqlite3
import subprocess
import sys

import pytest

from app.main import create_app
from app.recipes.models import RecipeDefinition, recipe_content_digest
from app.recipes.xdl import XdlError, XdlImportRequest, export_xdl, import_xdl, inspect_xdl
from tests.test_api import ApiClient
from tests import test_owned_application_api as owned_tests
from tests.test_owned_application_api import wait_idle
from tests.test_owned_offline_runtime import bundle as bundle
from tests.test_recipes import execute, readiness, save


XML = '''<?xdl version="2.0.0"?>
<XDL><Synthesis id="Water demo"><Metadata description="Fake-only example"/>
<Hardware><Component id="r" type="reactor"/><Component id="sf" type="separator"/>
<Component id="col" type="column"/></Hardware>
<Reagents><Reagent name="Blue"/><Reagent name="Purple"/><Reagent name="Water"/></Reagents>
<Procedure><Add reagent="Water" vessel="r" volume="1000 uL"/><Wait time="0.01 s"/>
</Procedure></Synthesis></XDL>'''
BINDINGS = {"reagents": {"B1": "Blue", "B2": "Purple", "S": "Water"},
            "vessels": {"REACTOR": "r", "SF": "sf", "COLUMN": "col"}}
base_assembly = owned_tests.assembly


def imported(xml=XML, **overrides):
    return import_xdl(XdlImportRequest(xml=xml, **(BINDINGS | overrides)))


@pytest.fixture
def assembly(base_assembly):
    base_assembly[1]._transport_mode = "FAKE"
    return base_assembly


def test_export_import_preserves_supported_recipe_and_escaped_text():
    definition = RecipeDefinition(name='Demo & "quotes"', description='A < B & C',
        sources={"B1": 'Blue & "ink"', "B2": "Purple", "S": "Water"}, steps=[
            {"kind": "ADD", "source": "B1", "volume_ml": "2.0"},
            {"kind": "ADD", "source": "B2", "volume_ml": "1.25"},
            {"kind": "TRANSFER", "route": "REACTOR_TO_SF", "volume_ml": "2.50"},
            {"kind": "WAIT", "duration_seconds": "1.5"},
            {"kind": "TRANSFER", "route": "SF_TO_COLUMN", "volume_ml": "2.50"},
        ])
    output = export_xdl(definition)
    assert output["content_digest"] == recipe_content_digest(definition)
    assert '&amp;' in output['xml'] and '&quot;' in output['xml']
    assert inspect_xdl(output["xml"])["reference_release"] == "2.1.0"
    result = import_xdl(XdlImportRequest(**{k: output[k] for k in ("xml", "reagents", "vessels")}))
    assert result == definition
    assert recipe_content_digest(result) == output["content_digest"]


@pytest.mark.parametrize("value,expected", [
    ("1 L", "1000"), ("1 ml", "1"), ("1 µL", "0.001"),
    ("1 μL", "0.001"), ("0.10000000000000000001 mL", "0.10000000000000000001"),
])
def test_volume_conversion_is_exact(value, expected):
    result = imported(XML.replace("1000 uL", value))
    assert result.steps[0].volume_ml == Decimal(expected)


@pytest.mark.parametrize("value,expected", [("0.5 min", "30"), ("1 h", "3600"), ("2 seconds", "2")])
def test_time_conversion_is_exact(value, expected):
    assert imported(XML.replace("0.01 s", value)).steps[1].duration_seconds == Decimal(expected)


@pytest.mark.parametrize("value", ["-1 mL", "0 mL", "NaN mL", "Infinity mL", "1e9 mL",
    "1", "1 kg", "1 mmol", "all", "${amount} mL", "1/2 mL", "1000001 mL"])
def test_unsupported_quantities_are_rejected(value):
    with pytest.raises(XdlError):
        imported(XML.replace("1000 uL", value))


@pytest.mark.parametrize("change", [
    '<HeatChill vessel="r" time="1 s" temp="20 C"/>',
    '<Stir vessel="sf" time="1 s"/>', '<RunColumn/>', '<Filter vessel="sf"/>',
    '<Repeat repeats="2"><Wait time="1 s"/></Repeat>', '<Async><Wait time="1 s"/></Async>',
    '<Reaction><Wait time="1 s"/></Reaction>',
])
def test_unsupported_operations_are_not_silently_dropped(change):
    xml = XML.replace('<Wait time="0.01 s"/>', change)
    with pytest.raises(XdlError):
        inspect_xdl(xml)


@pytest.mark.parametrize("change", [
    'mass="1 g"', 'amount="1 mmol"', 'stir="true"', 'time="10 s"',
    'stir_speed="250 rpm"', 'dropwise="true"', 'viscous="true"', 'purpose="dissolve"',
])
def test_add_does_not_ignore_requested_behavior(change):
    with pytest.raises(XdlError):
        imported(XML.replace('volume="1000 uL"', f'volume="1000 uL" {change}'))


@pytest.mark.parametrize("xml", [
    XML.replace('<Reagent name="Water"/>', '<Reagent name="Water" solid="true"/>'),
    XML.replace('<Reagent name="Water"/>', '<Reagent name="Water" temp="20 C"/>'),
    XML.replace('<Reagent name="Water"/>', '<Reagent name="Water"/><Reagent name="Water"/>'),
    XML.replace('<Component id="r" type="reactor"/>', '<Component id="r" type="reactor"/><Component id="r" type="reactor"/>'),
    XML.replace('<Metadata description="Fake-only example"/>', '<Metadata publication="source"/>'),
    XML.replace('<Procedure>', '<Parameters/><Procedure>'),
    XML.replace('<Procedure>', '<Variables/><Procedure>'),
    XML.replace('<Procedure>', '<Procedure/><Procedure>'),
    XML.replace('reagent="Water" vessel=', 'reagent="Missing" vessel='),
    XML.replace('vessel="r"', 'vessel="missing"'),
    XML.replace('<Wait time="0.01 s"/>', '<Wait time="1 s">ignored instruction</Wait>'),
    XML.replace('<XDL>', '<XDL xmlns="urn:unsupported">'),
    XML.replace('<Synthesis id="Water demo">', '<Synthesis graph_sha256="' + 'a' * 64 + '">'),
    XML.replace('<?xdl version="2.0.0"?>', '<?xdl version="0.5.0"?>'),
    XML.replace('<?xdl version="2.0.0"?>', '<?xdl version="2.1.0"?>'),
    XML.replace('<?xdl version="2.0.0"?>', '<?include file="unknown"?>'),
    XML.replace('<Procedure>', '<Procedure><?xdl version="2.0.0"?>'),
    XML.replace('<Reagent name="Water"/>', '<Reagent name="${water}"/>'),
])
def test_structure_declarations_and_version_fail_closed(xml):
    with pytest.raises(XdlError):
        inspect_xdl(xml)


@pytest.mark.parametrize("declaration", [
    '<!DOCTYPE XDL SYSTEM "file:///tmp/never-read">',
    '<!DOCTYPE XDL [<!ENTITY x SYSTEM "https://example.invalid/never-contact">]>',
    '<!DOCTYPE XDL [<!ENTITY x "expansion">]>',
])
def test_no_dtd_entities_or_external_resources(declaration):
    with pytest.raises(XdlError, match="DTDs"):
        inspect_xdl(XML.replace('<XDL>', declaration + '<XDL>'))


@pytest.mark.parametrize("xml", ["<XDL>" + " " * 131072,
    "<XDL>" + "Ž" * 70000, XML.replace('<Procedure>', '<Procedure>' + '<Wait time="1 s"/>' * 100),
    '<XDL>' * 9 + '</XDL>' * 9,
    XML.replace('<Procedure>', '<Procedure>' + '<Wait time="1 s"/>' * 520), '\ud800'])
def test_document_limits(xml):
    with pytest.raises(XdlError):
        inspect_xdl(xml)


def test_explicit_new_version_accepts_unwrapped_synthesis_but_not_ambiguous_legacy():
    xml = XML.replace('<XDL>', '').replace('</XDL>', '')
    assert inspect_xdl(xml)["step_count"] == 2
    with pytest.raises(XdlError):
        inspect_xdl(xml.replace('<?xdl version="2.0.0"?>', ''))


@pytest.mark.parametrize("override", [
    {"reagents": {}}, {"reagents": {"B1": "Water", "S": "Water"}},
    {"reagents": {"S": "missing"}}, {"vessels": {}},
    {"vessels": {"REACTOR": "sf"}}, {"vessels": {"REACTOR": "r", "SF": "r"}},
])
def test_explicit_unambiguous_bindings_are_required(override):
    with pytest.raises(XdlError):
        imported(**override)


def test_flow_and_route_validation_are_retained():
    transfer = '<Transfer from_vessel="r" to_vessel="sf" volume="2 mL"/>'
    with pytest.raises(ValueError, match="exceeds configured contents"):
        imported(XML.replace('<Wait time="0.01 s"/>', transfer))
    with pytest.raises(XdlError, match="route"):
        imported(XML.replace('<Wait time="0.01 s"/>', transfer.replace('to_vessel="sf"', 'to_vessel="r"')))


@pytest.mark.parametrize("step", [
    {"kind": "SF_MIX", "duration_seconds": "1"},
    {"kind": "SF_SETTLE", "duration_seconds": "1"},
    {"kind": "COLLECT", "fraction_count": 1, "fraction_duration_seconds": "1"},
])
def test_export_rejects_steps_without_an_exact_mapping(step):
    with pytest.raises(XdlError, match="no supported exact"):
        export_xdl(RecipeDefinition(name="Unsupported", steps=[step]))


@pytest.mark.parametrize("volume", ["1e99999999", "1e-99999999", "0." + "0" * 1000 + "1"])
def test_export_rejects_unbounded_decimals_before_expansion(volume):
    definition = RecipeDefinition(name="Large", steps=[{"kind": "ADD", "source": "S", "volume_ml": volume}])
    with pytest.raises(XdlError, match="range or precision"):
        export_xdl(definition)


def test_export_rejects_ambiguous_bottle_labels():
    definition = imported()
    definition = definition.model_copy(update={"sources": definition.sources.model_copy(update={"B1": "Water"})})
    with pytest.raises(XdlError, match="distinct"):
        export_xdl(definition)


def test_import_export_are_read_only_until_existing_save_review_execute(assembly, bundle):
    app, _, devices, _ = assembly
    with ApiClient(app, lifespan="on") as api:
        assert api.post('/api/v1/recipes/xdl/inspect', json={"xml": XML}).status_code == 200
        response = api.post('/api/v1/recipes/xdl/import', json={"xml": XML, **BINDINGS})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['preview']['calibrations_checked'] is True
        assert data['preview']['content_digest'] == recipe_content_digest(RecipeDefinition.model_validate(data['definition']))
        assert api.get('/api/v1/recipes').json() == []
        assert api.get('/api/v1/runs/existing-xdl-run').status_code == 404
        assert devices[0].calls == devices[0].sf_calls == []
        output = api.post('/api/v1/recipes/xdl/export', json={"definition": data['definition']})
        assert output.status_code == 200, output.text
        saved = save(api, RecipeDefinition.model_validate(data['definition']))
        assert devices[0].calls == []
        rejected = api.post(f"/api/v1/recipes/{saved['recipe_id']}/execute", json={
            "run_id": "existing-xdl-run", "expected_revision": 99,
            "expected_content_digest": saved['content_digest'], "readiness": readiness().model_dump(mode='json'),
            "occurred_at": "2026-11-10T10:00:00Z"})
        assert rejected.status_code == 409 and devices[0].calls == []
        accepted = execute(api, saved, run_id="existing-xdl-run")
        assert accepted.status_code == 202, accepted.text
        assert wait_idle(api)['error'] is None
        run = api.get('/api/v1/runs/existing-xdl-run').json()
        assert run['status'] == 'COMPLETED' and run['recipe_step_index'] == 2
        with sqlite3.connect(bundle.lifecycle_path) as db:
            assert db.execute('SELECT COUNT(*) FROM demo_runs').fetchone()[0] == 1


@pytest.mark.parametrize("mode", ['LIVE', 'UNSPECIFIED'])
@pytest.mark.parametrize("path,payload", [
    ('inspect', {"xml": XML}), ('import', {"xml": XML, **BINDINGS}),
    ('export', {"definition": imported().model_dump(mode='json')})])
def test_live_and_unknown_profiles_cannot_use_new_interchange(assembly, mode, path, payload):
    app, execution, devices, _ = assembly
    execution._transport_mode = mode
    with ApiClient(app, lifespan='on') as api:
        response = api.post('/api/v1/recipes/xdl/' + path, json=payload)
        assert response.status_code == 503
        assert devices[0].calls == devices[0].sf_calls == []


def test_no_execution_profile_is_not_an_implicit_fake_profile(tmp_path):
    app = create_app(database_path=tmp_path / 'domain.db')
    with ApiClient(app) as api:
        assert api.post('/api/v1/recipes/xdl/inspect', json={"xml": XML}).status_code == 503


def test_rejected_import_cannot_save_or_dispatch(assembly):
    app, _, devices, _ = assembly
    with ApiClient(app, lifespan='on') as api:
        for xml in [XML.replace('1000 uL', '1.0001 mL'), XML.replace('Wait', 'HeatChill')]:
            response = api.post('/api/v1/recipes/xdl/import', json={"xml": xml, **BINDINGS})
            assert response.status_code == 422, response.text
        assert api.get('/api/v1/recipes').json() == []
        assert devices[0].calls == devices[0].sf_calls == []


@pytest.mark.parametrize('name', ['LABFORGE_ARDUINO_PORT', 'LABFORGE_SF_BOTTOM_VALVE_PORT'])
def test_demo_rejects_live_configuration_before_creating_state(tmp_path, name):
    directory = tmp_path / 'not-created'
    result = subprocess.run([sys.executable, '-m', 'tests.xdl_demo', '--state-dir', str(directory)],
        env={**os.environ, name: 'forbidden-test-port'}, capture_output=True, text=True, timeout=5)
    assert result.returncode == 2 and 'unset LABFORGE_ARDUINO_PORT' in result.stderr
    assert not directory.exists()


def test_demo_never_reuses_or_repairs_an_existing_bundle(tmp_path):
    from tests.xdl_demo import demonstrate
    marker = tmp_path / 'existing-state'
    marker.write_bytes(b'preserved')
    with pytest.raises(ValueError, match='new empty'):
        demonstrate(tmp_path)
    assert marker.read_bytes() == b'preserved'


def test_published_example_uses_the_supported_reference_profile():
    xml = (Path(__file__).parents[1] / 'examples/xdl2/coloured-water.xdl').read_text()
    definition = import_xdl(XdlImportRequest(xml=xml, reagents={'S':'coloured_water'},
                                            vessels={'REACTOR':'reaction_vessel'}))
    assert len(definition.steps) == 2 and definition.steps[0].volume_ml == 1


@pytest.mark.parametrize('extra', [{'readiness': {}}, {'run_id': 'do-not-run'}, {'execute': True}])
def test_import_request_cannot_include_execution_instructions(assembly, extra):
    app, _, devices, _ = assembly
    with ApiClient(app, lifespan='on') as api:
        response = api.post('/api/v1/recipes/xdl/import', json={'xml': XML, **BINDINGS, **extra})
        assert response.status_code == 422
        assert api.get('/api/v1/recipes').json() == []
        assert devices[0].calls == devices[0].sf_calls == []
