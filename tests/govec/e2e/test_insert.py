import random

import pytest

from govec.client import GoVecClient
from govec.models import InsertRequest, SparseVector


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


@pytest.mark.e2e
def test_insert_many(govec_e2e_client: GoVecClient):
    # Arrange
    dims = govec_e2e_client.dimensions
    sparse_vector = SparseVector(indices=[0, 10, 42], values=[0.5, 0.3, 0.2])

    requests = [
        InsertRequest(
            id=f"test-insert-many-{i:03}",
            vector=[random.random() for _ in range(dims)],
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
def test_insert_many_with_error(govec_e2e_client: GoVecClient):
    # Arrange
    dims = govec_e2e_client.dimensions
    sparse_vector = SparseVector(indices=[0, 10, 42], values=[0.5, 0.3, 0.2])

    requests = [
        InsertRequest(
            id=f"test-insert-many-err-{i:03}",
            vector=[random.random() for _ in range(dims)],
            sparse_vector=sparse_vector,
        )
        for i in range(9)
    ]
    # One vector with wrong dimensions — server should reject it
    requests.append(
        InsertRequest(id="test-insert-many-err-bad", vector=[0.1, 0.2, 0.3], sparse_vector=sparse_vector)
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
