from types import TracebackType
from typing import Any, Literal, Self, assert_never

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
    GetByIdResponse,
    InfoResponse,
    InsertRequest,
    ResetResponse,
    SearchRequest,
    SearchResponse,
    SparseVector,
    GetStatsResponse,
    FlushResponse,
    HealthResponse,
)
from govec.transport.base import (
    DEFAULT_BATCH_TIMEOUT,
    DEFAULT_TIMEOUT,
    BaseTransport,
    Timeouts,
)

Protocol = Literal["rest", "grpc"]


def _open_transport(
    host: str,
    port: int,
    api_key: str,
    protocol: Protocol,
    tls: bool,
    timeouts: Timeouts,
) -> BaseTransport:
    # Imported here so a REST user never loads grpc and a gRPC user never
    # loads httpx.
    if protocol == "rest":
        from govec.transport.rest import RESTTransport

        return RESTTransport(host, port, api_key, tls=tls, timeouts=timeouts)

    if protocol == "grpc":
        from govec.transport.grpc import GRPCTransport

        return GRPCTransport(host, port, api_key, tls=tls, timeouts=timeouts)

    assert_never(protocol)


class GoVecClient:
    """
    GoVec Official Client for Python.

    This client provides methods to interact with the GoVec API,
    allowing users to perform various operations such as retrieving data, sending requests, and managing their account.

    The client is designed to be straightforward to use and integrates seamlessly with the GoVec platform.
    """

    host: str
    port: int
    protocol: Protocol
    dimensions: int
    enable_mmap: bool
    _transport: BaseTransport

    def __init__(
        self,
        host: str,
        port: int,
        api_key: str,
        protocol: Protocol,
        tls: bool = True,
        timeout: float | None = DEFAULT_TIMEOUT,
        batch_timeout: float | None = DEFAULT_BATCH_TIMEOUT,
    ):
        # Built first so a bad timeout raises before any connection is opened.
        timeouts = Timeouts(call=timeout, batch=batch_timeout)

        transport = _open_transport(host, port, api_key, protocol, tls, timeouts)
        self._attach(transport, host, port, protocol)

    @classmethod
    def _from_transport(
        cls, transport: BaseTransport, host: str, port: int, protocol: Protocol
    ) -> Self:
        """Build a client over a transport that is already open.

        Not public. The constructor raises before returning anything when the
        handshake fails, so this is the only way for a test to hold the
        transport afterwards and see that it was closed.
        """
        client = cls.__new__(cls)
        client._attach(transport, host, port, protocol)
        return client

    def _attach(
        self, transport: BaseTransport, host: str, port: int, protocol: Protocol
    ) -> None:
        self.host = host
        self.port = port
        self.protocol = protocol
        self._transport = transport

        # The Pre-Flight Handshake
        try:
            server_config = self._transport.server_info()
            self.dimensions = server_config.dimensions
            self.enable_mmap = server_config.enable_mmap

        except BaseException:
            # The transport already holds a connection pool or an open channel.
            # A failed handshake raises instead of returning an object, so the
            # caller has nothing to close -- this is the only chance to do it.
            self._transport.close()
            raise

    def close(self) -> None:
        """Release the underlying connection. Safe to call more than once.

        Prefer the context manager where the client's lifetime fits a block;
        call this directly when it does not, such as from a web framework's
        shutdown hook.
        """
        self._transport.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # Returning None rather than False: an exception from inside the
        # with-block propagates instead of being swallowed.
        self.close()

    def health(self) -> HealthResponse:
        """
        Check that the server is reachable and serving.
        """
        return self._transport.health()

    def info(self) -> InfoResponse:
        """
        Retrieve server information.
        """
        return self._transport.server_info()

    def get_stats(self) -> GetStatsResponse:
        """
        Retrieve collection statistics, such as the total number of vectors stored.
        """
        return self._transport.get_stats()

    def flush(self) -> FlushResponse:
        """
        Forces the database to flush in-memory structures (like the HNSW graph) to disk.
        """
        return self._transport.flush()

    def reset(self) -> ResetResponse:
        """
        Clears all vectors, ID mappings, and the WAL. Does not persist the cleared
        state to disk -- call flush() afterward if the reset should survive a restart.
        """
        return self._transport.reset()

    def get_by_id(self, vector_id: str) -> GetByIdResponse | None:
        """
        Retrieve a vector by its ID.
        """
        return self._transport.get_by_id(vector_id)

    def insert(
        self,
        vector_id: str,
        dense_vector: list[float],
        sparse_vector: SparseVector | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Inserts a single dense vector into the database.
        """
        check_width(dense_vector, self.dimensions, self.enable_mmap)

        request = InsertRequest(
            id=vector_id,
            vector=dense_vector,
            sparse_vector=sparse_vector,
            metadata=metadata,
        )

        check_finite(request)

        self._transport.insert(request)
        return True

    def insert_many(
        self, requests: list[InsertRequest], batch_size: int = 500
    ) -> BatchInsertResponse:
        """
        Chunks a large list of vectors and inserts them in optimized batches.
        Returns a BatchInsertResponse with the total inserted count and any per-vector errors.
        """
        check_batch_widths(requests, self.dimensions, self.enable_mmap)
        check_all_finite(requests)

        # A generator, so batches still go one at a time and the first failure
        # stops the rest from being sent.
        return merge_batches(
            self._transport.insert_batch(batch)
            for batch in batches(requests, batch_size)
        )

    def search(
        self,
        dense_vector: list[float] | None = None,
        sparse_vector: SparseVector | None = None,
        k: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> list[SearchResponse]:
        """
        Search for the nearest vectors.
        """
        request = SearchRequest(
            vector=dense_vector,
            sparse_vector=sparse_vector,
            k=k,
            filter=filter,
        )

        check_finite(request)

        return self._transport.search(request)

    def delete(self, vector_id: str) -> bool:
        """
        Deletes a vector by its ID.

        Raises GoVecAPIError if the vector does not exist -- both transports
        report a missing vector as an error, so this does not return False for
        that case.
        """
        response = self._transport.delete(vector_id)
        return was_deleted(response, vector_id)
