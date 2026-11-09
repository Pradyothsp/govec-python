from collections.abc import Iterator
from typing import cast, override

import grpc

from govec.models import (
    BatchInsertResponse,
    DeleteResponse,
    FlushResponse,
    GetByIdResponse,
    GetStatsResponse,
    HealthResponse,
    InfoResponse,
    InsertRequest,
    InsertResponse,
    ResetResponse,
    SearchRequest,
    SearchResponse,
)
from govec.proto import govec_pb2, govec_pb2_grpc
from govec.transport import grpc_mappers as mappers
from govec.transport.base import BaseTransport, Timeouts


class GRPCTransport(BaseTransport):
    """gRPC transport implementation for GoVec."""

    def __init__(
        self,
        host: str,
        port: int,
        api_key: str | None = None,
        tls: bool = True,
        timeouts: Timeouts = Timeouts(),
    ):
        self.target = f"{host}:{port}"
        self.timeouts = timeouts
        self.api_key = api_key
        self.metadata: list[tuple[str, str]] = []
        if api_key:
            self.metadata.append(("authorization", f"Bearer {api_key}"))

        options = [
            ("grpc.max_receive_message_length", 64 * 1024 * 1024),
            ("grpc.max_send_message_length", 64 * 1024 * 1024),
        ]
        if tls:
            credentials = grpc.ssl_channel_credentials()
            self.channel = grpc.secure_channel(
                self.target, credentials, options=options
            )
        else:
            self.channel = grpc.insecure_channel(self.target, options=options)

        self._stub = govec_pb2_grpc.GoVecServiceStub(self.channel)

    @property
    def stub(self) -> govec_pb2_grpc.GoVecServiceStub:
        """The service stub, refused once this transport has been closed.

        Guarding here rather than at the top of all ten RPC methods means a
        method added later cannot forget the check -- there is no way to reach
        the stub that bypasses it. Invoking an RPC on a closed channel
        otherwise fails somewhere inside grpc with a message that says nothing
        about this SDK.
        """
        self._ensure_open()
        return self._stub

    @override
    def _release(self) -> None:
        self.channel.close()

    @override
    def health(self) -> HealthResponse:
        try:
            resp = cast(
                govec_pb2.HealthResponse,
                self.stub.Health(
                    govec_pb2.HealthRequest(),
                    metadata=self.metadata,
                    timeout=self.timeouts.call,
                ),
            )
        except grpc.RpcError as e:
            mappers.raise_rpc_error(e, self.target)

        return mappers.health_from_proto(resp)

    @override
    def server_info(self) -> InfoResponse:
        try:
            resp = cast(
                govec_pb2.InfoResponse,
                self.stub.Info(
                    govec_pb2.InfoRequest(),
                    metadata=self.metadata,
                    timeout=self.timeouts.call,
                ),
            )
        except grpc.RpcError as e:
            mappers.raise_rpc_error(e, self.target)

        return mappers.info_from_proto(resp)

    @override
    def get_stats(self) -> GetStatsResponse:
        try:
            resp = cast(
                govec_pb2.StatsResponse,
                self.stub.Stats(
                    govec_pb2.StatsRequest(),
                    metadata=self.metadata,
                    timeout=self.timeouts.call,
                ),
            )
        except grpc.RpcError as e:
            mappers.raise_rpc_error(e, self.target)

        return mappers.stats_from_proto(resp)

    @override
    def flush(self) -> FlushResponse:
        try:
            resp = cast(
                govec_pb2.FlushResponse,
                self.stub.Flush(
                    govec_pb2.FlushRequest(),
                    metadata=self.metadata,
                    timeout=self.timeouts.call,
                ),
            )
        except grpc.RpcError as e:
            mappers.raise_rpc_error(e, self.target)

        return mappers.flush_from_proto(resp)

    @override
    def reset(self) -> ResetResponse:
        try:
            resp = cast(
                govec_pb2.ResetResponse,
                self.stub.Reset(
                    govec_pb2.ResetRequest(),
                    metadata=self.metadata,
                    timeout=self.timeouts.call,
                ),
            )
        except grpc.RpcError as e:
            mappers.raise_rpc_error(e, self.target)

        return mappers.reset_from_proto(resp)

    @override
    def get_by_id(self, vector_id: str) -> GetByIdResponse | None:
        try:
            resp = cast(
                govec_pb2.GetByIDResponse,
                self.stub.GetByID(
                    govec_pb2.GetByIDRequest(id=vector_id),
                    metadata=self.metadata,
                    timeout=self.timeouts.call,
                ),
            )
        except grpc.RpcError as e:
            # REST returns None for a missing vector rather than raising, and
            # the two transports have to behave the same way behind the client.
            if mappers.status_of(e) == grpc.StatusCode.NOT_FOUND:
                return None
            mappers.raise_rpc_error(e, self.target)

        return mappers.get_by_id_from_proto(resp)

    @override
    def insert(self, request: InsertRequest) -> InsertResponse:
        proto_req = mappers.insert_request_to_proto(request)

        try:
            resp = cast(
                govec_pb2.InsertResponse,
                self.stub.Insert(
                    proto_req, metadata=self.metadata, timeout=self.timeouts.call
                ),
            )
        except grpc.RpcError as e:
            mappers.raise_rpc_error(e, self.target)

        return mappers.insert_from_proto(resp)

    @override
    def insert_batch(self, requests: list[InsertRequest]) -> BatchInsertResponse:
        def request_generator() -> Iterator[govec_pb2.InsertRequest]:
            for r in requests:
                yield mappers.insert_request_to_proto(r)

        try:
            resp = cast(
                govec_pb2.BatchInsertResponse,
                self.stub.BatchInsert(
                    request_generator(),
                    metadata=self.metadata,
                    timeout=self.timeouts.batch,
                ),
            )
        except grpc.RpcError as e:
            mappers.raise_rpc_error(e, self.target)

        return mappers.batch_insert_from_proto(resp)

    @override
    def search(self, request: SearchRequest) -> list[SearchResponse]:
        proto_req = mappers.search_request_to_proto(request)

        try:
            resp = cast(
                govec_pb2.SearchResponse,
                self.stub.Search(
                    proto_req, metadata=self.metadata, timeout=self.timeouts.call
                ),
            )
        except grpc.RpcError as e:
            mappers.raise_rpc_error(e, self.target)

        return mappers.search_from_proto(resp)

    @override
    def delete(self, vector_id: str) -> DeleteResponse:
        try:
            resp = cast(
                govec_pb2.DeleteResponse,
                self.stub.Delete(
                    govec_pb2.DeleteRequest(id=vector_id),
                    metadata=self.metadata,
                    timeout=self.timeouts.call,
                ),
            )
        except grpc.RpcError as e:
            mappers.raise_rpc_error(e, self.target)

        return mappers.delete_from_proto(resp)
