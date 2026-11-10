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

The [GitHub backend/SiLA checks](docs/CI.md) run the full suite with the independent
C# client for relevant pushes and fork pull requests. CI uses the tool versions in
`ci-constraints.txt` and `global.json` and rejects skipped tests.

The default API can be started with `.venv/bin/uvicorn app.main:app`; it does not
automatically enable owned Recipes execution. The fake browser profile is
documented in [docs/BROWSER_CHECK.md](docs/BROWSER_CHECK.md). Explicit real-device
preparation is separate: [docs/LIVE_RECIPES.md](docs/LIVE_RECIPES.md).

The optional [SiLA 2 adapter](docs/SILA2.md) exposes discovery, status, recipe reads,
validation, execution, progress and Stop through the same backend using fake
devices only. Install `.[dev,sila2]` for its TLS client/server checks and launcher.
The [independent C# client](tools/sila2-client/README.md) adds a runnable local fake
demo and interoperability checks using a separate SiLA implementation.
SiLA application requests now require explicit client tokens with READ_ONLY or
CONTROL rights and are attributed in a separate request audit. This remains a
local fake-device scope; existing HTTP/UI authorization is unchanged.

The [XDL 2 interchange profile](docs/XDL2.md) adds bounded import/export of liquid
Add, Transfer and Wait through the existing Recipes editor and validation path.
It references public XDL release 2.1.0 (XML format 2.0.0), requires explicit
reagent/vessel bindings and currently permits FAKE profiles only. Import creates
an unsaved draft; save, review and Start remain separate actions.

Existing state, operator credentials, stable USB identities and profile digests
are not migrated or reset by the repository consolidation. The package remains
named `labforge-backend`. Current canonical state is in
[../docs/LABFORGE_CURRENT_STATE.md](../docs/LABFORGE_CURRENT_STATE.md).
