from collections.abc import Callable

import httpx
import pytest

from govec.transport.rest import RESTTransport


@pytest.fixture
def rest_transport() -> Callable[..., RESTTransport]:
    """Builds a RESTTransport whose requests are answered in-process.

    The transport is constructed exactly as production does -- same URL
    building, same auth header -- and only its underlying httpx client is
    swapped for one backed by httpx.MockTransport. That keeps these tests on
    the real request/response handling while removing the need for a server,
    and still lets a test assert on what was actually sent.

    `handler` receives the httpx.Request and returns the httpx.Response to
    answer it with, so a test can vary the reply per URL or assert on headers.
    """

    def _build(
        handler: Callable[[httpx.Request], httpx.Response],
        api_key: str | None = None,
    ) -> RESTTransport:
        transport = RESTTransport("testserver", 8000, api_key, tls=False)
        transport.client.close()
        transport.client = httpx.Client(
            headers=transport.headers,
            timeout=10.0,
            transport=httpx.MockTransport(handler),
        )
        return transport

    return _build


@pytest.fixture
def ok_json() -> Callable[..., Callable[[httpx.Request], httpx.Response]]:
    """Builds a handler that answers every request with one payload."""

    def _build(
        data: object, status_code: int = 200
    ) -> Callable[[httpx.Request], httpx.Response]:
        def _handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code, json={"success": True, "data": data})

        return _handler

    return _build
