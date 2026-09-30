import pytest

from govec.client import GoVecClient


@pytest.mark.e2e
def test_health__server_running__reports_ok(govec_grpc_client: GoVecClient) -> None:
    # Arrange / Act
    response = govec_grpc_client.health()

    # Assert
    assert response.status == "ok"
