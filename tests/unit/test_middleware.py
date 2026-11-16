import asyncio

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from api_sentinel.middleware import BodyLimitMiddleware


def test_chunked_request_cannot_bypass_body_limit():
    async def echo(request: Request):
        body = await request.body()
        return JSONResponse({"size": len(body)})

    async def run():
        app = BodyLimitMiddleware(Starlette(routes=[Route("/", echo, methods=["POST"])]), 100)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:

            async def chunks():
                for _ in range(3):
                    yield b"x" * 40

            response = await client.post("/", content=chunks())
            assert response.status_code == 413
            assert response.json()["error"]["code"] == "BODY_TOO_LARGE"
            response = await client.post("/", content=b"x" * 99)
            assert response.json() == {"size": 99}

    asyncio.run(run())
