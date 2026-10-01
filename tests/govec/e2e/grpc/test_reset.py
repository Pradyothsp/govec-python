from collections.abc import Callable

import pytest

from govec.client import GoVecClient
from govec.models import InsertRequest, ResetResponse


@pytest.mark.e2e
def test_reset__index_has_vectors__clears_every_one(
    govec_grpc_client: GoVecClient,
    inserted_vector: Callable[..., InsertRequest],
) -> None:
    # Arrange
    request = inserted_vector()
    assert govec_grpc_client.get_stats().vector_count > 0

    # Act
    result = govec_grpc_client.reset()

    # Assert
    assert isinstance(result, ResetResponse)
    assert govec_grpc_client.get_stats().vector_count == 0
    assert govec_grpc_client.get_by_id(request.id) is None


@pytest.mark.e2e
def test_reset__afterwards__the_index_still_accepts_inserts(
    govec_grpc_client: GoVecClient,
    inserted_vector: Callable[..., InsertRequest],
) -> None:
    # Arrange -- reset clears the ID mapper and the WAL as well as the store,
    # so the interesting question is whether the index is usable afterward,
    # not just empty
    inserted_vector()
    govec_grpc_client.reset()

    # Act
    request = inserted_vector()
    results = govec_grpc_client.search(dense_vector=request.vector, k=5)

    # Assert
    assert [r.id for r in results] == [request.id]
