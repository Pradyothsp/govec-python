from collections.abc import Callable
from typing import Any

import pytest

from govec.client import GoVecClient
from govec.models import InsertRequest


@pytest.mark.e2e
def test_search__exact_query_vector__returns_that_vector_first(
    govec_grpc_client: GoVecClient,
    inserted_vector: Callable[..., InsertRequest],
) -> None:
    # Arrange
    request = inserted_vector()

    # Act
    results = govec_grpc_client.search(dense_vector=request.vector, k=1)

    # Assert
    assert len(results) == 1
    assert results[0].id == request.id
    assert results[0].score == pytest.approx(1.0, abs=1e-5)


@pytest.mark.e2e
def test_search__metadata_filter__returns_only_matching_vectors(
    govec_grpc_client: GoVecClient,
    inserted_vector: Callable[..., InsertRequest],
) -> None:
    # Arrange
    tier = f"tier-{id(object())}"
    wanted = inserted_vector(metadata={"tier": tier})
    inserted_vector(metadata={"tier": f"other-{tier}"})

    # Act
    results = govec_grpc_client.search(
        dense_vector=wanted.vector, k=10, filter={"tier": tier}
    )

    # Assert
    assert [r.id for r in results] == [wanted.id]


@pytest.mark.e2e
def test_search__metadata_on_result__round_trips_through_protobuf_struct(
    govec_grpc_client: GoVecClient,
    inserted_vector: Callable[..., InsertRequest],
) -> None:
    # Arrange
    metadata: dict[str, Any] = {
        "label": "example",
        "active": True,
        "tags": ["a", "b"],
        "nested": {"key": "value"},
    }
    request = inserted_vector(metadata=metadata)

    # Act
    results = govec_grpc_client.search(dense_vector=request.vector, k=1)

    # Assert
    assert results[0].meta == metadata


@pytest.mark.e2e
def test_search__integer_metadata__comes_back_as_float(
    govec_grpc_client: GoVecClient,
    inserted_vector: Callable[..., InsertRequest],
) -> None:
    # Arrange -- protobuf Struct stores every number as a double, so ints
    # cannot survive a gRPC round trip. REST (JSON) preserves them.
    request = inserted_vector(metadata={"year": 2024})

    # Act
    results = govec_grpc_client.search(dense_vector=request.vector, k=1)

    # Assert
    meta = results[0].meta
    assert meta is not None
    assert meta["year"] == 2024.0
    assert isinstance(meta["year"], float)


@pytest.mark.e2e
def test_search__vector_without_metadata__returns_no_meta(
    govec_grpc_client: GoVecClient,
    inserted_vector: Callable[..., InsertRequest],
) -> None:
    # A protobuf map is always present, so gRPC reports "no metadata" as an
    # empty map where REST omits the key. Both must surface as None, or the
    # transport a caller picked would change what they have to check for.
    request = inserted_vector()

    # Act
    results = govec_grpc_client.search(dense_vector=request.vector, k=1)

    # Assert
    assert results[0].id == request.id
    assert results[0].meta is None
