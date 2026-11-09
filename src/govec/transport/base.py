from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import TracebackType
from typing import Self

from govec.exceptions import GoVecClientClosedError
from govec.models import (
    BatchInsertResponse,
    DeleteResponse,
    InfoResponse,
    InsertRequest,
    InsertResponse,
    ResetResponse,
    SearchRequest,
    SearchResponse,
    GetStatsResponse,
    FlushResponse,
    GetByIdResponse,
    HealthResponse,
)


DEFAULT_TIMEOUT = 10.0
DEFAULT_BATCH_TIMEOUT = 60.0


@dataclass(frozen=True)
class Timeouts:
    """Seconds a call may take before GoVecTimeoutError; None waits forever.

    `batch` is separate because one insert_batch carries up to a whole
    insert_many chunk and legitimately takes far longer than a query. Both
    transports apply both the same way: REST once used 10 s for a batch while
    gRPC used 60 s, so the same batch could time out on one and not the other.
    """

    call: float | None = DEFAULT_TIMEOUT
    batch: float | None = DEFAULT_BATCH_TIMEOUT

    def __post_init__(self) -> None:
        # Named after the client's arguments, which is what a caller passed.
        for name, value in (("timeout", self.call), ("batch_timeout", self.batch)):
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be positive or None, got {value}")


class _Closable:
    """The closed flag and its guard, shared by the sync and async contracts."""

    # Set by close()/aclose(). Subclasses must not assign it in __init__ --
    # reading it off the class keeps a transport that forgot to call
    # super().__init__() from looking permanently closed.
    _closed: bool = False

    def _ensure_open(self) -> None:
        """Raise if this transport has already been closed."""
        if self._closed:
            raise GoVecClientClosedError(
                f"{type(self).__name__} is closed; create a new client to make "
                "further requests"
            )


class BaseTransport(_Closable, ABC):
    @abstractmethod
    def _release(self) -> None:
        """Release the underlying connection -- the httpx client or gRPC channel.

        Implemented by each transport; callers use close(), which makes the
        release idempotent and flips the closed flag.
        """

    def close(self) -> None:
        """Close the underlying connection. Safe to call more than once."""
        if self._closed:
            return

        self._closed = True
        self._release()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # Returning None (not False) is deliberate: an exception raised inside
        # the with-block propagates rather than being swallowed.
        self.close()

    @abstractmethod
    def health(self) -> HealthResponse: ...

    @abstractmethod
    def server_info(self) -> InfoResponse: ...

    @abstractmethod
    def get_stats(self) -> GetStatsResponse: ...

    @abstractmethod
    def flush(self) -> FlushResponse: ...

    @abstractmethod
    def reset(self) -> ResetResponse: ...

    @abstractmethod
    def get_by_id(self, vector_id: str) -> GetByIdResponse | None: ...

    @abstractmethod
    def insert(self, request: InsertRequest) -> InsertResponse: ...

    @abstractmethod
    def insert_batch(self, requests: list[InsertRequest]) -> BatchInsertResponse: ...

    @abstractmethod
    def search(self, request: SearchRequest) -> list[SearchResponse]: ...

    @abstractmethod
    def delete(self, vector_id: str) -> DeleteResponse: ...


class AsyncBaseTransport(_Closable, ABC):
    """BaseTransport's contract with every call awaited.

    A separate ABC rather than async methods on BaseTransport: a class can't
    be both, and keeping them apart means a missing async implementation
    still fails at construction.
    """

    @abstractmethod
    async def _release(self) -> None:
        """Release the underlying connection; callers use aclose()."""

    async def aclose(self) -> None:
        """Close the underlying connection. Safe to call more than once."""
        if self._closed:
            return

        self._closed = True
        await self._release()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # Returning None (not False): an exception from inside the block
        # propagates rather than being swallowed.
        await self.aclose()

    @abstractmethod
    async def health(self) -> HealthResponse: ...

    @abstractmethod
    async def server_info(self) -> InfoResponse: ...

    @abstractmethod
    async def get_stats(self) -> GetStatsResponse: ...

    @abstractmethod
    async def flush(self) -> FlushResponse: ...

    @abstractmethod
    async def reset(self) -> ResetResponse: ...

    @abstractmethod
    async def get_by_id(self, vector_id: str) -> GetByIdResponse | None: ...

    @abstractmethod
    async def insert(self, request: InsertRequest) -> InsertResponse: ...

    @abstractmethod
    async def insert_batch(
        self, requests: list[InsertRequest]
    ) -> BatchInsertResponse: ...

    @abstractmethod
    async def search(self, request: SearchRequest) -> list[SearchResponse]: ...

    @abstractmethod
    async def delete(self, vector_id: str) -> DeleteResponse: ...
