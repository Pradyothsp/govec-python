import pytest

from govec.async_client import AsyncGoVecClient
from govec.client import GoVecClient
from govec.exceptions import GoVecClientClosedError, GoVecConnectionError
from tests.govec.e2e.conftest import REST_PORT
from tests.govec.sync_or_async import ClientKind, connect_client

pytestmark = pytest.mark.anyio


@pytest.mark.e2e
async def test_connect__unreachable_server__raises_connection_error(
    client_kind: ClientKind,
) -> None:
    # Arrange
    # The gRPC suite had this; REST did not, and REST was the transport that
    # used to let httpx.ConnectError escape instead of wrapping it.
    unused_port = 1

    # Act / Assert
    with pytest.raises(GoVecConnectionError):
        await connect_client(client_kind, "localhost", unused_port, "rest")


@pytest.mark.e2e
def test_context_manager__block_exits__client_is_closed() -> None:
    # Arrange / Act -- a client of its own, so no fixture is closed under
    # another test.
    with GoVecClient.connect("localhost", REST_PORT, "", "rest", tls=False) as client:
        assert client.health().status == "ok"

    # Assert
    with pytest.raises(GoVecClientClosedError):
        client.health()


@pytest.mark.e2e
async def test_async_context_manager__block_exits__client_is_closed() -> None:
    # Arrange / Act
    async with AsyncGoVecClient.connect(
        "localhost", REST_PORT, "", "rest", tls=False
    ) as client:
        assert (await client.health()).status == "ok"

    # Assert
    with pytest.raises(GoVecClientClosedError):
        await client.health()
