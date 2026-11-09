from collections.abc import Callable
from typing import cast

import pytest

from govec.transport.base import Timeouts
from govec.transport.grpc import AsyncGRPCTransport, GRPCTransport
from govec.transport.rest import AsyncRESTTransport, RESTTransport
from tests.govec.grpc_server import HOST as GRPC_HOST
from tests.govec.grpc_server import RunningServer
from tests.govec.rest_api import HOST, PORT


@pytest.fixture(params=[RESTTransport, AsyncRESTTransport], ids=["sync", "async"])
def rest_transport(
    request: pytest.FixtureRequest,
) -> Callable[..., RESTTransport | AsyncRESTTransport]:
    """Builds each REST transport exactly as production does.

    Every test that takes this runs once per transport, so sync and async are
    held to the same behaviour. Nothing in either is swapped: requests go out
    through its own httpx client and the `server` fixture answers them.
    """
    transport_class = cast(type[RESTTransport | AsyncRESTTransport], request.param)

    def _build(
        api_key: str | None = None, timeouts: Timeouts = Timeouts()
    ) -> RESTTransport | AsyncRESTTransport:
        return transport_class(HOST, PORT, api_key, tls=False, timeouts=timeouts)

    return _build


@pytest.fixture(params=[GRPCTransport, AsyncGRPCTransport], ids=["sync", "async"])
def grpc_transport(
    request: pytest.FixtureRequest, grpc_server: RunningServer
) -> Callable[..., GRPCTransport | AsyncGRPCTransport]:
    """Builds each gRPC transport, pointed at the in-process `grpc_server`.

    Call it from inside the (async) test: AsyncGRPCTransport has to be built
    on a running event loop.
    """
    transport_class = cast(type[GRPCTransport | AsyncGRPCTransport], request.param)

    def _build(
        api_key: str | None = None,
        timeouts: Timeouts = Timeouts(),
        port: int | None = None,
    ) -> GRPCTransport | AsyncGRPCTransport:
        return transport_class(
            GRPC_HOST,
            port if port is not None else grpc_server.port,
            api_key,
            tls=False,
            timeouts=timeouts,
        )

    return _build
