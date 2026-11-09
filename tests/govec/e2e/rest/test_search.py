import random

import pytest

from govec.models import SparseVector
from tests.govec.sync_or_async import AnyClient, settle

# Every test runs once per client kind; see `client_kind` in e2e/conftest.py.
pytestmark = pytest.mark.anyio


@pytest.mark.e2e
async def test_search__exact_query_vector__returns_that_vector_first(
    govec_e2e_client: AnyClient,
):
    # Arrange — insert a known vector
    dense_vector = [random.random() for _ in range(1536)]
    sparse_vector = SparseVector(indices=[0, 10, 42], values=[0.5, 0.3, 0.2])
    await settle(
        govec_e2e_client.insert(
            vector_id="test-search-001",
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
        )
    )

    # Act — search with the same vector (should be the closest match)
    results = await settle(govec_e2e_client.search(dense_vector=dense_vector, k=1))

    # Assert
    assert len(results) == 1
    assert results[0].id == "test-search-001"


@pytest.mark.e2e
async def test_search__vector_without_metadata__returns_no_meta(
    govec_e2e_client: AnyClient,
):
    # The server omits "meta" for a vector with no metadata. SearchResponse used
    # to require the key, so parsing a result without it raised TypeError.

    # Arrange
    dense_vector = [random.random() for _ in range(1536)]
    await settle(
        govec_e2e_client.insert(
            vector_id="test-search-no-meta", dense_vector=dense_vector
        )
    )

    # Act
    results = await settle(govec_e2e_client.search(dense_vector=dense_vector, k=1))

    # Assert
    assert results[0].id == "test-search-no-meta"
    assert results[0].meta is None
