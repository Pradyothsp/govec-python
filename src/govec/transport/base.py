from abc import ABC, abstractmethod
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


class BaseTransport(ABC):
    # Set by close(). Subclasses must not assign it in __init__ -- reading it
    # off the class keeps a transport that forgot to call super().__init__()
    # from looking permanently closed.
    _closed: bool = False

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

    def _ensure_open(self) -> None:
        """Raise if this transport has already been closed."""
        if self._closed:
            raise GoVecClientClosedError(
                f"{type(self).__name__} is closed; create a new client to make "
                "further requests"
            )

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
