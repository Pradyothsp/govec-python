from collections.abc import Callable
from typing import cast

import pytest

from govec.transport.rest import AsyncRESTTransport, RESTTransport
from tests.govec.rest_api import HOST, PORT


@pytest.fixture(params=[RESTTransport, AsyncRESTTransport], ids=["sync", "async"])
def rest_transport(
    request: pytest.FixtureRequest,
) -> Callable[..., RESTTransport | AsyncRESTTransport]:
    """Builds each REST transport exactly as production does.

    Every test that takes this runs once per transport, so sync and async are
    held to the same behaviour. Nothing in either is swapped: requests go out
    through its own httpx client and the `server` fixture answers them.
    """
    transport_class = cast(type[RESTTransport | AsyncRESTTransport], request.param)

    def _build(api_key: str | None = None) -> RESTTransport | AsyncRESTTransport:
        return transport_class(HOST, PORT, api_key, tls=False)

    return _build
