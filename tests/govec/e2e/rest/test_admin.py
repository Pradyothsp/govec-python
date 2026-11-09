from collections.abc import Callable

import pytest

from tests.govec.sync_or_async import AnyClient, settle

# Every test runs once per client kind; see `client_kind` in e2e/conftest.py.
pytestmark = pytest.mark.anyio


# flush and reset had gRPC e2e coverage and no REST equivalent, so the REST
# implementations of both were only ever exercised by hand.


@pytest.mark.e2e
async def test_flush__called__reports_flushed(govec_e2e_client: AnyClient) -> None:
    # The gRPC suite asserts the same string, which is the point -- the server
    # used to answer "ok" over gRPC and "flushed" over REST for this one call.

    # Act
    response = await settle(govec_e2e_client.flush())

    # Assert
    assert response.status == "flushed"


@pytest.mark.e2e
async def test_reset__index_has_vectors__clears_every_one(
    govec_e2e_client: AnyClient, dense_vector: Callable[[], list[float]]
) -> None:
    # Arrange
    await settle(
        govec_e2e_client.insert(vector_id="rest-reset-me", dense_vector=dense_vector())
    )
    assert (await settle(govec_e2e_client.get_stats())).vector_count > 0

    # Act
    await settle(govec_e2e_client.reset())

    # Assert
    assert (await settle(govec_e2e_client.get_stats())).vector_count == 0


@pytest.mark.e2e
async def test_reset__afterwards__the_index_still_accepts_inserts(
    govec_e2e_client: AnyClient, dense_vector: Callable[[], list[float]]
) -> None:
    # Arrange
    await settle(govec_e2e_client.reset())

    # Act
    await settle(
        govec_e2e_client.insert(
            vector_id="rest-after-reset", dense_vector=dense_vector()
        )
    )

    # Assert
    assert await settle(govec_e2e_client.get_by_id("rest-after-reset")) is not None
