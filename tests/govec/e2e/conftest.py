import random
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast
from uuid import uuid4

import pytest

from govec.models import InsertRequest
from tests.govec.sync_or_async import (
    CLIENT_KINDS,
    AnyClient,
    ClientKind,
    connect_client,
    settle,
    shut,
)

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


REST_PORT = 9697
GRPC_PORT = 9698


@pytest.fixture(params=CLIENT_KINDS)
def client_kind(request: pytest.FixtureRequest) -> ClientKind:
    """Which client every e2e test runs on: each runs once per kind.

    Shared by both client fixtures, so a test that compares REST with gRPC
    gets two runs (sync with sync, async with async), not four.
    """
    return cast(ClientKind, request.param)


# Function-scoped, so one handshake per test. A session-scoped async client
# would have to share one event loop across the whole session, and against a
# local server the handshake costs a millisecond.
@pytest.fixture
async def govec_e2e_client(client_kind: ClientKind) -> AsyncIterator[AnyClient]:
    client = await connect_client(client_kind, "localhost", REST_PORT, "rest")
    yield client

    await shut(client)


@pytest.fixture
async def govec_grpc_client(client_kind: ClientKind) -> AsyncIterator[AnyClient]:
    client = await connect_client(client_kind, "localhost", GRPC_PORT, "grpc")
    yield client

    await shut(client)


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
    govec_grpc_client: AnyClient,
    build_insert_request: Callable[..., InsertRequest],
) -> Callable[..., Awaitable[InsertRequest]]:
    """Inserts a vector over gRPC and returns the request that produced it."""

    async def _insert(metadata: dict[str, Any] | None = None) -> InsertRequest:
        request = build_insert_request(metadata=metadata)
        await settle(
            govec_grpc_client.insert(
                vector_id=request.id,
                dense_vector=request.vector,
                metadata=request.metadata,
            )
        )
        return request

    return _insert
