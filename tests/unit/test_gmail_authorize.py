import json
import runpy
from pathlib import Path

import pytest

load_client = runpy.run_path(str(Path(__file__).parents[2] / "scripts/gmail_authorize.py"))[
    "load_client"
]


def test_invalid_client_json_reports_location_without_leaking_contents(tmp_path):
    source = tmp_path / "client.json"
    source.write_text('{"secret": private-secret-value}')
    with pytest.raises(SystemExit) as error:
        load_client(source)
    assert "line 1" in str(error.value)
    assert "private-secret-value" not in str(error.value)


def test_desktop_json_accepts_utf8_bom(tmp_path):
    source = tmp_path / "client.json"
    data = {
        "installed": {
            "client_id": "test",
            "client_secret": "secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    source.write_text(json.dumps(data), encoding="utf-8-sig")
    assert load_client(source) == data


@pytest.mark.parametrize("data", [{}, {"web": {}}, {"installed": {"client_id": "test"}}])
def test_incomplete_or_wrong_client_type_is_rejected(tmp_path, data):
    source = tmp_path / "client.json"
    source.write_text(json.dumps(data))
    with pytest.raises(SystemExit):
        load_client(source)
