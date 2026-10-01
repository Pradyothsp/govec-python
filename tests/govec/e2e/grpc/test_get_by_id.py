from collections.abc import Callable

import pytest

from govec.client import GoVecClient
from govec.models import GetByIdResponse, InsertRequest, SparseVector
from tests.govec.e2e.conftest import E2E_DIMENSIONS


@pytest.mark.e2e
def test_get_by_id__existing_vector__returns_the_stored_record(
    govec_grpc_client: GoVecClient,
    inserted_vector: Callable[..., InsertRequest],
) -> None:
    # Arrange
    request = inserted_vector()

    # Act
    result = govec_grpc_client.get_by_id(request.id)

    # Assert
    assert isinstance(result, GetByIdResponse)
    assert result.id == request.id
    assert len(result.vector) == E2E_DIMENSIONS


@pytest.mark.e2e
def test_get_by_id__vector_has_metadata__returns_the_metadata(
    govec_grpc_client: GoVecClient,
    inserted_vector: Callable[..., InsertRequest],
) -> None:
    # Arrange
    request = inserted_vector(metadata={"source": "grpc", "category": "e2e"})

    # Act
    result = govec_grpc_client.get_by_id(request.id)

    # Assert
    assert result is not None
    assert result.metadata == {"source": "grpc", "category": "e2e"}


@pytest.mark.e2e
def test_get_by_id__vector_has_a_sparse_component__returns_it(
    govec_grpc_client: GoVecClient,
    build_insert_request: Callable[..., InsertRequest],
) -> None:
    # Arrange
    request = build_insert_request()
    sparse_vector = SparseVector(indices=[0, 10, 42], values=[0.5, 0.3, 0.2])
    govec_grpc_client.insert(
        vector_id=request.id,
        dense_vector=request.vector,
        sparse_vector=sparse_vector,
    )

    # Act
    result = govec_grpc_client.get_by_id(request.id)

    # Assert
    assert result is not None
    assert result.sparse_vector is not None
    assert result.sparse_vector.indices == [0, 10, 42]
    assert result.sparse_vector.values == pytest.approx([0.5, 0.3, 0.2])


@pytest.mark.e2e
def test_get_by_id__dense_only_vector__returns_no_sparse_component(
    govec_grpc_client: GoVecClient,
    inserted_vector: Callable[..., InsertRequest],
) -> None:
    # Arrange -- a vector inserted without a sparse component
    request = inserted_vector()

    # Act
    result = govec_grpc_client.get_by_id(request.id)

    # Assert -- None, not an empty SparseVector, which the model rejects
    assert result is not None
    assert result.sparse_vector is None


@pytest.mark.e2e
def test_get_by_id__missing_vector__returns_none(
    govec_grpc_client: GoVecClient,
) -> None:
    # Act -- the server answers NOT_FOUND; the transport translates it so both
    # protocols behave the same way behind the client
    result = govec_grpc_client.get_by_id("grpc-no-such-id-xyz")

    # Assert
    assert result is None
