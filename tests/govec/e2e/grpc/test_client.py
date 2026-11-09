import pytest

from govec.exceptions import GoVecConnectionError
from tests.govec.sync_or_async import ClientKind, connect_client

pytestmark = pytest.mark.anyio


@pytest.mark.e2e
async def test_connect__unreachable_server__raises_connection_error(
    client_kind: ClientKind,
) -> None:
    # Arrange
    unused_port = 59999

    # Act / Assert
    with pytest.raises(GoVecConnectionError):
        await connect_client(client_kind, "localhost", unused_port, "grpc")
