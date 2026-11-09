from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import grpc
import pytest
import respx

from govec.proto import govec_pb2_grpc
from tests.govec.grpc_server import HOST, GoVecServicer, RunningServer
from tests.govec.rest_api import BASE_URL


@pytest.fixture
def anyio_backend() -> str:
    # anyio's plugin would also run every async test on trio. grpc.aio only
    # runs on asyncio, so the async client is asyncio-only and so are its tests.
    return "asyncio"


@pytest.fixture
def server() -> Iterator[respx.MockRouter]:
    """GoVec's REST API, faked at the httpx layer.

    The real client and transport run unchanged; only the network is
    replaced. A request with no route fails the test rather than reaching
    anything, and so does a route the test added but never hit.
    """
    with respx.mock(base_url=BASE_URL) as router:
        yield router


@pytest.fixture
def grpc_server() -> Iterator[RunningServer]:
    """A real gRPC server in this process, serving a scripted GoVecServicer.

    The gRPC counterpart of `server`: the real transports and a real channel
    run unchanged, and only what answers them is replaced. It is a sync
    server on its own threads, so sync and async transports can both call it.
    """
    servicer = GoVecServicer()
    server = grpc.server(ThreadPoolExecutor(max_workers=4))
    govec_pb2_grpc.add_GoVecServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port(f"{HOST}:0")
    server.start()

    yield RunningServer(servicer=servicer, port=port)

    server.stop(grace=None)
