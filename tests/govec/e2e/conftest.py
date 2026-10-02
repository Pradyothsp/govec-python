import random
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest

from govec.client import GoVecClient
from govec.models import InsertRequest

# The width every e2e test uses, REST and gRPC alike.
#
# Deliberately a constant rather than govec_e2e_client.dimensions: the client
# fetches that once during its preflight handshake, and a server with no
# configured engine.dimensions reports 0 until its first insert. Tests that
# built vectors from it were producing *empty* vectors and passing vacuously.
#
# Both suites must also agree on this number. They share one server and the
# server rejects a vector whose width differs from the index's, so a
# disagreement would fail whichever suite ran second. Reset is not a way out
# when the server has a configured engine.dimensions: that width is the
# operator's choice and survives a reset, and only a width the index learned
# from its first insert is released.
E2E_DIMENSIONS = 1536


@pytest.fixture(scope="session")
def govec_e2e_client() -> GoVecClient:
    return GoVecClient(
        host="localhost", port=8000, api_key="", protocol="rest", tls=False
    )


@pytest.fixture(scope="session")
def govec_grpc_client() -> GoVecClient:
    return GoVecClient(
        host="localhost", port=50051, api_key="", protocol="grpc", tls=False
    )


@pytest.fixture
def dense_vector() -> Callable[[], list[float]]:
    def _build() -> list[float]:
        return [random.random() for _ in range(E2E_DIMENSIONS)]

    return _build


@pytest.fixture
def build_insert_request(
    dense_vector: Callable[[], list[float]],
) -> Callable[..., InsertRequest]:
    """Builds an InsertRequest with a unique id, so tests stay independent.

    Both suites share one server for the whole session, and the gRPC suite now
    resets it mid-run -- so every test must insert the data it asserts on
    rather than relying on anything a previous test left behind.
    """

    def _build(
        vector_id: str | None = None,
        vector: list[float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> InsertRequest:
        return InsertRequest(
            id=vector_id or f"grpc-{uuid4().hex[:12]}",
            vector=vector if vector is not None else dense_vector(),
            metadata=metadata,
        )

    return _build


@pytest.fixture
def inserted_vector(
    govec_grpc_client: GoVecClient,
    build_insert_request: Callable[..., InsertRequest],
) -> Callable[..., InsertRequest]:
    """Inserts a vector over gRPC and returns the request that produced it."""

    def _insert(metadata: dict[str, Any] | None = None) -> InsertRequest:
        request = build_insert_request(metadata=metadata)
        govec_grpc_client.insert(
            vector_id=request.id,
            dense_vector=request.vector,
            metadata=request.metadata,
        )
        return request

    return _insert
