from collections.abc import Callable

import httpx
import pytest

from govec.exceptions import (
    GoVecAPIError,
    GoVecClientClosedError,
    GoVecConnectionError,
    GoVecTimeoutError,
)
from govec.models import InsertRequest, SearchRequest, SparseVector
from govec.transport.json_codec import encode_request
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


def test_get_by_id__404_body_is_not_json__returns_none(
    rest_transport: BuildTransport,
) -> None:
    # Arrange
    # A reverse proxy in front of GoVec can answer 404 with its own HTML page.
    def proxy_not_found(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="<html>Not Found</html>")

    transport = rest_transport(proxy_not_found)

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


def test_server_info__response__includes_the_server_version(
    rest_transport: BuildTransport, ok_json: BuildOkHandler
) -> None:
    # Arrange
    transport = rest_transport(ok_json(_info_payload(version="v0.1.0")))

    # Act
    info = transport.server_info()

    # Assert
    assert info.version == "v0.1.0"


# --- forward compatibility ----------------------------------------------------
#
# Every response used to be built by splatting the JSON into its dataclass, so
# a field the server added in a later release -- as it did with /info's
# "version" -- raised TypeError in every older client. Unknown fields are now
# dropped; these pin that for the two shapes most likely to grow.


def test_server_info__server_sends_a_field_the_sdk_does_not_know__ignores_it(
    rest_transport: BuildTransport, ok_json: BuildOkHandler
) -> None:
    # Arrange
    payload = _info_payload(version="v9.0.0") | {"added_in_a_later_release": True}
    transport = rest_transport(ok_json(payload))

    # Act
    info = transport.server_info()

    # Assert
    assert info.version == "v9.0.0"


def test_search__result_has_a_field_the_sdk_does_not_know__ignores_it(
    rest_transport: BuildTransport, ok_json: BuildOkHandler
) -> None:
    # Arrange
    transport = rest_transport(ok_json([{"id": "a", "score": 1.0, "rank": 1}]))

    # Act
    results = transport.search(SearchRequest(vector=[1.0], k=1))

    # Assert
    assert results[0].id == "a"


# --- request bodies -------------------------------------------------------------
#
# What goes into a body is tested in test_json_codec.py. These pin only that the
# transport sends what the codec produced, and sends nothing when it refuses.


def _capture(sent: list[httpx.Request], data: object) -> Handler:
    def _handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"success": True, "data": data})

    return _handler


def test_search__request__sends_the_encoded_body_as_json(
    rest_transport: BuildTransport,
) -> None:
    # Arrange
    sent: list[httpx.Request] = []
    transport = rest_transport(_capture(sent, []))
    request = SearchRequest(vector=[0.1, -2.5], k=3)

    # Act
    transport.search(request)

    # Assert
    assert sent[0].content == encode_request(request)
    assert sent[0].headers["content-type"] == "application/json"


def test_insert_batch__a_record_has_nan__raises_value_error_and_sends_nothing(
    rest_transport: BuildTransport,
) -> None:
    # Arrange
    sent: list[httpx.Request] = []
    transport = rest_transport(_capture(sent, {"inserted_count": 0}))
    records = [
        InsertRequest(id="a", vector=[1.0]),
        InsertRequest(id="b", vector=[float("nan")]),
    ]

    # Act / Assert
    with pytest.raises(ValueError, match="vector contains NaN or infinity"):
        transport.insert_batch(records)

    assert sent == []


def _info_payload(version: str) -> dict[str, object]:
    return {
        "quantization": "none",
        "index_type": "brute",
        "distance_metric": "cosine",
        "dimensions": 3,
        "vector_count": 0,
        "enable_mmap": False,
        "version": version,
    }
