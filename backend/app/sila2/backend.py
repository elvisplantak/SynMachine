"""In-process calls to the existing API; no second owner or lifecycle startup."""

import json
import re
from datetime import UTC, datetime

import httpx
from fastapi import FastAPI

PREFIX = "/api/v1"


class BackendRejected(Exception):
    """Preserve the backend HTTP status and detail across the SiLA boundary."""

    def __init__(self, status: int, detail):
        self.status = status
        self.detail = detail
        super().__init__(json.dumps({"status": status, "detail": detail}, ensure_ascii=False))


def path_id(value: str) -> str:
    # A single path segment, never a caller-selected API route.
    if value in (".", "..") or re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value) is None:
        raise BackendRejected(422, "identifier must contain 1..128 ASCII letters, digits or _.:-")
    return value


def json_object(value: str) -> dict:
    def reject_constant(_):
        raise ValueError("nonfinite JSON constant")

    try:
        parsed = json.loads(value, parse_constant=reject_constant)
    except (ValueError, TypeError):
        raise BackendRejected(422, "parameter must be a JSON object") from None
    if type(parsed) is not dict:
        raise BackendRejected(422, "parameter must be a JSON object")
    return parsed


class FakeBackend:
    """Adapts an already-started, explicitly FAKE FastAPI composition.

    ASGITransport does not run lifespan. The caller starts/closes the application
    once. Every operation checks its transport mode; this slice cannot target a
    network backend, enable a live executor, or supply operator credentials.
    """

    def __init__(self, application: FastAPI):
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application, raise_app_exceptions=False),
            base_url="http://synmachine.internal",
            trust_env=False,
        )

    async def close(self):
        await self._client.aclose()

    async def _request(self, method, path, payload=None):
        response = await self._client.request(method, path, json=payload)
        if response.is_error:
            # Unexpected server failures must not disclose tracebacks/paths.
            if response.status_code >= 500:
                raise BackendRejected(response.status_code, "backend unavailable; inspect backend state")
            raise BackendRejected(response.status_code, response.json().get("detail"))
        return response.json()

    async def execution(self):
        snapshot = await self._request("GET", PREFIX + "/execution")
        if snapshot.get("transport_mode") != "FAKE":
            raise BackendRejected(503, "SiLA adapter requires an explicitly FAKE backend")
        return snapshot

    async def status(self):
        execution = await self.execution()
        health = await self._request("GET", "/health")
        # Initial machine absence is an authoritative state, not an initialization request.
        try:
            machine = await self._request("GET", PREFIX + "/machine")
        except BackendRejected as error:
            if error.status != 404:
                raise
            machine = None
        return {"health": health, "execution": execution, "machine": machine}

    async def recipes(self):
        await self.execution()
        return await self._request("GET", PREFIX + "/recipes")

    async def read_recipe(self, recipe_id):
        await self.execution()
        return await self._request("GET", PREFIX + f"/recipes/{path_id(recipe_id)}")

    async def validate_recipe(self, definition_json):
        await self.execution()
        return await self._request("POST", PREFIX + "/recipes/preview", json_object(definition_json))

    async def start_recipe(self, recipe_id, run_id, expected_revision,
                           expected_content_digest, readiness_json):
        await self.execution()
        return await self._request("POST", PREFIX + f"/recipes/{path_id(recipe_id)}/execute", {
            "run_id": path_id(run_id),
            "expected_revision": expected_revision,
            "expected_content_digest": expected_content_digest,
            "readiness": json_object(readiness_json),
            "occurred_at": datetime.now(UTC).isoformat(),
        })

    async def progress(self, run_id):
        await self.execution()
        return await self._request("GET", PREFIX + f"/runs/{path_id(run_id)}")

    async def stop(self, operation_id):
        await self.execution()
        return await self._request("POST", PREFIX + f"/execution/{path_id(operation_id)}/stop", {
            "occurred_at": datetime.now(UTC).isoformat(),
        })
