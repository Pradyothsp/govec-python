import pytest

from govec.client import GoVecClient


@pytest.mark.e2e
def test_flush__called__reports_flushed(govec_grpc_client: GoVecClient) -> None:
    # "flushed", matching REST. gRPC used to answer "ok" here, so the status a
    # caller got back depended on the protocol they picked.
    response = govec_grpc_client.flush()

    # Assert
    assert response.status == "flushed"
