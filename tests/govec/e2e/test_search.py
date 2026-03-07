import random

import pytest

from govec.client import GoVecClient
from govec.models import SparseVector


@pytest.mark.e2e
def test_search(govec_e2e_client: GoVecClient):
    dense_vector = [random.random() for _ in range(1536)]
    sparse_vector = SparseVector(indices=[0, 10, 42], values=[0.5, 0.3, 0.2])

    # Arrange — insert a known vector
    govec_e2e_client.insert(
        vector_id="test-search-001",
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
    )

    # Act — search with the same vector (should be the closest match)
    results = govec_e2e_client.search(dense_vector=dense_vector, k=1)

    # Assert
    assert len(results) == 1
    assert results[0].id == "test-search-001"
