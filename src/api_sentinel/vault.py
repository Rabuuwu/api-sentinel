"""Write-only webhook secrets stored outside the database in a private local volume."""

import os
import re
import tempfile
from pathlib import Path
from uuid import UUID


def validate_webhook(value: str) -> str:
    if not re.fullmatch(r"https://discord\.com/api/webhooks/[0-9]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("Use a Discord webhook URL without query parameters")
    return value


class SecretVault:
    def __init__(self, directory: str):
        self.directory = Path(directory)

    def write(self, key: UUID, value: str):
        validate_webhook(value)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        fd, temporary = tempfile.mkstemp(dir=self.directory)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(value)
            os.replace(temporary, self.directory / str(key))
        finally:
            Path(temporary).unlink(missing_ok=True)

    def read(self, key: UUID) -> str:
        return validate_webhook((self.directory / str(key)).read_text())
