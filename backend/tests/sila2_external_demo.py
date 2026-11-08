"""One-command fake demonstration; all client requests run in a separate C# process."""

import argparse
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.browser_check import require_fake_environment

CLIENT_DLL = (Path(__file__).resolve().parents[1] / "tools/sila2-client/bin/Release/net10.0"
              / "SynMachine.SilaClient.dll")


async def demonstrate(directory, dotnet, dll):
    require_fake_environment()
    if directory.exists() and (directory.is_symlink() or any(directory.iterdir())):
        raise ValueError("demo requires a new empty fake state directory; existing state is preserved")
    if not dotnet.is_file() or not dll.is_file():
        raise ValueError("explicit dotnet executable and built client DLL are required")

    # Only server-side Python dependencies are used; the client is the compiled C# program.
    import httpx
    from sila.server import create_certificate

    from app.sila2.server import fake_server
    from tests.browser_check import build_profile
    from tests.sila2_credentials import issue_fake_access

    application, execution = build_profile(directory, command_delay=0)
    identity = execution.bundle.lifecycle_id
    certificate = create_certificate(identity, ip_addresses=["127.0.0.1"])
    with TemporaryDirectory(prefix="synmachine-external-client-") as temporary:
        work = Path(temporary)
        cert = work / "public-certificate.pem"
        cert.write_bytes(certificate.pem_certificate)
        access, tokens = issue_fake_access(directory, work)
        readiness = work / "fake-readiness.json"
        readiness.write_text(json.dumps({
            "operator": "Fake interoperability demo",
            "evidence_note": "Explicit fake fixture only; no physical readiness is asserted.",
            "sources_match_recipe": True, "reactor_sf_column_empty_clean": True,
            "waste_capacity_available": True, "collection_tubes_ready": True,
        }))
        async with application.router.lifespan_context(application):
            async with fake_server(application, server_uuid=identity,
                                   certificate=certificate.pem_certificate,
                                   private_key=certificate.pem_private_key, access=access) as server:
                async def client(action, *arguments, role="controller", denied=None):
                    process = await asyncio.create_subprocess_exec(
                        str(dotnet), str(dll), action, "--port", server.address.rsplit(":", 1)[1],
                        "--certificate", str(cert), "--server-uuid", identity,
                        "--token-file", str(tokens[role]), *arguments,
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    )
                    try:
                        output, error = await asyncio.wait_for(process.communicate(), 40)
                    finally:
                        if process.returncode is None:
                            process.kill()
                            await process.wait()
                    if denied is not None:
                        assert process.returncode != 0
                        assert json.loads(error.decode().splitlines()[0])["error"] == denied
                        return []
                    if process.returncode:
                        raise RuntimeError(error.decode().strip())
                    return [json.loads(line) for line in output.decode().splitlines()]

                async def prepare(api, name, steps):
                    # Fixture preparation uses the same recipe-save API as the UI, in fake state only.
                    response = await api.post("/api/v1/recipes", json={"definition": {"name": name, "steps": steps}})
                    response.raise_for_status()
                    saved = response.json()
                    snapshot = work / f"{name}.json"
                    snapshot.write_text(json.dumps(saved))
                    return snapshot

                print(f"FAKE TRANSPORTS ONLY | separate .NET client | state={directory.absolute()}", flush=True)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(application),
                                            base_url="http://fake", trust_env=False) as api:
                    complete_recipe = await prepare(api, "complete", [
                        {"kind": "ADD", "source": "S", "volume_ml": "1"},
                        {"kind": "WAIT", "duration_seconds": "1"},
                    ])
                    stop_recipe = await prepare(api, "stop", [{"kind": "WAIT", "duration_seconds": "30"}])
                    discovered = (await client("discover"))[0]
                    assert len(discovered["features"]) == 4
                    assert (await client("status"))[0]["execution"]["transport_mode"] == "FAKE"
                    assert len((await client("recipes", role="reader"))[0]) == 2
                    await client("start", "--recipe", str(complete_recipe), "--readiness", str(readiness),
                                 "--run-id", "reader-denied", role="reader", denied="PermissionDenied")
                    print("PASS: authenticated TLS/discovery; reader can read recipes but cannot Start", flush=True)
                    await client("start", "--recipe", str(complete_recipe), "--readiness", str(readiness),
                                 "--run-id", "external-demo-complete")
                    completed = (await client("watch", "--run-id", "external-demo-complete"))[-1]
                    assert completed["status"] == "COMPLETED" and completed["recipe_step_index"] == 2
                    print("PASS: recipe accepted, progress observed, run COMPLETED", flush=True)
                    await client("start", "--recipe", str(stop_recipe), "--readiness", str(readiness),
                                 "--run-id", "external-demo-stop")
                    current = (await client("status"))[0]["execution"]
                    await client("stop", "--operation-id", current["operation"]["operation_id"],
                                 role="reader", denied="PermissionDenied")
                    await client("stop", "--operation-id", current["operation"]["operation_id"])
                    stopped = (await client("watch", "--run-id", "external-demo-stop"))[-1]
                    assert stopped["status"] == "ABORTED"
                    assert (await client("status"))[0]["execution"]["retained_owner_id"]
                    print("PASS: reader Stop denied; controller Stop accepted; ABORTED with fake owner retained", flush=True)
                    print(f"Request attribution preserved in {access.audit.path}", flush=True)
    print("DONE: listeners/client processes closed; fake state preserved without repair/reset", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="SynMachine independent SiLA client — fake demo only")
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--dotnet", type=Path, required=True)
    parser.add_argument("--client-dll", type=Path, default=CLIENT_DLL)
    args = parser.parse_args(argv)
    try:
        require_fake_environment()
        asyncio.run(demonstrate(args.state_dir, args.dotnet, args.client_dll))
    except (ValueError, RuntimeError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
