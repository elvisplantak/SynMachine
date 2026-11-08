"""Manual UI + SiLA 2 check over the existing hardwired fake browser profile."""

import argparse
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.browser_check import require_fake_environment


async def serve(directory: Path, *, http_port: int, sila_port: int, command_delay: float):
    require_fake_environment()

    # This guard must precede build_profile's deferred app.main import.
    from sila.server import create_certificate
    from uvicorn import Config, Server

    from app.sila2.server import fake_server
    from tests.browser_check import build_profile
    from tests.sila2_credentials import issue_fake_access

    application, execution = build_profile(directory, command_delay=command_delay)
    identity = execution.bundle.lifecycle_id
    certificate = create_certificate(identity, ip_addresses=["127.0.0.1"])

    # Only the public test certificate is written. The ephemeral key stays in memory.
    with TemporaryDirectory(prefix="synmachine-sila2-tls-") as tls_directory:
        certificate_path = Path(tls_directory) / "certificate.pem"
        certificate_path.write_bytes(certificate.pem_certificate)
        access, token_paths = issue_fake_access(directory, tls_directory)
        async with application.router.lifespan_context(application):
            async with fake_server(
                application, server_uuid=identity, certificate=certificate.pem_certificate,
                private_key=certificate.pem_private_key, port=sila_port,
                access=access,
            ) as server:
                print(f"FAKE TRANSPORTS ONLY | state={directory.absolute()} | SiLA TLS={server.address}",
                      flush=True)
                print(f"SiLA UUID={identity} | trust certificate={certificate_path}", flush=True)
                print(f"READ_ONLY token file={token_paths['reader']} | CONTROL token file={token_paths['controller']}", flush=True)
                print(f"SiLA access audit={access.audit.path} | client tokens expire in one hour", flush=True)
                # FastAPI lifespan is already owned above. One process, one executor.
                await Server(Config(application, host="127.0.0.1", port=http_port,
                                    workers=1, lifespan="off")).serve()


def main(argv=None):
    parser = argparse.ArgumentParser(description="SynMachine UI + SiLA 2 — fake transports only")
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--http-port", type=int, default=8000)
    parser.add_argument("--sila-port", type=int, default=50052)
    parser.add_argument("--command-delay", type=float, default=0.15)
    args = parser.parse_args(argv)
    if not all(1 <= value <= 65535 for value in (args.http_port, args.sila_port)):
        parser.error("ports must be in 1..65535")
    if args.http_port == args.sila_port:
        parser.error("HTTP and SiLA ports must differ")
    try:
        require_fake_environment()
    except ValueError as error:
        parser.error(str(error))
    asyncio.run(serve(args.state_dir, http_port=args.http_port, sila_port=args.sila_port,
                      command_delay=args.command_delay))


if __name__ == "__main__":
    main()
