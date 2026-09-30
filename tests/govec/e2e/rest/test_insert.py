import random

import pytest

from govec.client import GoVecClient
from govec.models import InsertRequest, SparseVector
from tests.govec.e2e.conftest import E2E_DIMENSIONS


@pytest.mark.e2e
def test_insert__dense_and_sparse_vector__returns_true(govec_e2e_client: GoVecClient):
    # Arrange
    dense_vector = [random.random() for _ in range(E2E_DIMENSIONS)]
    sparse_vector = SparseVector(
        indices=[0, 10, 42],
        values=[0.5, 0.3, 0.2],
    )

    # Act
    result = govec_e2e_client.insert(
        vector_id="test-insert-001",
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
    )

    # Assert
    assert result is True


@pytest.mark.e2e
def test_insert_many__batch_of_vectors__inserts_all_without_errors(
    govec_e2e_client: GoVecClient,
):
    # Arrange
    sparse_vector = SparseVector(indices=[0, 10, 42], values=[0.5, 0.3, 0.2])

    requests = [
        InsertRequest(
            id=f"test-insert-many-{i:03}",
            vector=[random.random() for _ in range(E2E_DIMENSIONS)],
            sparse_vector=sparse_vector,
        )
        for i in range(10)
    ]

    # Act
    result = govec_e2e_client.insert_many(requests)

    # Assert
    assert result.inserted_count == len(requests)
    assert result.errors == []


@pytest.mark.e2e
def test_insert_many__one_vector_has_wrong_width__reports_only_that_one(
    govec_e2e_client: GoVecClient,
):
    # Arrange
    sparse_vector = SparseVector(indices=[0, 10, 42], values=[0.5, 0.3, 0.2])

    requests = [
        InsertRequest(
            id=f"test-insert-many-err-{i:03}",
            vector=[random.random() for _ in range(E2E_DIMENSIONS)],
            sparse_vector=sparse_vector,
        )
        for i in range(9)
    ]
    # One vector with wrong dimensions — server should reject it
    requests.append(
        InsertRequest(
            id="test-insert-many-err-bad",
            vector=[0.1, 0.2, 0.3],
            sparse_vector=sparse_vector,
        )
    )

    # Bypass client-side dimension check so the bad vector reaches the server
    original_enable_mmap = govec_e2e_client.enable_mmap
    govec_e2e_client.enable_mmap = False
    try:
        result = govec_e2e_client.insert_many(requests)
    finally:
        govec_e2e_client.enable_mmap = original_enable_mmap

    # Assert
    assert result.inserted_count == 9
    assert len(result.errors) == 1
    assert result.errors[0].id == "test-insert-many-err-bad"
