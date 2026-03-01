from abc import ABC, abstractmethod

from govec.models import (
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
    def search(self, request: SearchRequest) -> list[SearchResponse]: ...
