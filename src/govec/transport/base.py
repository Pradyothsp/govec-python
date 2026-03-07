from abc import ABC, abstractmethod

from govec.models import (
    BatchInsertResponse,
    DeleteResponse,
    InfoResponse,
    InsertRequest,
    InsertResponse,
    SearchRequest,
    SearchResponse,
    GetStatsResponse,
    FlushResponse,
    GetByIdResponse,
)


class BaseTransport(ABC):
    @abstractmethod
    def server_info(self) -> InfoResponse: ...

    @abstractmethod
    def get_stats(self) -> GetStatsResponse: ...

    @abstractmethod
    def flush(self) -> FlushResponse: ...

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
