from collections.abc import AsyncIterator, Awaitable, Callable
from typing import cast

import httpx
import pytest
import respx

from govec.async_client import AsyncGoVecClient
from govec.client import GoVecClient, Protocol
from govec.exceptions import GoVecClientClosedError, GoVecConnectionError
from govec.models import InsertRequest
from govec.transport.base import DEFAULT_BATCH_TIMEOUT, DEFAULT_TIMEOUT
from govec.transport.rest import AsyncRESTTransport, RESTTransport
from tests.govec.grpc_server import HOST as GRPC_HOST
from tests.govec.grpc_server import RunningServer
from tests.govec.rest_api import HOST, PORT, info, ok
from tests.govec.sync_or_async import (
    CLIENT_KINDS,
    AnyClient,
    ClientKind,
    connect_client,
    settle,
    shut,
)

# Both clients over their real transports, with only the network faked. The
# client's own behaviour does not depend on the protocol, so REST stands in for
# both except where a test says otherwise; the e2e suites run gRPC too.
#
# Every test taking `connect` or `client` runs once per client.
pytestmark = pytest.mark.anyio

type Connect = Callable[..., Awaitable[AnyClient]]


@pytest.fixture(params=CLIENT_KINDS)
def connect(request: pytest.FixtureRequest) -> Connect:
    kind = cast(ClientKind, request.param)

    async def _connect(
        protocol: Protocol = "rest",
        host: str = HOST,
        port: int = PORT,
        timeout: float | None = DEFAULT_TIMEOUT,
        batch_timeout: float | None = DEFAULT_BATCH_TIMEOUT,
    ) -> AnyClient:
        return await connect_client(
            kind, host, port, protocol, timeout=timeout, batch_timeout=batch_timeout
        )

    return _connect


@pytest.fixture
async def client(
    server: respx.MockRouter, connect: Connect
) -> AsyncIterator[AnyClient]:
    server.get("/api/v1/info").mock(return_value=ok(info(dimensions=3)))

    client = await connect()
    yield client

    await shut(client)


def _paths_sent(server: respx.MockRouter) -> list[str]:
    return [call.request.url.path for call in server.calls]


# --- connecting ---------------------------------------------------------------


async def test_connect__server_answers__returns_a_client_that_knows_its_width(
    client: AnyClient,
) -> None:
    # Assert
    # The handshake has run by the time a client exists, on both kinds.
    assert client.dimensions == 3


async def test_connect__over_grpc__talks_to_the_grpc_server(
    grpc_server: RunningServer, connect: Connect
) -> None:
    # Arrange
    client = await connect(protocol="grpc", host=GRPC_HOST, port=grpc_server.port)

    # Act
    health = await settle(client.health())

    # Assert
    assert health.status == "ok"
    assert [call.rpc for call in grpc_server.servicer.calls] == ["Info", "Health"]

    await shut(client)


async def test_connect__server_unreachable__raises_connection_error(
    server: respx.MockRouter, connect: Connect
) -> None:
    # Arrange
    server.get("/api/v1/info").mock(side_effect=httpx.ConnectError)

    # Act / Assert
    with pytest.raises(GoVecConnectionError):
        await connect()


async def test_connect__unknown_protocol__is_rejected(connect: Connect) -> None:
    # Arrange / Act / Assert
    with pytest.raises(Exception):
        await connect(protocol="carrier-pigeon")


def test_from_transport__handshake_fails__closes_the_transport(
    server: respx.MockRouter,
) -> None:
    # Arrange
    # A failed handshake raises rather than returning a client, so the caller
    # has nothing to close. Without this the httpx pool or gRPC channel the
    # transport already opened would leak on every failed connection attempt.
    server.get("/api/v1/info").mock(side_effect=httpx.ConnectError)
    transport = RESTTransport(HOST, PORT, tls=False)

    # Act
    with pytest.raises(GoVecConnectionError):
        GoVecClient._from_transport(transport, host=HOST, port=PORT, protocol="rest")

    # Assert
    assert transport.client.is_closed


async def test_async_from_transport__handshake_fails__closes_the_transport(
    server: respx.MockRouter,
) -> None:
    # Arrange
    server.get("/api/v1/info").mock(side_effect=httpx.ConnectError)
    transport = AsyncRESTTransport(HOST, PORT, tls=False)

    # Act
    with pytest.raises(GoVecConnectionError):
        await AsyncGoVecClient._from_transport(
            transport, host=HOST, port=PORT, protocol="rest"
        )

    # Assert
    assert transport.client.is_closed


# --- lifecycle ----------------------------------------------------------------


async def test_close__called__refuses_further_requests(client: AnyClient) -> None:
    # Act
    await shut(client)

    # Assert
    with pytest.raises(GoVecClientClosedError):
        await settle(client.health())


async def test_close__called_twice__does_not_raise(client: AnyClient) -> None:
    # Arrange
    await shut(client)

    # Act
    await shut(client)

    # Assert
    with pytest.raises(GoVecClientClosedError):
        await settle(client.health())


def test_context_manager__block_exits__closes_the_client(
    server: respx.MockRouter,
) -> None:
    # Arrange
    server.get("/api/v1/info").mock(return_value=ok(info()))

    # Act
    with GoVecClient.connect(HOST, PORT, "", "rest", tls=False) as client:
        pass

    # Assert
    with pytest.raises(GoVecClientClosedError):
        client.health()


def test_context_manager__block_raises__still_closes_and_propagates(
    server: respx.MockRouter,
) -> None:
    # Arrange
    server.get("/api/v1/info").mock(return_value=ok(info()))
    client = GoVecClient.connect(HOST, PORT, "", "rest", tls=False)

    # Act
    with pytest.raises(ValueError):
        with client:
            raise ValueError("boom")

    # Assert
    with pytest.raises(GoVecClientClosedError):
        client.health()


async def test_async_connect_as_context_manager__block_exits__closes_the_client(
    server: respx.MockRouter,
) -> None:
    # Arrange
    server.get("/api/v1/info").mock(return_value=ok(info()))

    # Act
    async with AsyncGoVecClient.connect(HOST, PORT, "", "rest", tls=False) as client:
        assert client.dimensions == 3

    # Assert
    with pytest.raises(GoVecClientClosedError):
        await client.health()


async def test_async_connect_as_context_manager__block_raises__closes_and_propagates(
    server: respx.MockRouter,
) -> None:
    # Arrange
    server.get("/api/v1/info").mock(return_value=ok(info()))
    entered: list[AsyncGoVecClient] = []

    # Act
    with pytest.raises(ValueError):
        async with AsyncGoVecClient.connect(
            HOST, PORT, "", "rest", tls=False
        ) as client:
            entered.append(client)
            raise ValueError("boom")

    # Assert
    with pytest.raises(GoVecClientClosedError):
        await entered[0].health()


async def test_async_connect_as_context_manager__handshake_fails__runs_no_block(
    server: respx.MockRouter,
) -> None:
    # Arrange
    server.get("/api/v1/info").mock(side_effect=httpx.ConnectError)
    ran: list[bool] = []

    # Act
    with pytest.raises(GoVecConnectionError):
        async with AsyncGoVecClient.connect(HOST, PORT, "", "rest", tls=False):
            ran.append(True)

    # Assert
    assert ran == []


async def test_async_client_as_context_manager__block_exits__closes_it(
    server: respx.MockRouter,
) -> None:
    # Arrange
    # A client from `await connect(...)` is a context manager in its own right.
    server.get("/api/v1/info").mock(return_value=ok(info()))
    client = await AsyncGoVecClient.connect(HOST, PORT, "", "rest", tls=False)

    # Act
    async with client as entered:
        assert entered is client

    # Assert
    with pytest.raises(GoVecClientClosedError):
        await client.health()


# --- insert_many ----------------------------------------------------------------


async def test_insert_many__more_than_one_batch__sends_them_in_order_and_sums(
    server: respx.MockRouter, client: AnyClient
) -> None:
    # Arrange
    route = server.post("/api/v1/vectors/batch").mock(
        return_value=ok({"inserted_count": 1, "errors": []})
    )
    requests = [InsertRequest(id=f"v{i}", vector=[1.0]) for i in range(3)]

    # Act
    result = await settle(client.insert_many(requests, batch_size=1))

    # Assert
    bodies = [call.request.content for call in route.calls]
    assert [b'"v0"' in body for body in bodies] == [True, False, False]
    assert [b'"v2"' in body for body in bodies] == [False, False, True]
    assert result.inserted_count == 3


# --- timeouts -------------------------------------------------------------------


async def test_connect__timeouts_given__apply_to_calls_and_to_batches(
    server: respx.MockRouter, connect: Connect
) -> None:
    # Arrange
    handshake = server.get("/api/v1/info").mock(return_value=ok(info()))
    batch = server.post("/api/v1/vectors/batch").mock(
        return_value=ok({"inserted_count": 1, "errors": []})
    )
    client = await connect(timeout=3.0, batch_timeout=30.0)

    # Act
    await settle(client.insert_many([InsertRequest(id="a", vector=[1.0])]))

    # Assert
    assert handshake.calls.last.request.extensions["timeout"]["read"] == 3.0
    assert batch.calls.last.request.extensions["timeout"]["read"] == 30.0

    await shut(client)


@pytest.mark.parametrize(
    ("timeout", "batch_timeout", "named"),
    [(0, 60.0, "timeout"), (-1, 60.0, "timeout"), (10.0, 0, "batch_timeout")],
)
async def test_connect__timeout_not_positive__raises_before_contacting_the_server(
    server: respx.MockRouter,
    connect: Connect,
    timeout: float,
    batch_timeout: float,
    named: str,
) -> None:
    # Act
    with pytest.raises(ValueError, match=f"^{named} must be positive"):
        await connect(timeout=timeout, batch_timeout=batch_timeout)

    # Assert
    assert not server.calls


# --- NaN and infinity never reach a transport -----------------------------------
#
# Checked in the client rather than in either transport, so REST and gRPC reject
# them the same way. Only the handshake may have been sent.


async def test_insert__vector_has_nan__raises_and_sends_nothing(
    server: respx.MockRouter, client: AnyClient
) -> None:
    # Act
    with pytest.raises(ValueError, match="vector contains NaN or infinity"):
        await settle(client.insert(vector_id="a", dense_vector=[1.0, float("nan")]))

    # Assert
    assert _paths_sent(server) == ["/api/v1/info"]


async def test_insert_many__nan_in_a_later_batch__raises_before_any_batch_is_sent(
    server: respx.MockRouter, client: AnyClient
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
        await settle(client.insert_many(requests, batch_size=1))

    # Assert
    assert _paths_sent(server) == ["/api/v1/info"]


async def test_search__filter_has_nan__raises_and_sends_nothing(
    server: respx.MockRouter, client: AnyClient
) -> None:
    # Act
    with pytest.raises(ValueError, match="metadata or filter contains NaN"):
        await settle(client.search(dense_vector=[1.0], filter={"score": float("nan")}))

    # Assert
    assert _paths_sent(server) == ["/api/v1/info"]
