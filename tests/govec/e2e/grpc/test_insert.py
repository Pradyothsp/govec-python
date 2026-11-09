from collections.abc import Callable

import pytest

from govec.models import InsertRequest
from tests.govec.sync_or_async import AnyClient, settle

# Every test runs once per client kind; see `client_kind` in e2e/conftest.py.
pytestmark = pytest.mark.anyio


@pytest.mark.e2e
async def test_insert__dense_vector__returns_true(
    govec_grpc_client: AnyClient,
    build_insert_request: Callable[..., InsertRequest],
) -> None:
    # Arrange
    request = build_insert_request()

    # Act
    result = await settle(
        govec_grpc_client.insert(vector_id=request.id, dense_vector=request.vector)
    )

    # Assert
    assert result is True


@pytest.mark.e2e
async def test_insert_many__batch_of_vectors__inserts_all_without_errors(
    govec_grpc_client: AnyClient,
    build_insert_request: Callable[..., InsertRequest],
) -> None:
    # Arrange
    requests = [build_insert_request() for _ in range(10)]

    # Act
    result = await settle(govec_grpc_client.insert_many(requests))

    # Assert
    assert result.inserted_count == len(requests)
    assert result.errors == []
