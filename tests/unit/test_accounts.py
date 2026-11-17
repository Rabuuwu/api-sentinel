import pytest
from pydantic import ValidationError

from api_sentinel.auth import Bootstrap, Credentials, digest, owner
from api_sentinel.passwords import Passwords


def test_password_storage_is_salted_argon2id():
    passwords = Passwords()
    first = passwords.hash("a unique passphrase for testing")
    second = passwords.hash("a unique passphrase for testing")
    assert first != second
    assert first.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    assert passwords.verify(first, "a unique passphrase for testing")
    assert not passwords.verify(first, "incorrect password")
    assert not passwords.verify("broken", "incorrect password")
    assert not passwords.check_needs_rehash(first)


def test_credentials_do_not_accept_roles_or_short_passwords():
    with pytest.raises(ValidationError):
        Credentials(username="alice", password="short")
    with pytest.raises(ValidationError):
        Credentials(username="alice", password="a sufficiently long password", is_admin=True)
    data = Bootstrap(username="Alice", password="a sufficiently long password", setup_key="k" * 40)
    assert data.username == "alice"
    assert "sufficiently" not in repr(data)
    assert "k" * 40 not in repr(data)


def test_session_digest_and_fail_closed_owner():
    assert len(digest("opaque-token")) == 64
    assert digest("opaque-token") != "opaque-token"

    class Session:
        info = {}

    with pytest.raises(KeyError):
        owner(Session())
