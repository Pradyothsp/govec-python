import random

import pytest

from govec.client import GoVecClient
from govec.models import GetByIdResponse, SparseVector
from tests.govec.e2e.conftest import E2E_DIMENSIONS


@pytest.mark.e2e
def test_get_by_id__existing_vector__returns_vector_and_sparse(
    govec_e2e_client: GoVecClient,
):
    # Arrange — insert a known vector
    dense_vector = [random.random() for _ in range(E2E_DIMENSIONS)]
    sparse_vector = SparseVector(indices=[0, 10, 42], values=[0.5, 0.3, 0.2])

    govec_e2e_client.insert(
        vector_id="test-get-by-id-001",
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
    )

    # Act
    result = govec_e2e_client.get_by_id("test-get-by-id-001")

    # Assert
    assert isinstance(result, GetByIdResponse)
    assert result.id == "test-get-by-id-001"
    assert len(result.vector) == E2E_DIMENSIONS
    assert isinstance(result.sparse_vector, SparseVector)
    assert result.sparse_vector.indices == [0, 10, 42]
    assert result.sparse_vector.values == [0.5, 0.3, 0.2]


@pytest.mark.e2e
def test_get_by_id__vector_has_metadata__returns_the_metadata(
    govec_e2e_client: GoVecClient,
):
    # Arrange
    dense_vector = [random.random() for _ in range(E2E_DIMENSIONS)]
    sparse_vector = SparseVector(indices=[1, 5], values=[0.7, 0.3])
    metadata = {"source": "test", "category": "e2e"}

    govec_e2e_client.insert(
        vector_id="test-get-by-id-meta-001",
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        metadata=metadata,
    )

    # Act
    result = govec_e2e_client.get_by_id("test-get-by-id-meta-001")

    # Assert
    assert isinstance(result, GetByIdResponse)
    assert result.id == "test-get-by-id-meta-001"
    assert result.metadata == metadata


@pytest.mark.e2e
def test_get_by_id__missing_vector__returns_none(govec_e2e_client: GoVecClient):
    # Act
    result = govec_e2e_client.get_by_id("non-existent-id-xyz")

    # Assert
    assert result is None
