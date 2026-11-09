from collections.abc import Coroutine, Generator
from types import TracebackType
from typing import Any, Self, assert_never

from govec.client import Protocol
from govec.client_logic import (
    batches,
    check_all_finite,
    check_batch_widths,
    check_finite,
    check_width,
    merge_batches,
    was_deleted,
)
from govec.models import (
    BatchInsertResponse,
    FlushResponse,
    GetByIdResponse,
    GetStatsResponse,
    HealthResponse,
    InfoResponse,
    InsertRequest,
    ResetResponse,
    SearchRequest,
    SearchResponse,
    SparseVector,
)
from govec.transport.base import (
    DEFAULT_BATCH_TIMEOUT,
    DEFAULT_TIMEOUT,
    AsyncBaseTransport,
    Timeouts,
)


def _open_async_transport(
    host: str,
    port: int,
    api_key: str,
    protocol: Protocol,
    tls: bool,
    timeouts: Timeouts,
) -> AsyncBaseTransport:
    # Imported here so a REST user never loads grpc and a gRPC user never
    # loads httpx.
    if protocol == "rest":
        from govec.transport.rest import AsyncRESTTransport

        return AsyncRESTTransport(host, port, api_key, tls=tls, timeouts=timeouts)

    if protocol == "grpc":
        from govec.transport.grpc import AsyncGRPCTransport

        return AsyncGRPCTransport(host, port, api_key, tls=tls, timeouts=timeouts)

    assert_never(protocol)


class AsyncGoVecClient:
    """GoVecClient for asyncio: the same methods, each awaited.

    Get one from `await AsyncGoVecClient.connect(...)` or
    `async with AsyncGoVecClient.connect(...) as client:`. A constructor can't
    await the handshake, so connect() runs it and only then builds the client:
    every instance has completed its handshake, as every GoVecClient has.

    asyncio only: grpc.aio does not run on trio.
    """

    def __init__(
        self,
        transport: AsyncBaseTransport,
        info: InfoResponse,
        host: str,
        port: int,
        protocol: Protocol,
    ):
        self.host = host
        self.port = port
        self.protocol = protocol
        self.dimensions = info.dimensions
        self.enable_mmap = info.enable_mmap
        self._transport = transport

    @classmethod
    def connect(
        cls,
        host: str,
        port: int,
        api_key: str,
        protocol: Protocol,
        tls: bool = True,
        timeout: float | None = DEFAULT_TIMEOUT,
        batch_timeout: float | None = DEFAULT_BATCH_TIMEOUT,
    ) -> "_Connecting[Self]":
        """Connect to a GoVec server: await the result, or `async with` it."""
        # Built here, not in _open, so a bad timeout raises at the call even
        # if the result is never awaited.
        timeouts = Timeouts(call=timeout, batch=batch_timeout)

        return _Connecting(cls._open(host, port, api_key, protocol, tls, timeouts))

    @classmethod
    async def _open(
        cls,
        host: str,
        port: int,
        api_key: str,
        protocol: Protocol,
        tls: bool,
        timeouts: Timeouts,
    ) -> Self:
        # Runs inside the caller's event loop, which AsyncGRPCTransport needs.
        transport = _open_async_transport(host, port, api_key, protocol, tls, timeouts)
        return await cls._from_transport(transport, host, port, protocol)

    @classmethod
    async def _from_transport(
        cls,
        transport: AsyncBaseTransport,
        host: str,
        port: int,
        protocol: Protocol,
    ) -> Self:
        """Run the handshake over an open transport and build the client.

        Not public, but separate from _open for the same reason as
        GoVecClient._from_transport: a test can hold the transport and see
        that a failed handshake closed it.
        """
        try:
            info = await transport.server_info()
        except BaseException:
            # The caller never got a client, so has nothing to close.
            await transport.aclose()
            raise

        return cls(transport, info, host, port, protocol)

    async def aclose(self) -> None:
        """Release the underlying connection. Safe to call more than once."""
        await self._transport.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # Returning None rather than False: an exception from inside the
        # block propagates instead of being swallowed.
        await self.aclose()

    async def health(self) -> HealthResponse:
        return await self._transport.health()

    async def info(self) -> InfoResponse:
        return await self._transport.server_info()

    async def get_stats(self) -> GetStatsResponse:
        return await self._transport.get_stats()

    async def flush(self) -> FlushResponse:
        return await self._transport.flush()

    async def reset(self) -> ResetResponse:
        """Clear all vectors, ID mappings and the WAL.

        Does not persist the cleared state to disk -- call flush() afterward if
        the reset should survive a restart.
        """
        return await self._transport.reset()

    async def get_by_id(self, vector_id: str) -> GetByIdResponse | None:
        return await self._transport.get_by_id(vector_id)

    async def insert(
        self,
        vector_id: str,
        dense_vector: list[float],
        sparse_vector: SparseVector | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        check_width(dense_vector, self.dimensions, self.enable_mmap)

        request = InsertRequest(
            id=vector_id,
            vector=dense_vector,
            sparse_vector=sparse_vector,
            metadata=metadata,
        )

        check_finite(request)

        await self._transport.insert(request)
        return True

    async def insert_many(
        self, requests: list[InsertRequest], batch_size: int = 500
    ) -> BatchInsertResponse:
        """Insert in chunks of `batch_size`, one chunk at a time.

        Sequential on purpose, as in GoVecClient: sending chunks concurrently
        would change which write wins when an ID appears in two of them.
        """
        check_batch_widths(requests, self.dimensions, self.enable_mmap)
        check_all_finite(requests)

        # Each chunk is awaited before the next is sent, so the first failure
        # stops the rest.
        results = [
            await self._transport.insert_batch(batch)
            for batch in batches(requests, batch_size)
        ]
        return merge_batches(results)

    async def search(
        self,
        dense_vector: list[float] | None = None,
        sparse_vector: SparseVector | None = None,
        k: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> list[SearchResponse]:
        request = SearchRequest(
            vector=dense_vector,
            sparse_vector=sparse_vector,
            k=k,
            filter=filter,
        )

        check_finite(request)

        return await self._transport.search(request)

    async def delete(self, vector_id: str) -> bool:
        """Delete a vector by its ID.

        Raises GoVecAPIError if the vector does not exist -- both transports
        report a missing vector as an error, so this does not return False for
        that case.
        """
        response = await self._transport.delete(vector_id)
        return was_deleted(response, vector_id)


class _Connecting[C: AsyncGoVecClient]:
    """What AsyncGoVecClient.connect() returns: await it, or `async with` it.

    Awaiting gives the connected client. As a context manager it connects on
    entry and closes the client on exit.
    """

    def __init__(self, opening: Coroutine[Any, Any, C]):
        self._opening = opening
        self._client: C | None = None

    def __await__(self) -> Generator[Any, None, C]:
        return self._opening.__await__()

    async def __aenter__(self) -> C:
        self._client = await self._opening
        return self._client

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # None when entering failed: the handshake already closed the
        # transport, and there is no client to close.
        if self._client is not None:
            await self._client.aclose()
