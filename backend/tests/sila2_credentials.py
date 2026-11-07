"""Explicit fake-only client credentials for manual launchers and test fixtures."""

from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
from secrets import token_urlsafe


def issue_fake_access(state_directory, credential_directory):
    from app.sila2.access import AccessControl, AuditJournal, Credential, Policy, Role

    directory = Path(credential_directory)
    credentials, paths = [], {}
    for name, role in (("reader", Role.READ_ONLY), ("controller", Role.CONTROL)):
        token = token_urlsafe(32)
        path = directory / f"{name}.token"
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(token)
        credentials.append(Credential.from_token(
            client_id=f"fake-{name}", role=role, token=token,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        ))
        paths[name] = path
    return AccessControl(Policy(credentials), AuditJournal(Path(state_directory) / "sila-access.sqlite3")), paths
