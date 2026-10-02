from collections.abc import Callable

import httpx
import pytest

from govec.exceptions import (
    GoVecAPIError,
    GoVecClientClosedError,
    GoVecConnectionError,
    GoVecTimeoutError,
)
from govec.models import SearchRequest, SparseVector
from govec.transport.rest import RESTTransport

type Handler = Callable[[httpx.Request], httpx.Response]
type BuildTransport = Callable[..., RESTTransport]
type BuildOkHandler = Callable[..., Handler]


# --- transport failures become govec exceptions -------------------------------
#
# These are the regression tests for a REST-only gap: the SDK wrapped a
# connection failure during the client's preflight handshake and let
# httpx.ConnectError escape from every call made afterwards, so the same
# failure had two exception types depending on when it happened.


def test_request__server_unreachable__raises_connection_error(
    rest_transport: BuildTransport,
) -> None:
    # Arrange
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    transport = rest_transport(refuse)

    # Act / Assert
    with pytest.raises(GoVecConnectionError):
        transport.health()


def test_request__server_times_out__raises_timeout_error(
    rest_transport: BuildTransport,
) -> None:
    # Arrange
    def time_out(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    transport = rest_transport(time_out)

    # Act / Assert
    with pytest.raises(GoVecTimeoutError):
        transport.health()


def test_request__server_times_out__is_not_reported_as_unreachable(
    rest_transport: BuildTransport,
) -> None:
    # httpx.TimeoutException subclasses RequestError, so ordering the except
    # clauses the other way round would silently collapse the two. A caller
    # retrying a timeout with a smaller k must be able to tell it apart from a
    # server that is simply down.
    def time_out(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    transport = rest_transport(time_out)

    # Act
    with pytest.raises(GoVecTimeoutError) as excinfo:
        transport.health()

    # Assert
    assert not isinstance(excinfo.value, GoVecConnectionError)


def test_request__error_status__raises_api_error_not_connection_error(
    rest_transport: BuildTransport,
) -> None:
    # A response that arrives carrying an error status is the server answering,
    # which is a different thing from failing to reach it.
    def bad_request(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"success": False, "error": "k is negative"})

    transport = rest_transport(bad_request)

    # Act / Assert
    with pytest.raises(GoVecAPIError) as excinfo:
        transport.health()

    assert excinfo.value.status_code == 400
    assert "k is negative" in excinfo.value.message
    assert str(excinfo.value).startswith("HTTP 400")


# --- auth ---------------------------------------------------------------------
#
# Bearer-header coverage was lost when MockGoVecService was removed; this is
# where it lives now, and it needs no server.


def test_request__api_key_given__sends_a_bearer_header(
    rest_transport: BuildTransport,
) -> None:
    # Arrange
    seen: dict[str, str] = {}

    def capture(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={"success": True, "data": {"status": "ok"}})

    transport = rest_transport(capture, api_key="s3cret")

    # Act
    transport.health()

    # Assert
    assert seen["authorization"] == "Bearer s3cret"


def test_request__no_api_key__sends_no_authorization_header(
    rest_transport: BuildTransport,
) -> None:
    # Arrange
    seen: dict[str, str] = {}

    def capture(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={"success": True, "data": {"status": "ok"}})

    transport = rest_transport(capture)

    # Act
    transport.health()

    # Assert
    assert "authorization" not in seen


# --- lifecycle ----------------------------------------------------------------


def test_close__called__releases_the_underlying_httpx_client(
    rest_transport: BuildTransport, ok_json: BuildOkHandler
) -> None:
    # Arrange
    transport = rest_transport(ok_json({"status": "ok"}))

    # Act
    transport.close()

    # Assert
    assert transport.client.is_closed


def test_close__called_twice__does_not_raise(
    rest_transport: BuildTransport, ok_json: BuildOkHandler
) -> None:
    # Arrange
    transport = rest_transport(ok_json({"status": "ok"}))

    # Act
    transport.close()
    transport.close()

    # Assert
    assert transport.client.is_closed


def test_request__transport_already_closed__raises_client_closed_error(
    rest_transport: BuildTransport, ok_json: BuildOkHandler
) -> None:
    # Without the guard this surfaces as a bare RuntimeError from inside httpx,
    # which says nothing about this SDK and differs from what gRPC would say.
    transport = rest_transport(ok_json({"status": "ok"}))
    transport.close()

    # Act / Assert
    with pytest.raises(GoVecClientClosedError):
        transport.health()


def test_context_manager__block_exits__closes_the_transport(
    rest_transport: BuildTransport, ok_json: BuildOkHandler
) -> None:
    # Arrange
    transport = rest_transport(ok_json({"status": "ok"}))

    # Act
    with transport as entered:
        assert entered is transport

    # Assert
    assert transport.client.is_closed


def test_context_manager__block_raises__still_closes_and_propagates(
    rest_transport: BuildTransport, ok_json: BuildOkHandler
) -> None:
    # __exit__ returns None rather than False so the error is not swallowed.
    transport = rest_transport(ok_json({"status": "ok"}))

    # Act / Assert
    with pytest.raises(ValueError):
        with transport:
            raise ValueError("boom")

    assert transport.client.is_closed


# --- response parsing ---------------------------------------------------------


def test_get_by_id__dense_only_record__returns_no_sparse_component(
    rest_transport: BuildTransport, ok_json: BuildOkHandler
) -> None:
    # The server omits sparse_vector for a dense-only record.
    transport = rest_transport(ok_json({"id": "a", "vector": [1.0, 2.0]}))

    # Act
    record = transport.get_by_id("a")

    # Assert
    assert record is not None
    assert record.sparse_vector is None


def test_get_by_id__record_has_sparse__returns_it(
    rest_transport: BuildTransport, ok_json: BuildOkHandler
) -> None:
    # Arrange
    transport = rest_transport(
        ok_json(
            {
                "id": "a",
                "vector": [1.0, 2.0],
                "sparse_vector": {"indices": [0, 7], "values": [0.5, 0.25]},
            }
        )
    )

    # Act
    record = transport.get_by_id("a")

    # Assert
    assert record is not None
    assert record.sparse_vector == SparseVector(indices=[0, 7], values=[0.5, 0.25])


def test_get_by_id__missing_vector__returns_none_rather_than_raising(
    rest_transport: BuildTransport,
) -> None:
    # gRPC translates NOT_FOUND to None to match this; the two must agree.
    def not_found(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"success": False, "error": "vector not found"})

    transport = rest_transport(not_found)

    # Act
    record = transport.get_by_id("nope")

    # Assert
    assert record is None


def test_search__result_without_metadata__has_no_meta(
    rest_transport: BuildTransport, ok_json: BuildOkHandler
) -> None:
    # The server omits "meta" when a vector carries no metadata.
    transport = rest_transport(ok_json([{"id": "a", "score": 1.0}]))

    # Act
    results = transport.search(SearchRequest(vector=[1.0], k=1))

    # Assert
    assert results[0].meta is None
