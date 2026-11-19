import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api_sentinel.email_auth import EmailAccounts
from api_sentinel.models import now


class Session:
    def __init__(self, action):
        self.get = AsyncMock(return_value=action)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def test_invalid_links_never_spend_valid_or_login_budget():
    async def run():
        budget = AsyncMock()
        accounts = EmailAccounts(SimpleNamespace(sessions=lambda: Session(None)), None, budget)
        request = Request({'type': 'http', 'client': ('127.0.0.1', 1),
                           'headers': [(b'x-forwarded-for', b'forged-address')]})
        with pytest.raises(HTTPException) as failure:
            await accounts.action_budget('x'*43, 'reset', request)
        assert failure.value.status_code == 400
        assert budget.call_args.kwargs['namespace'] == 'invalid-reset'
        assert budget.call_args.args == ('127.0.0.1',)
    asyncio.run(run())


def test_valid_links_have_separate_hashed_subjects_and_operation_budgets():
    async def run():
        budget = AsyncMock()
        action = SimpleNamespace(purpose='verify', expires_at=now()+timedelta(minutes=1))
        accounts = EmailAccounts(SimpleNamespace(sessions=lambda: Session(action)), None, budget)
        request = Request({'type': 'http', 'client': ('127.0.0.1', 1)})
        await accounts.action_budget('a'*43, 'verify', request)
        await accounts.action_budget('b'*43, 'verify', request)
        calls = budget.call_args_list
        assert calls[0].args != calls[2].args
        assert all('a'*43 not in str(call) and 'b'*43 not in str(call) for call in calls)
        assert calls[0].kwargs['namespace'] == 'confirm-verify'
        assert calls[1].kwargs['namespace'] == 'client-confirm-verify'
    asyncio.run(run())
