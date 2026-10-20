# SynMachine backend

The Python/FastAPI backend validates and stores recipes, selects supported routes
and orchestrates execution through the existing owned command/journal paths.
Device pins, stepping, direction and low-level execution belong to firmware.

See the [project README](../README.md) for the prototype scope and fake-device
quick start. From this directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
```

The default API can be started with `.venv/bin/uvicorn app.main:app`; it does not
automatically enable owned Recipes execution. The fake browser profile is
documented in [docs/BROWSER_CHECK.md](docs/BROWSER_CHECK.md). Explicit real-device
preparation is separate: [docs/LIVE_RECIPES.md](docs/LIVE_RECIPES.md).

Existing state, operator credentials, stable USB identities and profile digests
are not migrated or reset by the repository consolidation. The package remains
named `labforge-backend`. Current canonical state is in
[../docs/LABFORGE_CURRENT_STATE.md](../docs/LABFORGE_CURRENT_STATE.md).
