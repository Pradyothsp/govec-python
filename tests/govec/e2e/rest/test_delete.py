import random

import pytest

from govec.models import SparseVector
from tests.govec.sync_or_async import AnyClient, settle

# Every test runs once per client kind; see `client_kind` in e2e/conftest.py.
pytestmark = pytest.mark.anyio


@pytest.mark.e2e
async def test_delete__existing_vector__returns_true(govec_e2e_client: AnyClient):
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

    # Act
    results = await settle(govec_e2e_client.delete(vector_id="test-search-001"))

    # Assert
    assert results is True
