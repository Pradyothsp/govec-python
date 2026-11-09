from collections.abc import Callable
from typing import NamedTuple

import httpx
import pytest
import respx

from govec.exceptions import (
    GoVecAPIError,
    GoVecClientClosedError,
    GoVecConnectionError,
    GoVecTimeoutError,
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
    SparseVector,
)
from govec.transport.json_codec import encode_request
from govec.transport.rest import AsyncRESTTransport, RESTTransport
from tests.govec.rest_api import HOST, PORT, error, info, ok
from tests.govec.sync_or_async import settle, shut

type BuildTransport = Callable[..., RESTTransport | AsyncRESTTransport]

# Every test taking `rest_transport` runs against both REST transports.
pytestmark = pytest.mark.anyio


# --- transport failures become govec exceptions -------------------------------
#
# These are the regression tests for a REST-only gap: the SDK wrapped a
# connection failure during the client's preflight handshake and let
# httpx.ConnectError escape from every call made afterwards, so the same
# failure had two exception types depending on when it happened.


async def test_request__server_unreachable__raises_connection_error(
    server: respx.MockRouter, rest_transport: BuildTransport
) -> None:
    # Arrange
    server.get("/health").mock(side_effect=httpx.ConnectError)
    transport = rest_transport()

    # Act / Assert
    with pytest.raises(GoVecConnectionError):
        await settle(transport.health())


async def test_request__server_times_out__raises_timeout_error(
    server: respx.MockRouter, rest_transport: BuildTransport
) -> None:
    # Arrange
    server.get("/health").mock(side_effect=httpx.ReadTimeout)
    transport = rest_transport()

    # Act / Assert
    with pytest.raises(GoVecTimeoutError):
        await settle(transport.health())


async def test_request__server_times_out__is_not_reported_as_unreachable(
    server: respx.MockRouter, rest_transport: BuildTransport
) -> None:
    # Arrange
    # httpx.TimeoutException subclasses RequestError, so ordering the except
    # clauses the other way round would silently collapse the two. A caller
    # retrying a timeout with a smaller k must be able to tell it apart from a
    # server that is simply down.
    server.get("/health").mock(side_effect=httpx.ReadTimeout)
    transport = rest_transport()

    # Act
    with pytest.raises(GoVecTimeoutError) as excinfo:
        await settle(transport.health())

    # Assert
    assert not isinstance(excinfo.value, GoVecConnectionError)


async def test_request__error_status__raises_api_error_not_connection_error(
    server: respx.MockRouter, rest_transport: BuildTransport
) -> None:
    # Arrange
    # A response that arrives carrying an error status is the server answering,
    # which is a different thing from failing to reach it.
    server.get("/health").mock(return_value=error(400, "k is negative"))
    transport = rest_transport()

    # Act
    with pytest.raises(GoVecAPIError) as excinfo:
        await settle(transport.health())

    # Assert
    assert excinfo.value.status_code == 400
    assert "k is negative" in excinfo.value.message
    assert str(excinfo.value).startswith("HTTP 400")


# --- auth ---------------------------------------------------------------------
#
# Bearer-header coverage was lost when MockGoVecService was removed; this is
# where it lives now, and it needs no server.


async def test_request__api_key_given__sends_a_bearer_header(
    server: respx.MockRouter, rest_transport: BuildTransport
) -> None:
    # Arrange
    route = server.get("/health").mock(return_value=ok({"status": "ok"}))
    transport = rest_transport(api_key="s3cret")

    # Act
    await settle(transport.health())

    # Assert
    assert route.calls.last.request.headers["authorization"] == "Bearer s3cret"


async def test_request__no_api_key__sends_no_authorization_header(
    server: respx.MockRouter, rest_transport: BuildTransport
) -> None:
    # Arrange
    route = server.get("/health").mock(return_value=ok({"status": "ok"}))
    transport = rest_transport()

    # Act
    await settle(transport.health())

    # Assert
    assert "authorization" not in route.calls.last.request.headers


# --- lifecycle ----------------------------------------------------------------


async def test_close__called__releases_the_underlying_httpx_client(
    rest_transport: BuildTransport,
) -> None:
    # Arrange
    transport = rest_transport()

    # Act
    await shut(transport)

    # Assert
    assert transport.client.is_closed


async def test_close__called_twice__does_not_raise(
    rest_transport: BuildTransport,
) -> None:
    # Arrange
    transport = rest_transport()

    # Act
    await shut(transport)
    await shut(transport)

    # Assert
    assert transport.client.is_closed


async def test_request__transport_already_closed__raises_client_closed_error(
    rest_transport: BuildTransport,
) -> None:
    # Arrange
    # Without the guard this surfaces as a bare RuntimeError from inside httpx,
    # which says nothing about this SDK and differs from what gRPC would say.
    transport = rest_transport()
    await shut(transport)

    # Act / Assert
    with pytest.raises(GoVecClientClosedError):
        await settle(transport.health())


def test_context_manager__block_exits__closes_the_transport() -> None:
    # Arrange
    transport = RESTTransport(HOST, PORT, tls=False)

    # Act
    with transport as entered:
        assert entered is transport

    # Assert
    assert transport.client.is_closed


def test_context_manager__block_raises__still_closes_and_propagates() -> None:
    # Arrange
    # __exit__ returns None rather than False so the error is not swallowed.
    transport = RESTTransport(HOST, PORT, tls=False)

    # Act / Assert
    with pytest.raises(ValueError):
        with transport:
            raise ValueError("boom")

    assert transport.client.is_closed


async def test_async_context_manager__block_exits__closes_the_transport() -> None:
    # Arrange
    transport = AsyncRESTTransport(HOST, PORT, tls=False)

    # Act
    async with transport as entered:
        assert entered is transport

    # Assert
    assert transport.client.is_closed


async def test_async_context_manager__block_raises__still_closes_and_propagates() -> (
    None
):
    # Arrange
    transport = AsyncRESTTransport(HOST, PORT, tls=False)

    # Act / Assert
    with pytest.raises(ValueError):
        async with transport:
            raise ValueError("boom")

    assert transport.client.is_closed


# --- every operation ----------------------------------------------------------
#
# The sync and async classes each spell out every method, path and expected
# status, so a slip in one would otherwise surface only in the e2e suites.

type AnyTransport = RESTTransport | AsyncRESTTransport


class _Operation(NamedTuple):
    call: Callable[[AnyTransport], object]
    method: str
    path: str
    status: int
    data: object
    expected: object


_REQUEST = InsertRequest(id="a", vector=[1.0])

_OPERATIONS = {
    "health": _Operation(
        lambda t: t.health(),
        "GET",
        "/health",
        200,
        {"status": "ok"},
        HealthResponse(status="ok"),
    ),
    "server_info": _Operation(
        lambda t: t.server_info(),
        "GET",
        "/api/v1/info",
        200,
        info(version="v1"),
        InfoResponse(
            quantization="none",
            index_type="brute",
            distance_metric="cosine",
            dimensions=3,
            vector_count=0,
            enable_mmap=False,
            version="v1",
        ),
    ),
    "get_stats": _Operation(
        lambda t: t.get_stats(),
        "GET",
        "/api/v1/stats",
        200,
        {"vector_count": 3},
        GetStatsResponse(vector_count=3),
    ),
    "flush": _Operation(
        lambda t: t.flush(),
        "POST",
        "/api/v1/admin/flush",
        200,
        {"status": "flushed"},
        FlushResponse(status="flushed"),
    ),
    "reset": _Operation(
        lambda t: t.reset(),
        "POST",
        "/api/v1/admin/reset",
        200,
        {"status": "reset"},
        ResetResponse(status="reset"),
    ),
    "get_by_id": _Operation(
        lambda t: t.get_by_id("a"),
        "GET",
        "/api/v1/vectors/a",
        200,
        {"id": "a", "vector": [1.0]},
        GetByIdResponse(id="a", vector=[1.0], sparse_vector=None, metadata=None),
    ),
    "insert": _Operation(
        lambda t: t.insert(_REQUEST),
        "POST",
        "/api/v1/vectors",
        201,
        {"status": "inserted"},
        InsertResponse(status="inserted"),
    ),
    "insert_batch": _Operation(
        lambda t: t.insert_batch([_REQUEST]),
        "POST",
        "/api/v1/vectors/batch",
        200,
        {"inserted_count": 1, "errors": []},
        BatchInsertResponse(inserted_count=1, errors=[]),
    ),
    "search": _Operation(
        lambda t: t.search(SearchRequest(vector=[1.0], k=1)),
        "POST",
        "/api/v1/vectors/search",
        200,
        [],
        [],
    ),
    "delete": _Operation(
        lambda t: t.delete("a"),
        "DELETE",
        "/api/v1/vectors/a",
        200,
        {"id": "a", "status": "deleted"},
        DeleteResponse(id="a", status="deleted"),
    ),
}


@pytest.mark.parametrize("operation", _OPERATIONS.values(), ids=_OPERATIONS.keys())
async def test_operation__server_answers__sends_its_request_and_maps_the_reply(
    server: respx.MockRouter, rest_transport: BuildTransport, operation: _Operation
) -> None:
    # Arrange
    route = server.request(operation.method, operation.path).mock(
        return_value=ok(operation.data, status_code=operation.status)
    )
    transport = rest_transport()

    # Act
    result = await settle(operation.call(transport))

    # Assert
    assert route.called
    assert result == operation.expected


# --- response parsing ---------------------------------------------------------


async def test_get_by_id__dense_only_record__returns_no_sparse_component(
    server: respx.MockRouter, rest_transport: BuildTransport
) -> None:
    # Arrange
    # The server omits sparse_vector for a dense-only record.
    server.get("/api/v1/vectors/a").mock(
        return_value=ok({"id": "a", "vector": [1.0, 2.0]})
    )
    transport = rest_transport()

    # Act
    record = await settle(transport.get_by_id("a"))

    # Assert
    assert record is not None
    assert record.sparse_vector is None


async def test_get_by_id__record_has_sparse__returns_it(
    server: respx.MockRouter, rest_transport: BuildTransport
) -> None:
    # Arrange
    server.get("/api/v1/vectors/a").mock(
        return_value=ok(
            {
                "id": "a",
                "vector": [1.0, 2.0],
                "sparse_vector": {"indices": [0, 7], "values": [0.5, 0.25]},
            }
        )
    )
    transport = rest_transport()

    # Act
    record = await settle(transport.get_by_id("a"))

    # Assert
    assert record is not None
    assert record.sparse_vector == SparseVector(indices=[0, 7], values=[0.5, 0.25])


async def test_get_by_id__missing_vector__returns_none_rather_than_raising(
    server: respx.MockRouter, rest_transport: BuildTransport
) -> None:
    # Arrange
    # gRPC translates NOT_FOUND to None to match this; the two must agree.
    server.get("/api/v1/vectors/nope").mock(return_value=error(404, "vector not found"))
    transport = rest_transport()

    # Act
    record = await settle(transport.get_by_id("nope"))

    # Assert
    assert record is None


async def test_get_by_id__404_body_is_not_json__returns_none(
    server: respx.MockRouter, rest_transport: BuildTransport
) -> None:
    # Arrange
    # A reverse proxy in front of GoVec can answer 404 with its own HTML page.
    server.get("/api/v1/vectors/nope").mock(
        return_value=httpx.Response(404, text="<html>Not Found</html>")
    )
    transport = rest_transport()

    # Act
    record = await settle(transport.get_by_id("nope"))

    # Assert
    assert record is None


async def test_search__result_without_metadata__has_no_meta(
    server: respx.MockRouter, rest_transport: BuildTransport
) -> None:
    # Arrange
    # The server omits "meta" when a vector carries no metadata.
    server.post("/api/v1/vectors/search").mock(
        return_value=ok([{"id": "a", "score": 1.0}])
    )
    transport = rest_transport()

    # Act
    results = await settle(transport.search(SearchRequest(vector=[1.0], k=1)))

    # Assert
    assert results[0].meta is None


async def test_server_info__response__includes_the_server_version(
    server: respx.MockRouter, rest_transport: BuildTransport
) -> None:
    # Arrange
    server.get("/api/v1/info").mock(return_value=ok(info(version="v0.1.0")))
    transport = rest_transport()

    # Act
    response = await settle(transport.server_info())

    # Assert
    assert response.version == "v0.1.0"


# --- forward compatibility ----------------------------------------------------
#
# Every response used to be built by splatting the JSON into its dataclass, so
# a field the server added in a later release -- as it did with /info's
# "version" -- raised TypeError in every older client. Unknown fields are now
# dropped; these pin that for the two shapes most likely to grow.


async def test_server_info__server_sends_a_field_the_sdk_does_not_know__ignores_it(
    server: respx.MockRouter, rest_transport: BuildTransport
) -> None:
    # Arrange
    payload = info(version="v9.0.0") | {"added_in_a_later_release": True}
    server.get("/api/v1/info").mock(return_value=ok(payload))
    transport = rest_transport()

    # Act
    response = await settle(transport.server_info())

    # Assert
    assert response.version == "v9.0.0"


async def test_search__result_has_a_field_the_sdk_does_not_know__ignores_it(
    server: respx.MockRouter, rest_transport: BuildTransport
) -> None:
    # Arrange
    server.post("/api/v1/vectors/search").mock(
        return_value=ok([{"id": "a", "score": 1.0, "rank": 1}])
    )
    transport = rest_transport()

    # Act
    results = await settle(transport.search(SearchRequest(vector=[1.0], k=1)))

    # Assert
    assert results[0].id == "a"


# --- request bodies -------------------------------------------------------------
#
# What goes into a body is tested in test_json_codec.py. This pins only that the
# transport sends what the codec produced.


async def test_search__request__sends_the_encoded_body_as_json(
    server: respx.MockRouter, rest_transport: BuildTransport
) -> None:
    # Arrange
    route = server.post("/api/v1/vectors/search").mock(return_value=ok([]))
    transport = rest_transport()
    request = SearchRequest(vector=[0.1, -2.5], k=3)

    # Act
    await settle(transport.search(request))

    # Assert
    sent = route.calls.last.request
    assert sent.content == encode_request(request)
    assert sent.headers["content-type"] == "application/json"
