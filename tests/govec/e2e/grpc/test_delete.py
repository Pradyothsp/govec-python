from collections.abc import Awaitable, Callable

import pytest

from govec.exceptions import GoVecAPIError
from govec.models import InsertRequest
from tests.govec.sync_or_async import AnyClient, settle

# Every test runs once per client kind; see `client_kind` in e2e/conftest.py.
pytestmark = pytest.mark.anyio


@pytest.mark.e2e
async def test_delete__existing_vector__returns_true(
    govec_grpc_client: AnyClient,
    inserted_vector: Callable[..., Awaitable[InsertRequest]],
) -> None:
    # Arrange
    request = await inserted_vector()

    # Act
    result = await settle(govec_grpc_client.delete(request.id))

    # Assert
    assert result is True


@pytest.mark.e2e
async def test_delete__missing_vector__raises_api_error(
    govec_grpc_client: AnyClient,
) -> None:
    # Arrange
    missing_id = "grpc-definitely-not-inserted"

    # Act / Assert
    with pytest.raises(GoVecAPIError):
        await settle(govec_grpc_client.delete(missing_id))


@pytest.mark.e2e
async def test_delete__missing_vector__error_is_labelled_grpc_not_http(
    govec_grpc_client: AnyClient,
) -> None:
    # Arrange / Act
    with pytest.raises(GoVecAPIError) as excinfo:
        await settle(
            govec_grpc_client.delete("grpc-definitely-not-inserted-label-check")
        )

    # Assert -- the code is a gRPC status, so calling it HTTP is wrong.
    assert excinfo.value.status_label == "gRPC"
    assert "HTTP" not in str(excinfo.value)
