# LabForge backend

This repository will contain the LabForge backend and domain core. Its current focus is the Guided Demo and the data needed by Demo Log, separate from the sibling UI and firmware repositories.

The first foundation is intentionally narrow: validated demo configuration, configured fluid-plan calculation, run phases, phase-dependent control policy, and a minimal FastAPI health endpoint. It does not include execution, persistence, serial communication, or hardware integration. Arduino pin assignments belong to firmware, not the backend.

## Local setup

Ubuntu with Python 3.12:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run the checks:

```bash
pytest
ruff check .
```

Start the local API:

```bash
uvicorn app.main:app --reload
```

`GET /health` reports only backend application availability. It does not indicate hardware readiness.
