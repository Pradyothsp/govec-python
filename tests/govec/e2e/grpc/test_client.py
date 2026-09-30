import pytest

from govec.client import GoVecClient
from govec.exceptions import GoVecConnectionError


@pytest.mark.e2e
def test_client_init__unreachable_server__raises_connection_error() -> None:
    # Arrange
    unused_port = 59999

    # Act / Assert
    with pytest.raises(GoVecConnectionError):
        GoVecClient(
            host="localhost",
            port=unused_port,
            api_key="",
            protocol="grpc",
            tls=False,
        )
