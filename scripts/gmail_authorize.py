"""Operator-run OAuth setup. Requests only gmail.send, writes secrets to ignored .local/."""

import os
import tempfile
from pathlib import Path


def main():
    from google_auth_oauthlib.flow import InstalledAppFlow

    root = Path(__file__).resolve().parents[1]
    source = root / ".local/google-oauth-client.json"
    target = root / ".local/gmail-render.env"
    if not source.is_file():
        raise SystemExit(
            "Save the downloaded Desktop OAuth client JSON as .local/google-oauth-client.json"
        )
    source.chmod(0o600)
    flow = InstalledAppFlow.from_client_secrets_file(
        str(source), scopes=["https://www.googleapis.com/auth/gmail.send"]
    )
    credentials = flow.run_local_server(
        host="127.0.0.1",
        port=0,
        prompt="consent",
        access_type="offline",
        success_message="Gmail authorization complete. Close this tab.",
    )
    if not credentials.refresh_token:
        raise SystemExit(
            "Google did not return a refresh token; repeat authorization with offline access"
        )
    values = {
        "GMAIL_CLIENT_ID": credentials.client_id,
        "GMAIL_CLIENT_SECRET": credentials.client_secret,
        "GMAIL_REFRESH_TOKEN": credentials.refresh_token,
    }
    fd, temporary = tempfile.mkstemp(dir=target.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            for key, value in values.items():
                if not value or "\n" in value or "\r" in value:
                    raise ValueError("Invalid OAuth result")
                stream.write(key + "=" + value + "\n")
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print("Saved OAuth secrets to .local/gmail-render.env (permissions 600).")
    print("Copy these three values into Render Environment. Do not commit or share this file.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(
            "Gmail setup failed (" + type(error).__name__ + "); no credentials printed"
        ) from None
