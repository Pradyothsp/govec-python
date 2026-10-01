from collections.abc import Iterator
from typing import cast, override
import grpc

from govec.exceptions import GoVecAPIError, GoVecConnectionError
from govec.models import (
    BatchInsertError,
    BatchInsertResponse,
    DeleteResponse,
    DistanceMetric,
    FlushResponse,
    GetByIdResponse,
    GetStatsResponse,
    HealthResponse,
    IndexType,
    InfoResponse,
    InsertRequest,
    InsertResponse,
    ResetResponse,
    SearchRequest,
    SearchResponse,
    SparseVector,
)
from govec.proto import govec_pb2, govec_pb2_grpc
from govec.transport.convert import from_proto_value, to_proto_value
from govec.transport.base import BaseTransport


class GRPCTransport(BaseTransport):
    """gRPC transport implementation for GoVec."""

    def __init__(
        self, host: str, port: int, api_key: str | None = None, tls: bool = True
    ):
        self.target = f"{host}:{port}"
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

        self.stub = govec_pb2_grpc.GoVecServiceStub(self.channel)

    def close(self) -> None:
        """Close underlying gRPC channel."""
        self.channel.close()

    def _handle_rpc_error(self, e: grpc.RpcError) -> None:
        if isinstance(e, grpc.Call):
            code = e.code()
            details = e.details() or ""
            if code == grpc.StatusCode.UNAVAILABLE:
                raise GoVecConnectionError(
                    f"Failed to connect to GoVec gRPC server: {details}"
                ) from e
            # code.value is (number, name) -- label it gRPC so a NOT_FOUND
            # does not render as "HTTP 5".
            raise GoVecAPIError(code.value[0], details, status_label="gRPC") from e
        raise e

    @override
    def health(self) -> HealthResponse:
        try:
            resp = cast(
                govec_pb2.HealthResponse,
                self.stub.Health(
                    govec_pb2.HealthRequest(), metadata=self.metadata, timeout=10.0
                ),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)
            raise

        return HealthResponse(status=resp.status)

    @override
    def server_info(self) -> InfoResponse:
        try:
            resp = cast(
                govec_pb2.InfoResponse,
                self.stub.Info(
                    govec_pb2.InfoRequest(), metadata=self.metadata, timeout=10.0
                ),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)
            raise

        return InfoResponse(
            quantization=resp.quantization,
            index_type=cast(IndexType, resp.index_type),
            distance_metric=cast(DistanceMetric, resp.distance_metric),
            dimensions=resp.dimensions,
            vector_count=resp.vector_count,
            enable_mmap=resp.enable_mmap,
        )

    @override
    def get_stats(self) -> GetStatsResponse:
        try:
            resp = cast(
                govec_pb2.StatsResponse,
                self.stub.Stats(
                    govec_pb2.StatsRequest(), metadata=self.metadata, timeout=10.0
                ),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)
            raise

        return GetStatsResponse(vector_count=resp.vector_count)

    @override
    def flush(self) -> FlushResponse:
        try:
            resp = cast(
                govec_pb2.FlushResponse,
                self.stub.Flush(
                    govec_pb2.FlushRequest(), metadata=self.metadata, timeout=10.0
                ),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)
            raise

        return FlushResponse(status=resp.status)

    @override
    def reset(self) -> ResetResponse:
        try:
            resp = cast(
                govec_pb2.ResetResponse,
                self.stub.Reset(
                    govec_pb2.ResetRequest(), metadata=self.metadata, timeout=10.0
                ),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)
            raise

        return ResetResponse(status=resp.status)

    @override
    def get_by_id(self, vector_id: str) -> GetByIdResponse | None:
        try:
            resp = cast(
                govec_pb2.GetByIDResponse,
                self.stub.GetByID(
                    govec_pb2.GetByIDRequest(id=vector_id),
                    metadata=self.metadata,
                    timeout=10.0,
                ),
            )
        except grpc.RpcError as e:
            # REST returns None for a missing vector rather than raising, and
            # the two transports have to behave the same way behind the client.
            if isinstance(e, grpc.Call) and e.code() == grpc.StatusCode.NOT_FOUND:
                return None
            self._handle_rpc_error(e)
            raise

        # The server omits the sparse message entirely for a dense-only record;
        # proto3 would otherwise hand back a zero-valued one that SparseVector
        # rejects.
        sparse_vector = (
            SparseVector(
                indices=list(resp.sparse.indices),
                values=list(resp.sparse.values),
            )
            if resp.HasField("sparse")
            else None
        )

        return GetByIdResponse(
            id=resp.id,
            vector=list(resp.vector),
            sparse_vector=sparse_vector,
            metadata={k: from_proto_value(v) for k, v in resp.metadata.items()} or None,
        )

    def _to_proto_insert_req(self, request: InsertRequest) -> govec_pb2.InsertRequest:
        sparse_pb = None
        if request.sparse_vector:
            sparse_pb = govec_pb2.SparseVector(
                indices=request.sparse_vector.indices,
                values=request.sparse_vector.values,
            )
        meta_pb = (
            {k: to_proto_value(v) for k, v in request.metadata.items()}
            if request.metadata
            else None
        )
        return govec_pb2.InsertRequest(
            id=request.id,
            vector=request.vector,
            sparse=sparse_pb,
            metadata=meta_pb,
        )

    @override
    def insert(self, request: InsertRequest) -> InsertResponse:
        proto_req = self._to_proto_insert_req(request)
        try:
            resp = cast(
                govec_pb2.InsertResponse,
                self.stub.Insert(proto_req, metadata=self.metadata, timeout=10.0),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)
            raise

        return InsertResponse(status=resp.status)

    @override
    def insert_batch(self, requests: list[InsertRequest]) -> BatchInsertResponse:
        def request_generator() -> Iterator[govec_pb2.InsertRequest]:
            for r in requests:
                yield self._to_proto_insert_req(r)

        try:
            resp = cast(
                govec_pb2.BatchInsertResponse,
                self.stub.BatchInsert(
                    request_generator(), metadata=self.metadata, timeout=60.0
                ),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)
            raise

        return BatchInsertResponse(
            inserted_count=resp.inserted_count,
            errors=[BatchInsertError(id=e.id, error=e.error) for e in resp.errors],
        )

    @override
    def search(self, request: SearchRequest) -> list[SearchResponse]:
        sparse_pb = None
        if request.sparse_vector:
            sparse_pb = govec_pb2.SparseVector(
                indices=request.sparse_vector.indices,
                values=request.sparse_vector.values,
            )

        filters_pb = (
            {k: to_proto_value(v) for k, v in request.filter.items()}
            if request.filter
            else None
        )

        proto_req = govec_pb2.SearchRequest(
            query_vector=request.vector or [],
            sparse_query=sparse_pb,
            k=request.k,
            filters=filters_pb,
        )

        try:
            resp = cast(
                govec_pb2.SearchResponse,
                self.stub.Search(proto_req, metadata=self.metadata, timeout=10.0),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)
            raise

        return [
            SearchResponse(
                id=r.id,
                score=r.score,
                meta={k: from_proto_value(v) for k, v in r.meta.items()},
            )
            for r in resp.results
        ]

    @override
    def delete(self, vector_id: str) -> DeleteResponse:
        try:
            resp = cast(
                govec_pb2.DeleteResponse,
                self.stub.Delete(
                    govec_pb2.DeleteRequest(id=vector_id),
                    metadata=self.metadata,
                    timeout=10.0,
                ),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)
            raise

        return DeleteResponse(id=resp.id, status=resp.status)
