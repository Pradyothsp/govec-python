from collections.abc import Callable

import pytest

from govec.client import GoVecClient
from govec.models import InsertRequest


@pytest.mark.e2e
def test_get_stats__after_an_insert__counts_at_least_that_vector(
    govec_grpc_client: GoVecClient,
    inserted_vector: Callable[..., InsertRequest],
) -> None:
    # Arrange
    before = govec_grpc_client.get_stats().vector_count

    # Act
    inserted_vector()
    after = govec_grpc_client.get_stats().vector_count

    # Assert
    assert after == before + 1
