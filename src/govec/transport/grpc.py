from govec.models import (
    InfoResponse,
    InsertRequest,
    InsertResponse,
    SearchRequest,
    SearchResponse,
)
from govec.transport.base import BaseTransport


class GRPCTransport(BaseTransport):
    def server_info(self) -> InfoResponse: ...

    def insert(self, request: InsertRequest) -> InsertResponse: ...

    def search(self, request: SearchRequest) -> list[SearchResponse]: ...
