import pytest


@pytest.fixture
def anyio_backend() -> str:
    # anyio's plugin would also run every async test on trio. grpc.aio only
    # runs on asyncio, so the async client is asyncio-only and so are its tests.
    return "asyncio"
