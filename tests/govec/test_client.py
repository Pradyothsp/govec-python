from collections.abc import Iterator

import httpx
import pytest
import respx

from govec.client import GoVecClient
from govec.exceptions import GoVecClientClosedError, GoVecConnectionError
from govec.models import InsertRequest
from govec.transport.rest import RESTTransport
from tests.govec.rest_api import HOST, PORT, info, ok

# The client over its real REST transport, with only the network faked. The
# client's own behaviour does not depend on the transport, so REST stands in
# for both; the e2e suites run it over gRPC too.


@pytest.fixture
def client(server: respx.MockRouter) -> Iterator[GoVecClient]:
    server.get("/api/v1/info").mock(return_value=ok(info()))

    client = GoVecClient(host=HOST, port=PORT, api_key="", protocol="rest", tls=False)
    yield client

    client.close()


def _paths_sent(server: respx.MockRouter) -> list[str]:
    return [call.request.url.path for call in server.calls]


# --- lifecycle ----------------------------------------------------------------


def test_close__called__refuses_further_requests(client: GoVecClient) -> None:
    # Arrange / Act
    client.close()

    # Assert
    with pytest.raises(GoVecClientClosedError):
        client.health()


def test_close__called_twice__does_not_raise(client: GoVecClient) -> None:
    # Arrange
    client.close()

    # Act
    client.close()

    # Assert
    with pytest.raises(GoVecClientClosedError):
        client.health()


def test_context_manager__block_exits__closes_the_client(client: GoVecClient) -> None:
    # Arrange / Act
    with client as entered:
        assert entered is client

    # Assert
    with pytest.raises(GoVecClientClosedError):
        client.health()


def test_context_manager__block_raises__still_closes_and_propagates(
    client: GoVecClient,
) -> None:
    # Arrange / Act
    with pytest.raises(ValueError):
        with client:
            raise ValueError("boom")

    # Assert
    with pytest.raises(GoVecClientClosedError):
        client.health()


def test_init__server_unreachable__raises_connection_error(
    server: respx.MockRouter,
) -> None:
    # Arrange
    server.get("/api/v1/info").mock(side_effect=httpx.ConnectError)

    # Act / Assert
    with pytest.raises(GoVecConnectionError):
        GoVecClient(host=HOST, port=PORT, api_key="", protocol="rest", tls=False)


def test_init__preflight_handshake_fails__closes_the_transport(
    server: respx.MockRouter,
) -> None:
    # Arrange
    # The constructor raises rather than returning an object, so the caller has
    # nothing to close. Without this the httpx pool or gRPC channel the
    # transport already opened would leak on every failed connection attempt.
    # Built through _from_transport so the transport is still reachable after
    # the handshake that threw.
    server.get("/api/v1/info").mock(side_effect=httpx.ConnectError)
    transport = RESTTransport(HOST, PORT, tls=False)

    # Act
    with pytest.raises(GoVecConnectionError):
        GoVecClient._from_transport(transport, host=HOST, port=PORT, protocol="rest")

    # Assert
    assert transport.client.is_closed


def test_init__unknown_protocol__is_rejected() -> None:
    # Arrange / Act / Assert
    with pytest.raises(Exception):
        GoVecClient(
            host=HOST,
            port=PORT,
            api_key="",
            protocol="carrier-pigeon",  # ty: ignore[invalid-argument-type]
            tls=False,
        )


# --- timeouts -------------------------------------------------------------------


def test_init__timeouts_given__apply_to_calls_and_to_batches(
    server: respx.MockRouter,
) -> None:
    # Arrange
    handshake = server.get("/api/v1/info").mock(return_value=ok(info()))
    batch = server.post("/api/v1/vectors/batch").mock(
        return_value=ok({"inserted_count": 1, "errors": []})
    )

    # Act
    with GoVecClient(
        host=HOST,
        port=PORT,
        api_key="",
        protocol="rest",
        tls=False,
        timeout=3.0,
        batch_timeout=30.0,
    ) as client:
        client.insert_many([InsertRequest(id="a", vector=[1.0])])

    # Assert
    assert handshake.calls.last.request.extensions["timeout"]["read"] == 3.0
    assert batch.calls.last.request.extensions["timeout"]["read"] == 30.0


@pytest.mark.parametrize(
    ("timeout", "batch_timeout", "named"),
    [(0, 60.0, "timeout"), (-1, 60.0, "timeout"), (10.0, 0, "batch_timeout")],
)
def test_init__timeout_not_positive__raises_before_contacting_the_server(
    server: respx.MockRouter, timeout: float, batch_timeout: float, named: str
) -> None:
    # Act
    with pytest.raises(ValueError, match=f"^{named} must be positive"):
        GoVecClient(
            host=HOST,
            port=PORT,
            api_key="",
            protocol="rest",
            tls=False,
            timeout=timeout,
            batch_timeout=batch_timeout,
        )

    # Assert
    assert not server.calls


# --- NaN and infinity never reach a transport -----------------------------------
#
# Checked in the client rather than in either transport, so REST and gRPC reject
# them the same way. Only the handshake may have been sent.


def test_insert__vector_has_nan__raises_and_sends_nothing(
    server: respx.MockRouter, client: GoVecClient
) -> None:
    # Act
    with pytest.raises(ValueError, match="vector contains NaN or infinity"):
        client.insert(vector_id="a", dense_vector=[1.0, float("nan")])

    # Assert
    assert _paths_sent(server) == ["/api/v1/info"]


def test_insert_many__nan_in_a_later_batch__raises_before_any_batch_is_sent(
    server: respx.MockRouter, client: GoVecClient
) -> None:
    # Arrange
    # Checked per batch while encoding, the first batch had already gone out by
    # the time the bad record in the second one raised.
    requests = [
        InsertRequest(id="a", vector=[1.0]),
        InsertRequest(id="b", vector=[float("inf")]),
    ]

    # Act
    with pytest.raises(ValueError, match="vector contains NaN or infinity"):
        client.insert_many(requests, batch_size=1)

    # Assert
    assert _paths_sent(server) == ["/api/v1/info"]


def test_search__filter_has_nan__raises_and_sends_nothing(
    server: respx.MockRouter, client: GoVecClient
) -> None:
    # Act
    with pytest.raises(ValueError, match="metadata or filter contains NaN"):
        client.search(dense_vector=[1.0], filter={"score": float("nan")})

    # Assert
    assert _paths_sent(server) == ["/api/v1/info"]
