import pytest

from tests.govec.sync_or_async import AnyClient, settle

# Every test runs once per client kind; see `client_kind` in e2e/conftest.py.
pytestmark = pytest.mark.anyio


@pytest.mark.e2e
async def test_health__server_running__reports_ok(govec_grpc_client: AnyClient) -> None:
    # Arrange / Act
    response = await settle(govec_grpc_client.health())

    # Assert
    assert response.status == "ok"
