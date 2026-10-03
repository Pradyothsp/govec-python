import pytest

from govec.client import GoVecClient
from govec.exceptions import GoVecClientClosedError, GoVecConnectionError


@pytest.mark.e2e
def test_client_init__unreachable_server__raises_connection_error() -> None:
    # The gRPC suite had this; REST did not, and REST was the transport that
    # used to let httpx.ConnectError escape instead of wrapping it.
    with pytest.raises(GoVecConnectionError):
        GoVecClient(host="localhost", port=1, api_key="", protocol="rest", tls=False)


@pytest.mark.e2e
def test_context_manager__block_exits__client_is_closed() -> None:
    # Arrange / Act -- a separate client, so the session-scoped fixture is not
    # closed out from under the rest of the suite.
    with GoVecClient(
        host="localhost", port=9697, api_key="", protocol="rest", tls=False
    ) as client:
        assert client.health().status == "ok"

    # Assert
    with pytest.raises(GoVecClientClosedError):
        client.health()
