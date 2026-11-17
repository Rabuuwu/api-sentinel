"""Operator-run OAuth setup. Requests only gmail.send, writes secrets to ignored .local/."""

import json
import os
import tempfile
from pathlib import Path


def load_client(source):
    try:
        data = json.loads(source.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise SystemExit(
            "Invalid JSON in .local/google-oauth-client.json "
            f"(line {error.lineno}, column {error.colno}). "
            "Replace it with the complete Desktop OAuth JSON downloaded from Google Cloud; "
            "do not paste only the client ID, secret or .env contents."
        ) from None
    except UnicodeError:
        raise SystemExit(
            "OAuth client file must be the UTF-8 JSON downloaded from Google"
        ) from None
    client = data.get("installed") if isinstance(data, dict) else None
    if not isinstance(client, dict):
        raise SystemExit("Expected a Desktop app OAuth JSON with an 'installed' object")
    for name in ("client_id", "client_secret"):
        if not isinstance(client.get(name), str) or not client[name].strip():
            raise SystemExit("Downloaded OAuth JSON is missing " + name)
    if (
        client.get("auth_uri") != "https://accounts.google.com/o/oauth2/auth"
        or client.get("token_uri") != "https://oauth2.googleapis.com/token"
    ):
        raise SystemExit("OAuth JSON must use the official Google authorization and token URLs")
    return data


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
    flow = InstalledAppFlow.from_client_config(
        load_client(source), scopes=["https://www.googleapis.com/auth/gmail.send"]
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
