import asyncio
from collections.abc import Iterator
from typing import NamedTuple, cast, override

import grpc
import grpc.aio

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
from govec.transport.base import AsyncBaseTransport, BaseTransport, Timeouts

_MAX_MESSAGE_BYTES = 64 * 1024 * 1024


class _Channel(NamedTuple):
    target: str
    metadata: list[tuple[str, str]]
    options: list[tuple[str, int]]
    credentials: grpc.ChannelCredentials | None


def _channel(host: str, port: int, api_key: str | None, tls: bool) -> _Channel:
    metadata: list[tuple[str, str]] = []
    if api_key:
        metadata.append(("authorization", f"Bearer {api_key}"))

    return _Channel(
        target=f"{host}:{port}",
        metadata=metadata,
        options=[
            ("grpc.max_receive_message_length", _MAX_MESSAGE_BYTES),
            ("grpc.max_send_message_length", _MAX_MESSAGE_BYTES),
        ],
        credentials=grpc.ssl_channel_credentials() if tls else None,
    )


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
        config = _channel(host, port, api_key, tls)
        self.target = config.target
        self.metadata = config.metadata
        self.timeouts = timeouts

        if config.credentials is not None:
            self.channel = grpc.secure_channel(
                config.target, config.credentials, options=config.options
            )
        else:
            self.channel = grpc.insecure_channel(config.target, options=config.options)

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


class AsyncGRPCTransport(AsyncBaseTransport):
    """GRPCTransport over grpc.aio.

    Everything but the call is shared with GRPCTransport: the channel settings
    (`_channel`), request and response mappers and error translation. Keep
    each method's RPC and timeout in step with the sync class above.

    Must be created inside a running event loop. A grpc.aio channel binds to
    the loop it is created on; made outside one, grpc quietly starts a loop of
    its own that the caller's code never runs on, and every call then fails
    with asyncio's RuntimeError about a Future attached to a different loop.
    """

    def __init__(
        self,
        host: str,
        port: int,
        api_key: str | None = None,
        tls: bool = True,
        timeouts: Timeouts = Timeouts(),
    ):
        try:
            asyncio.get_running_loop()
        except RuntimeError as e:
            raise RuntimeError(
                "AsyncGRPCTransport must be created inside a running event loop"
            ) from e

        config = _channel(host, port, api_key, tls)
        self.target = config.target
        self.metadata = config.metadata
        self.timeouts = timeouts

        if config.credentials is not None:
            self.channel = grpc.aio.secure_channel(
                config.target, config.credentials, options=config.options
            )
        else:
            self.channel = grpc.aio.insecure_channel(
                config.target, options=config.options
            )

        self._stub = govec_pb2_grpc.GoVecServiceStub(self.channel)

    @property
    def stub(self) -> govec_pb2_grpc.GoVecServiceStub:
        # Guarded here for the same reason as GRPCTransport.stub.
        self._ensure_open()
        return self._stub

    @override
    async def _release(self) -> None:
        await self.channel.close()

    @override
    async def health(self) -> HealthResponse:
        try:
            resp = cast(
                govec_pb2.HealthResponse,
                await self.stub.Health(
                    govec_pb2.HealthRequest(),
                    metadata=self.metadata,
                    timeout=self.timeouts.call,
                ),
            )
        except grpc.RpcError as e:
            mappers.raise_rpc_error(e, self.target)

        return mappers.health_from_proto(resp)

    @override
    async def server_info(self) -> InfoResponse:
        try:
            resp = cast(
                govec_pb2.InfoResponse,
                await self.stub.Info(
                    govec_pb2.InfoRequest(),
                    metadata=self.metadata,
                    timeout=self.timeouts.call,
                ),
            )
        except grpc.RpcError as e:
            mappers.raise_rpc_error(e, self.target)

        return mappers.info_from_proto(resp)

    @override
    async def get_stats(self) -> GetStatsResponse:
        try:
            resp = cast(
                govec_pb2.StatsResponse,
                await self.stub.Stats(
                    govec_pb2.StatsRequest(),
                    metadata=self.metadata,
                    timeout=self.timeouts.call,
                ),
            )
        except grpc.RpcError as e:
            mappers.raise_rpc_error(e, self.target)

        return mappers.stats_from_proto(resp)

    @override
    async def flush(self) -> FlushResponse:
        try:
            resp = cast(
                govec_pb2.FlushResponse,
                await self.stub.Flush(
                    govec_pb2.FlushRequest(),
                    metadata=self.metadata,
                    timeout=self.timeouts.call,
                ),
            )
        except grpc.RpcError as e:
            mappers.raise_rpc_error(e, self.target)

        return mappers.flush_from_proto(resp)

    @override
    async def reset(self) -> ResetResponse:
        try:
            resp = cast(
                govec_pb2.ResetResponse,
                await self.stub.Reset(
                    govec_pb2.ResetRequest(),
                    metadata=self.metadata,
                    timeout=self.timeouts.call,
                ),
            )
        except grpc.RpcError as e:
            mappers.raise_rpc_error(e, self.target)

        return mappers.reset_from_proto(resp)

    @override
    async def get_by_id(self, vector_id: str) -> GetByIdResponse | None:
        try:
            resp = cast(
                govec_pb2.GetByIDResponse,
                await self.stub.GetByID(
                    govec_pb2.GetByIDRequest(id=vector_id),
                    metadata=self.metadata,
                    timeout=self.timeouts.call,
                ),
            )
        except grpc.RpcError as e:
            if mappers.status_of(e) == grpc.StatusCode.NOT_FOUND:
                return None
            mappers.raise_rpc_error(e, self.target)

        return mappers.get_by_id_from_proto(resp)

    @override
    async def insert(self, request: InsertRequest) -> InsertResponse:
        proto_req = mappers.insert_request_to_proto(request)

        try:
            resp = cast(
                govec_pb2.InsertResponse,
                await self.stub.Insert(
                    proto_req, metadata=self.metadata, timeout=self.timeouts.call
                ),
            )
        except grpc.RpcError as e:
            mappers.raise_rpc_error(e, self.target)

        return mappers.insert_from_proto(resp)

    @override
    async def insert_batch(self, requests: list[InsertRequest]) -> BatchInsertResponse:
        # grpc.aio streams a plain iterable as well as an async one; converting
        # lazily keeps one batch's protos from all being built up front.
        proto_reqs = (mappers.insert_request_to_proto(r) for r in requests)

        try:
            resp = cast(
                govec_pb2.BatchInsertResponse,
                await self.stub.BatchInsert(
                    proto_reqs, metadata=self.metadata, timeout=self.timeouts.batch
                ),
            )
        except grpc.RpcError as e:
            mappers.raise_rpc_error(e, self.target)

        return mappers.batch_insert_from_proto(resp)

    @override
    async def search(self, request: SearchRequest) -> list[SearchResponse]:
        proto_req = mappers.search_request_to_proto(request)

        try:
            resp = cast(
                govec_pb2.SearchResponse,
                await self.stub.Search(
                    proto_req, metadata=self.metadata, timeout=self.timeouts.call
                ),
            )
        except grpc.RpcError as e:
            mappers.raise_rpc_error(e, self.target)

        return mappers.search_from_proto(resp)

    @override
    async def delete(self, vector_id: str) -> DeleteResponse:
        try:
            resp = cast(
                govec_pb2.DeleteResponse,
                await self.stub.Delete(
                    govec_pb2.DeleteRequest(id=vector_id),
                    metadata=self.metadata,
                    timeout=self.timeouts.call,
                ),
            )
        except grpc.RpcError as e:
            mappers.raise_rpc_error(e, self.target)

        return mappers.delete_from_proto(resp)
