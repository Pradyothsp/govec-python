import pytest

from tests.govec.sync_or_async import AnyClient, settle

# Every test runs once per client kind; see `client_kind` in e2e/conftest.py.
pytestmark = pytest.mark.anyio


@pytest.mark.e2e
async def test_flush__called__reports_flushed(govec_grpc_client: AnyClient) -> None:
    # "flushed", matching REST. gRPC used to answer "ok" here, so the status a
    # caller got back depended on the protocol they picked.

    # Act
    response = await settle(govec_grpc_client.flush())

    # Assert
    assert response.status == "flushed"
