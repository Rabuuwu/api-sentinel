"""Durable limits and token isolation, using only an explicitly selected test DB."""
import asyncio
import os
import secrets
from datetime import timedelta

import httpx
import pytest
from account_helpers import create_identity, remove_identity
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url

from api_sentinel.app import create_app
from api_sentinel.auth import digest
from api_sentinel.auth_models import AuthBudget, EmailAction
from api_sentinel.config import Settings
from api_sentinel.models import now

pytestmark = pytest.mark.integration


def test_invalid_budget_survives_restart_but_does_not_block_valid_links(tmp_path):
    url = os.getenv('SENTINEL_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Requires isolated migrated localhost sentinel_test')
    parsed = make_url(url)
    assert parsed.host in {'localhost', '127.0.0.1'} and parsed.database == 'sentinel_test'
    config = Settings(url, 'x'*40, secrets_dir=str(tmp_path),
                      webhook_encryption_key='ab'*32, gmail_client_id='test-client',
                      gmail_client_secret='test-secret', gmail_refresh_token='test-refresh',
                      mail_from='sender@gmail.com', public_app_url='https://example.com')

    async def run():
        app = create_app(config)
        db = app.state.db
        user_id, _ = await create_identity(db)
        good = secrets.token_urlsafe(32)
        second = None
        try:
            async with db.sessions.begin() as session:
                await session.execute(delete(AuthBudget))
                from api_sentinel.auth_models import User
                user = await session.get(User, user_id)
                user.email = 'limits@example.com'
                session.add(EmailAction(token_hash=digest(good), user_id=user_id,
                                        purpose='reset', email=user.email,
                                        expires_at=now()+timedelta(minutes=5)))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url='http://localhost') as client:
                async def invalid(i):
                    return await client.post('/api/v1/auth/password-reset/confirm', json={
                        'token': f'{i:043}', 'new_password': 'a new test password 12345'})
                results = await asyncio.gather(*(invalid(i) for i in range(31)))
                assert sum(r.status_code == 400 for r in results) == 30
                assert sum(r.status_code == 429 for r in results) == 1
            # New app/engine shares persisted counters, not process-local state.
            second = create_app(config)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=second),
                                         base_url='http://localhost') as client:
                blocked = await client.post('/api/v1/auth/password-reset/confirm', json={
                    'token': 'x'*43, 'new_password': 'a new test password 12345'})
                assert blocked.status_code == 429
                responses = await asyncio.gather(*(
                    client.post('/api/v1/auth/password-reset/confirm', json={
                        'token': good, 'new_password': 'a new test password 12345'})
                    for _ in range(2)))
                assert sum(r.status_code == 200 for r in responses) == 1
                assert all(r.status_code in (200, 400, 429) for r in responses)
            async with db.sessions() as session:
                keys = list((await session.scalars(select(AuthBudget.key))).all())
                assert all(len(key) == 64 for key in keys)
                assert good not in keys
        finally:
            await remove_identity(db, user_id)
            async with db.sessions.begin() as session:
                await session.execute(delete(AuthBudget))
            await db.close()
            if second:
                await second.state.db.close()
    asyncio.run(run())
