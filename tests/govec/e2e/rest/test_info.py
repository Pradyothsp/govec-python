from collections.abc import Callable

import pytest

from govec.client import GoVecClient
from govec.models import DistanceMetric, IndexType

# The gRPC suite covered info and stats; REST did not, so nothing checked that
# the REST transport parsed /info into the same shape.


@pytest.mark.e2e
def test_server_info__server_running__returns_server_config(
    govec_e2e_client: GoVecClient,
) -> None:
    # Arrange / Act
    info = govec_e2e_client.info()

    # Assert
    assert info.index_type in ("brute", "hnsw")
    assert info.distance_metric in ("cosine", "euclidean")
    assert info.vector_count >= 0


@pytest.mark.e2e
def test_server_info__index_type__is_one_the_sdk_declares(
    govec_e2e_client: GoVecClient,
) -> None:
    # The SDK's IndexType literal said "brute_force", which the server never
    # sends -- it says "brute". Pinned against a live server so the declared
    # type cannot drift from the real one again.
    declared_index_types = set(IndexType.__args__)
    declared_metrics = set(DistanceMetric.__args__)

    # Act
    info = govec_e2e_client.info()

    # Assert
    assert info.index_type in declared_index_types
    assert info.distance_metric in declared_metrics


@pytest.mark.e2e
def test_get_stats__after_an_insert__counts_at_least_that_vector(
    govec_e2e_client: GoVecClient, dense_vector: Callable[[], list[float]]
) -> None:
    # Arrange
    govec_e2e_client.insert(vector_id="rest-stats-me", dense_vector=dense_vector())

    # Act
    stats = govec_e2e_client.get_stats()

    # Assert
    assert stats.vector_count >= 1
