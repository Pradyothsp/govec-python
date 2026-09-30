import pytest

from govec.client import GoVecClient


@pytest.mark.e2e
def test_flush__called__reports_ok(govec_grpc_client: GoVecClient) -> None:
    # Arrange / Act
    response = govec_grpc_client.flush()

    # Assert
    assert response.status == "ok"
