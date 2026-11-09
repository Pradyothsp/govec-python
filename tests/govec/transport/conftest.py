from collections.abc import Callable

import pytest

from govec.transport.rest import RESTTransport
from tests.govec.rest_api import HOST, PORT


@pytest.fixture
def rest_transport() -> Callable[..., RESTTransport]:
    """Builds a RESTTransport exactly as production does.

    Nothing in it is swapped: requests go out through its own httpx client and
    the `server` fixture answers them.
    """

    def _build(api_key: str | None = None) -> RESTTransport:
        return RESTTransport(HOST, PORT, api_key, tls=False)

    return _build
