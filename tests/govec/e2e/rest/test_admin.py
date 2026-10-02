from collections.abc import Callable

import pytest

from govec.client import GoVecClient

# flush and reset had gRPC e2e coverage and no REST equivalent, so the REST
# implementations of both were only ever exercised by hand.


@pytest.mark.e2e
def test_flush__called__reports_flushed(govec_e2e_client: GoVecClient) -> None:
    # "flushed", not "ok" -- the two transports disagree on the status string
    # for the same operation, and this pins what REST actually says today.
    # gRPC answers "ok" here, and likewise where REST says "reset",
    # "inserted" and "deleted". See govec-notes FIXES.md; until that is
    # settled server-side, `response.status == "ok"` is a check that passes
    # over gRPC and fails over REST.
    response = govec_e2e_client.flush()

    # Assert
    assert response.status == "flushed"


@pytest.mark.e2e
def test_reset__index_has_vectors__clears_every_one(
    govec_e2e_client: GoVecClient, dense_vector: Callable[[], list[float]]
) -> None:
    # Arrange
    govec_e2e_client.insert(vector_id="rest-reset-me", dense_vector=dense_vector())
    assert govec_e2e_client.get_stats().vector_count > 0

    # Act
    govec_e2e_client.reset()

    # Assert
    assert govec_e2e_client.get_stats().vector_count == 0


@pytest.mark.e2e
def test_reset__afterwards__the_index_still_accepts_inserts(
    govec_e2e_client: GoVecClient, dense_vector: Callable[[], list[float]]
) -> None:
    # Arrange
    govec_e2e_client.reset()

    # Act
    govec_e2e_client.insert(vector_id="rest-after-reset", dense_vector=dense_vector())

    # Assert
    assert govec_e2e_client.get_by_id("rest-after-reset") is not None
