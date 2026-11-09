from collections.abc import Awaitable, Callable

import pytest

from govec.models import InsertRequest
from tests.govec.sync_or_async import AnyClient, settle

# Every test runs once per client kind; see `client_kind` in e2e/conftest.py.
pytestmark = pytest.mark.anyio


@pytest.mark.e2e
async def test_get_stats__after_an_insert__counts_at_least_that_vector(
    govec_grpc_client: AnyClient,
    inserted_vector: Callable[..., Awaitable[InsertRequest]],
) -> None:
    # Arrange
    before = (await settle(govec_grpc_client.get_stats())).vector_count

    # Act
    await inserted_vector()
    after = (await settle(govec_grpc_client.get_stats())).vector_count

    # Assert
    assert after == before + 1
