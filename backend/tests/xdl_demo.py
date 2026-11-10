"""Runnable XDL import -> existing save/review/Start -> progress -> export, fake only."""

import argparse
from datetime import UTC, datetime
from pathlib import Path

from tests.browser_check import require_fake_environment


def demonstrate(directory):
    require_fake_environment()
    if directory.exists() and (directory.is_symlink() or any(directory.iterdir())):
        raise ValueError("XDL demo requires a new empty fake state directory; existing state is preserved")
    from tests.browser_check import build_profile
    from tests.test_api import ApiClient
    from tests.test_owned_application_api import wait_idle
    from tests.test_recipes import readiness

    xml = (Path(__file__).resolve().parents[1] / 'examples/xdl2/coloured-water.xdl').read_text()
    application, _ = build_profile(directory, command_delay=0)
    with ApiClient(application, lifespan='on') as api:
        def post(path, data):
            response = api.post('/api/v1/recipes' + path, json=data)
            if response.status_code >= 400:
                raise RuntimeError(response.text)
            return response.json()

        inspected = post('/xdl/inspect', {'xml': xml})
        assert inspected['reference_release'] == '2.1.0'
        draft = post('/xdl/import', {'xml': xml,
            'reagents': {'S': 'coloured_water'}, 'vessels': {'REACTOR': 'reaction_vessel'}})
        assert api.get('/api/v1/recipes').json() == []
        assert not api.get('/api/v1/execution').json()['busy']
        print('PASS: XDL 2 inspected and imported with explicit bindings; no save or Start', flush=True)
        saved = post('', {'definition': draft['definition']})
        review = post('/preview', saved['definition'])
        assert review['content_digest'] == saved['content_digest']
        accepted = post(f"/{saved['recipe_id']}/execute", {
            'run_id': 'xdl-demo', 'expected_revision': saved['revision'],
            'expected_content_digest': saved['content_digest'],
            'readiness': readiness().model_dump(mode='json'),
            'occurred_at': datetime.now(UTC).isoformat()})
        assert accepted['run_id'] == 'xdl-demo'
        progress = api.get('/api/v1/runs/xdl-demo').json()
        print(f"PASS: existing save/review/Start path accepted; progress={progress['status']}", flush=True)
        assert wait_idle(api)['error'] is None
        completed = api.get('/api/v1/runs/xdl-demo').json()
        assert completed['status'] == 'COMPLETED' and completed['recipe_step_index'] == 2
        output = post('/xdl/export', {'definition': saved['definition']})
        roundtrip = post('/xdl/import', {key: output[key] for key in ('xml', 'reagents', 'vessels')})
        assert roundtrip['definition'] == saved['definition']
        (directory / 'roundtrip.xdl').write_text(output['xml'])
        print('PASS: run COMPLETED at step 2; exported XDL imports to the same recipe', flush=True)
    print(f'DONE: server closed; separate fake evidence preserved at {directory}', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='SynMachine XDL 2 demonstration, fake devices only')
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        demonstrate(args.state_dir)
    except (ValueError, RuntimeError) as error:
        parser.exit(2, f'{error}\n')


if __name__ == '__main__':
    main()
