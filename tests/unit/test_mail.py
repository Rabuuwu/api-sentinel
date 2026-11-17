import asyncio
import base64
from email import policy
from email.parser import BytesParser

import httpx
import pytest

from api_sentinel.config import Settings
from api_sentinel.mail_config import normalize_email
from api_sentinel.mailer import MailError, cipher, gmail_send


def config(**overrides):
    values = dict(
        webhook_encryption_key="ab" * 32,
        gmail_client_id="test-client",
        gmail_client_secret="private-oauth-secret",
        gmail_refresh_token="private-refresh-token",
        mail_from="sender@gmail.com",
        public_app_url="https://example.com/sentinel/",
    )
    values.update(overrides)
    return Settings("postgresql://localhost/sentinel_test", "x" * 40, **values)


def test_oauth_secrets_never_appear_in_config_repr():
    value = config()
    assert value.mail_enabled
    assert "private-oauth-secret" not in repr(value)
    assert "private-refresh-token" not in repr(value)
    encrypted = cipher(value).encrypt(b"private-link-token")
    assert b"private-link-token" not in encrypted
    assert cipher(value).decrypt(encrypted) == b"private-link-token"


@pytest.mark.parametrize(
    "address",
    [
        "a@b.com\r\nBcc: attacker@example.com",
        "Name <x@y.com>",
        "a..b@gmail.com",
        "no-at-sign",
        "x@localhost",
    ],
)
def test_email_header_injection_and_invalid_addresses_rejected(address):
    with pytest.raises(ValueError):
        normalize_email(address)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:pass@example.com",
        "https://example.com/#/reset",
        "https://example.com/?redirect=evil",
    ],
)
def test_recovery_base_url_rejects_untrusted_components(url):
    with pytest.raises(ValueError):
        config(public_app_url=url)


def test_gmail_https_refresh_and_send_uses_mime_and_only_two_google_endpoints():
    calls = []

    def transport(request):
        calls.append(request)
        if len(calls) == 1:
            assert str(request.url) == "https://oauth2.googleapis.com/token"
            assert b"grant_type=refresh_token" in request.content
            return httpx.Response(200, json={"access_token": "transient-access"})
        assert str(request.url) == "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
        assert request.headers["authorization"] == "Bearer transient-access"
        import json

        raw = json.loads(request.content)["raw"]
        message = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw))
        assert message["To"] == "recipient@example.com"
        assert message["From"] == "sender@gmail.com"
        assert "15 minutes" in message.get_content()
        assert "#/account-link?purpose=reset&token=test" in message.get_content()
        return httpx.Response(200, json={"id": "accepted"})

    asyncio.run(
        gmail_send(
            config(),
            {
                "email": "recipient@example.com",
                "purpose": "reset",
                "link": "https://example.com/#/account-link?purpose=reset&token=test",
            },
            httpx.MockTransport(transport),
        )
    )
    assert len(calls) == 2


def test_provider_failure_is_sanitized_and_marked_permanent():
    with pytest.raises(MailError) as result:
        asyncio.run(
            gmail_send(
                config(),
                {
                    "email": "recipient@example.com",
                    "purpose": "verify",
                    "link": "https://example.com/#/account-link?token=secret",
                },
                httpx.MockTransport(
                    lambda r: httpx.Response(400, json={"error": "private provider details"})
                ),
            )
        )
    assert result.value.permanent
    assert str(result.value) == "GMAIL_AUTH_FAILED"


def test_partial_oauth_config_fails_closed_and_disabled_mode_remains_available():
    with pytest.raises(ValueError, match="Gmail requires"):
        config(gmail_refresh_token="")
    assert not Settings("postgresql://localhost/sentinel_test", "x" * 40).mail_enabled


def test_transient_provider_error_keeps_retryable_status():
    calls = 0

    def transport(request):
        nonlocal calls
        calls += 1
        return (
            httpx.Response(200, json={"access_token": "test"})
            if calls == 1
            else httpx.Response(429, json={"error": "quota exceeded"})
        )

    with pytest.raises(MailError) as result:
        asyncio.run(
            gmail_send(
                config(),
                {
                    "email": "recipient@example.com",
                    "purpose": "reset",
                    "link": "https://example.com/#/account-link?token=secret",
                },
                httpx.MockTransport(transport),
            )
        )
    assert not result.value.permanent
    assert str(result.value) == "GMAIL_SEND_FAILED"
