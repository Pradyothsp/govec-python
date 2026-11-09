from collections.abc import Awaitable, Callable

import pytest

from govec.models import GetByIdResponse, InsertRequest, SparseVector
from tests.govec.e2e.conftest import E2E_DIMENSIONS
from tests.govec.sync_or_async import AnyClient, settle

# Every test runs once per client kind; see `client_kind` in e2e/conftest.py.
pytestmark = pytest.mark.anyio


@pytest.mark.e2e
async def test_get_by_id__existing_vector__returns_the_stored_record(
    govec_grpc_client: AnyClient,
    inserted_vector: Callable[..., Awaitable[InsertRequest]],
) -> None:
    # Arrange
    request = await inserted_vector()

    # Act
    result = await settle(govec_grpc_client.get_by_id(request.id))

    # Assert
    assert isinstance(result, GetByIdResponse)
    assert result.id == request.id
    assert len(result.vector) == E2E_DIMENSIONS


@pytest.mark.e2e
async def test_get_by_id__vector_has_metadata__returns_the_metadata(
    govec_grpc_client: AnyClient,
    inserted_vector: Callable[..., Awaitable[InsertRequest]],
) -> None:
    # Arrange
    request = await inserted_vector(metadata={"source": "grpc", "category": "e2e"})

    # Act
    result = await settle(govec_grpc_client.get_by_id(request.id))

    # Assert
    assert result is not None
    assert result.metadata == {"source": "grpc", "category": "e2e"}


@pytest.mark.e2e
async def test_get_by_id__vector_has_a_sparse_component__returns_it(
    govec_grpc_client: AnyClient,
    build_insert_request: Callable[..., InsertRequest],
) -> None:
    # Arrange
    request = build_insert_request()
    sparse_vector = SparseVector(indices=[0, 10, 42], values=[0.5, 0.3, 0.2])
    await settle(
        govec_grpc_client.insert(
            vector_id=request.id,
            dense_vector=request.vector,
            sparse_vector=sparse_vector,
        )
    )

    # Act
    result = await settle(govec_grpc_client.get_by_id(request.id))

    # Assert
    assert result is not None
    assert result.sparse_vector is not None
    assert result.sparse_vector.indices == [0, 10, 42]
    assert result.sparse_vector.values == pytest.approx([0.5, 0.3, 0.2])


@pytest.mark.e2e
async def test_get_by_id__dense_only_vector__returns_no_sparse_component(
    govec_grpc_client: AnyClient,
    inserted_vector: Callable[..., Awaitable[InsertRequest]],
) -> None:
    # Arrange -- a vector inserted without a sparse component
    request = await inserted_vector()

    # Act
    result = await settle(govec_grpc_client.get_by_id(request.id))

    # Assert -- None, not an empty SparseVector, which the model rejects
    assert result is not None
    assert result.sparse_vector is None


@pytest.mark.e2e
async def test_get_by_id__missing_vector__returns_none(
    govec_grpc_client: AnyClient,
) -> None:
    # Act -- the server answers NOT_FOUND; the transport translates it so both
    # protocols behave the same way behind the client
    result = await settle(govec_grpc_client.get_by_id("grpc-no-such-id-xyz"))

    # Assert
    assert result is None
