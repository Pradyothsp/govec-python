from collections.abc import Iterator

import pytest
import respx

from tests.govec.rest_api import BASE_URL


@pytest.fixture
def anyio_backend() -> str:
    # anyio's plugin would also run every async test on trio. grpc.aio only
    # runs on asyncio, so the async client is asyncio-only and so are its tests.
    return "asyncio"


@pytest.fixture
def server() -> Iterator[respx.MockRouter]:
    """GoVec's REST API, faked at the httpx layer.

    The real client and transport run unchanged; only the network is
    replaced. A request with no route fails the test rather than reaching
    anything, and so does a route the test added but never hit.
    """
    with respx.mock(base_url=BASE_URL) as router:
        yield router
