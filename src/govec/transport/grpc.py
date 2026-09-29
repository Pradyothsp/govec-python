from typing import override

from govec.models import (
    InfoResponse,
    InsertRequest,
    InsertResponse,
    SearchRequest,
    SearchResponse,
)
from govec.transport.base import BaseTransport

_NOT_IMPLEMENTED = "gRPC transport is not implemented yet."


class GRPCTransport(BaseTransport):
    @override
    def server_info(self) -> InfoResponse:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    @override
    def insert(self, request: InsertRequest) -> InsertResponse:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    @override
    def search(self, request: SearchRequest) -> list[SearchResponse]:
        raise NotImplementedError(_NOT_IMPLEMENTED)
