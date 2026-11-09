import socket
from collections.abc import Callable
from typing import NamedTuple, cast

import grpc
import pytest
from google.protobuf.message import Message

from govec.exceptions import (
    GoVecAPIError,
    GoVecClientClosedError,
    GoVecConnectionError,
)
from govec.models import (
    BatchInsertResponse,
    DeleteResponse,
    FlushResponse,
    GetByIdResponse,
    GetStatsResponse,
    HealthResponse,
    InfoResponse,
    InsertRequest,
    InsertResponse,
    ResetResponse,
    SearchRequest,
    SearchResponse,
)
from govec.proto import govec_pb2
from govec.transport.base import Timeouts
from govec.transport.grpc import AsyncGRPCTransport, GRPCTransport
from tests.govec.grpc_server import Failure, RunningServer
from tests.govec.sync_or_async import settle, shut

type AnyTransport = GRPCTransport | AsyncGRPCTransport
type BuildTransport = Callable[..., AnyTransport]

# Every test taking `grpc_transport` runs against both gRPC transports, over a
# real channel to the in-process `grpc_server`.
pytestmark = pytest.mark.anyio


# --- every operation ----------------------------------------------------------
#
# The sync and async classes each spell out every RPC and its timeout, so a
# slip in one would otherwise surface only in the e2e suites.


class _Operation(NamedTuple):
    call: Callable[[AnyTransport], object]
    rpc: str
    reply: Message
    expected: object


_REQUEST = InsertRequest(id="a", vector=[1.0])

_OPERATIONS = {
    "health": _Operation(
        lambda t: t.health(),
        "Health",
        govec_pb2.HealthResponse(status="ok"),
        HealthResponse(status="ok"),
    ),
    "server_info": _Operation(
        lambda t: t.server_info(),
        "Info",
        govec_pb2.InfoResponse(
            quantization="none",
            index_type="hnsw",
            distance_metric="euclidean",
            dimensions=3,
            vector_count=2,
            enable_mmap=True,
            version="v1",
        ),
        InfoResponse(
            quantization="none",
            index_type="hnsw",
            distance_metric="euclidean",
            dimensions=3,
            vector_count=2,
            enable_mmap=True,
            version="v1",
        ),
    ),
    "get_stats": _Operation(
        lambda t: t.get_stats(),
        "Stats",
        govec_pb2.StatsResponse(vector_count=3),
        GetStatsResponse(vector_count=3),
    ),
    "flush": _Operation(
        lambda t: t.flush(),
        "Flush",
        govec_pb2.FlushResponse(status="flushed"),
        FlushResponse(status="flushed"),
    ),
    "reset": _Operation(
        lambda t: t.reset(),
        "Reset",
        govec_pb2.ResetResponse(status="reset"),
        ResetResponse(status="reset"),
    ),
    "get_by_id": _Operation(
        lambda t: t.get_by_id("a"),
        "GetByID",
        govec_pb2.GetByIDResponse(id="a", vector=[1.0]),
        GetByIdResponse(id="a", vector=[1.0], sparse_vector=None, metadata=None),
    ),
    "insert": _Operation(
        lambda t: t.insert(_REQUEST),
        "Insert",
        govec_pb2.InsertResponse(status="inserted"),
        InsertResponse(status="inserted"),
    ),
    "insert_batch": _Operation(
        lambda t: t.insert_batch([_REQUEST]),
        "BatchInsert",
        govec_pb2.BatchInsertResponse(inserted_count=1),
        BatchInsertResponse(inserted_count=1, errors=[]),
    ),
    "search": _Operation(
        lambda t: t.search(SearchRequest(vector=[1.0], k=1)),
        "Search",
        govec_pb2.SearchResponse(results=[govec_pb2.SearchResult(id="a", score=0.5)]),
        [SearchResponse(id="a", score=0.5, meta=None)],
    ),
    "delete": _Operation(
        lambda t: t.delete("a"),
        "Delete",
        govec_pb2.DeleteResponse(id="a", status="deleted"),
        DeleteResponse(id="a", status="deleted"),
    ),
}


@pytest.mark.parametrize("operation", _OPERATIONS.values(), ids=_OPERATIONS.keys())
async def test_operation__server_answers__calls_its_rpc_and_maps_the_reply(
    grpc_server: RunningServer, grpc_transport: BuildTransport, operation: _Operation
) -> None:
    # Arrange
    grpc_server.servicer.replies[operation.rpc] = operation.reply
    transport = grpc_transport()

    # Act
    result = await settle(operation.call(transport))

    # Assert
    assert [call.rpc for call in grpc_server.servicer.calls] == [operation.rpc]
    assert result == operation.expected


async def test_insert_batch__records__streams_each_one_to_the_server(
    grpc_server: RunningServer, grpc_transport: BuildTransport
) -> None:
    # Arrange
    transport = grpc_transport()
    requests = [
        InsertRequest(id="a", vector=[1.0]),
        InsertRequest(id="b", vector=[2.0]),
    ]

    # Act
    await settle(transport.insert_batch(requests))

    # Assert
    streamed = grpc_server.servicer.calls[-1].request
    assert isinstance(streamed, list)
    assert [r.id for r in streamed] == ["a", "b"]  # ty: ignore[unresolved-attribute]


# --- timeouts -------------------------------------------------------------------
#
# The server sees the deadline each call carried, which is what these read. gRPC
# rounds the deadline on the wire and some of it passes in transit, so it can
# arrive a few ms either side of the timeout set.


async def test_request__ordinary_call__carries_the_call_timeout(
    grpc_server: RunningServer, grpc_transport: BuildTransport
) -> None:
    # Arrange
    transport = grpc_transport(timeouts=Timeouts(call=3.0, batch=30.0))

    # Act
    await settle(transport.health())

    # Assert
    assert grpc_server.servicer.calls[-1].time_remaining == pytest.approx(3.0, abs=0.5)


async def test_insert_batch__any_batch__carries_the_batch_timeout(
    grpc_server: RunningServer, grpc_transport: BuildTransport
) -> None:
    # Arrange
    transport = grpc_transport(timeouts=Timeouts(call=3.0, batch=30.0))

    # Act
    await settle(transport.insert_batch([_REQUEST]))

    # Assert
    assert grpc_server.servicer.calls[-1].time_remaining == pytest.approx(30.0, abs=0.5)


async def test_request__timeout_is_none__carries_no_deadline(
    grpc_server: RunningServer, grpc_transport: BuildTransport
) -> None:
    # Arrange
    transport = grpc_transport(timeouts=Timeouts(call=None))

    # Act
    await settle(transport.health())

    # Assert
    assert grpc_server.servicer.calls[-1].time_remaining is None


# --- auth ---------------------------------------------------------------------


async def test_request__api_key_given__sends_a_bearer_header(
    grpc_server: RunningServer, grpc_transport: BuildTransport
) -> None:
    # Arrange
    transport = grpc_transport(api_key="s3cret")

    # Act
    await settle(transport.health())

    # Assert
    assert grpc_server.servicer.calls[-1].metadata["authorization"] == "Bearer s3cret"


async def test_request__no_api_key__sends_no_authorization_header(
    grpc_server: RunningServer, grpc_transport: BuildTransport
) -> None:
    # Arrange
    transport = grpc_transport()

    # Act
    await settle(transport.health())

    # Assert
    assert "authorization" not in grpc_server.servicer.calls[-1].metadata


# --- failures become govec exceptions -----------------------------------------
#
# The code-by-code mapping is pinned in test_grpc_errors.py; these check that
# each transport actually routes a failed call through it.


async def test_get_by_id__server_answers_not_found__returns_none(
    grpc_server: RunningServer, grpc_transport: BuildTransport
) -> None:
    # Arrange
    # REST answers a missing vector with 404 and also returns None.
    grpc_server.servicer.failures["GetByID"] = Failure(
        grpc.StatusCode.NOT_FOUND, "vector not found"
    )
    transport = grpc_transport()

    # Act
    record = await settle(transport.get_by_id("nope"))

    # Assert
    assert record is None


async def test_request__server_rejects_it__raises_api_error_labelled_grpc(
    grpc_server: RunningServer, grpc_transport: BuildTransport
) -> None:
    # Arrange
    grpc_server.servicer.failures["Search"] = Failure(
        grpc.StatusCode.INVALID_ARGUMENT, "dimension mismatch"
    )
    transport = grpc_transport()

    # Act
    with pytest.raises(GoVecAPIError) as excinfo:
        await settle(transport.search(SearchRequest(vector=[1.0], k=1)))

    # Assert
    assert excinfo.value.status_label == "gRPC"
    assert "dimension mismatch" in excinfo.value.message


def _unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("localhost", 0))
        # getsockname() is typed Any; for an AF_INET socket it is (host, port).
        return cast(int, sock.getsockname()[1])


async def test_request__nothing_listening__raises_connection_error(
    grpc_transport: BuildTransport,
) -> None:
    # Arrange
    transport = grpc_transport(port=_unused_port())

    # Act / Assert
    with pytest.raises(GoVecConnectionError):
        await settle(transport.health())


# --- lifecycle ----------------------------------------------------------------


async def test_request__transport_already_closed__raises_client_closed_error(
    grpc_server: RunningServer, grpc_transport: BuildTransport
) -> None:
    # Arrange
    transport = grpc_transport()
    await shut(transport)

    # Act / Assert
    with pytest.raises(GoVecClientClosedError):
        await settle(transport.health())

    assert grpc_server.servicer.calls == []


async def test_close__called_twice__does_not_raise(
    grpc_transport: BuildTransport,
) -> None:
    # Arrange
    transport = grpc_transport()

    # Act
    await shut(transport)
    await shut(transport)

    # Assert
    with pytest.raises(GoVecClientClosedError):
        await settle(transport.health())


def test_async_transport__created_outside_an_event_loop__raises_runtime_error() -> None:
    # Arrange / Act / Assert
    # grpc.aio would otherwise start a loop of its own, which the caller's
    # code never runs on.
    with pytest.raises(RuntimeError, match="inside a running event loop"):
        AsyncGRPCTransport("localhost", 9698, tls=False)
