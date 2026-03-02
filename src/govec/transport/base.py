from abc import ABC, abstractmethod

from govec.models import (
    BatchInsertResponse,
    DeleteResponse,
    InfoResponse,
    InsertRequest,
    InsertResponse,
    SearchRequest,
    SearchResponse,
)


class BaseTransport(ABC):
    @abstractmethod
    def server_info(self) -> InfoResponse: ...

    @abstractmethod
    def insert(self, request: InsertRequest) -> InsertResponse: ...

    @abstractmethod
    def insert_batch(self, requests: list[InsertRequest]) -> BatchInsertResponse: ...

    @abstractmethod
    def search(self, request: SearchRequest) -> list[SearchResponse]: ...

    @abstractmethod
    def delete(self, id: str) -> DeleteResponse: ...
