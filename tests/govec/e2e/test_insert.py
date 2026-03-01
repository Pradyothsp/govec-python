import random

import pytest

from govec.client import GoVecClient
from govec.models import SparseVector


@pytest.mark.e2e
def test_insert(govec_e2e_client: GoVecClient):
    # Arrange
    dims = govec_e2e_client.dimensions

    dense_vector = [random.random() for _ in range(dims)]
    sparse_vector = SparseVector(
        indices=[0, 10, 42],
        values=[0.5, 0.3, 0.2],
    )

    # Act
    result = govec_e2e_client.insert(
        id="test-insert-001",
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
    )

    # Assert
    assert result is True
