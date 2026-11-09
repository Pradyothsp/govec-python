from collections.abc import Awaitable, Callable

import pytest

from govec.models import InsertRequest, ResetResponse
from tests.govec.sync_or_async import AnyClient, settle

# Every test runs once per client kind; see `client_kind` in e2e/conftest.py.
pytestmark = pytest.mark.anyio


@pytest.mark.e2e
async def test_reset__index_has_vectors__clears_every_one(
    govec_grpc_client: AnyClient,
    inserted_vector: Callable[..., Awaitable[InsertRequest]],
) -> None:
    # Arrange
    request = await inserted_vector()
    assert (await settle(govec_grpc_client.get_stats())).vector_count > 0

    # Act
    result = await settle(govec_grpc_client.reset())

    # Assert
    assert isinstance(result, ResetResponse)
    assert (await settle(govec_grpc_client.get_stats())).vector_count == 0
    assert await settle(govec_grpc_client.get_by_id(request.id)) is None


@pytest.mark.e2e
async def test_reset__afterwards__the_index_still_accepts_inserts(
    govec_grpc_client: AnyClient,
    inserted_vector: Callable[..., Awaitable[InsertRequest]],
) -> None:
    # Arrange -- reset clears the ID mapper and the WAL as well as the store,
    # so the interesting question is whether the index is usable afterward,
    # not just empty
    await inserted_vector()
    await settle(govec_grpc_client.reset())

    # Act
    request = await inserted_vector()
    results = await settle(govec_grpc_client.search(dense_vector=request.vector, k=5))

    # Assert
    assert [r.id for r in results] == [request.id]
