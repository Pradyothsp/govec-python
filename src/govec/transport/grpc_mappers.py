"""Maps between the SDK's models and the gRPC messages, and gRPC errors onto
GoVec exceptions.

Kept apart from `grpc.py` so the sync and async gRPC transports share them:
the two differ only in how a call is made, and building the request, reading
the response and translating a failure live here once.
"""

from typing import NoReturn, cast

import grpc
import grpc.aio

from govec.exceptions import GoVecAPIError, GoVecConnectionError, GoVecTimeoutError
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
from govec.proto import govec_pb2
from govec.transport.convert import from_proto_value, to_proto_value


# --- errors -------------------------------------------------------------------


def status_of(e: grpc.RpcError) -> grpc.StatusCode | None:
    """The status code of a failed call, or None if the error carries none.

    Sync calls fail with a `grpc.Call`; `grpc.aio` calls fail with an
    `AioRpcError`, which is *not* a `grpc.Call`. Checking only `grpc.Call`
    would let every async failure escape untranslated.
    """
    if isinstance(e, (grpc.Call, grpc.aio.AioRpcError)):
        # grpc.Call's stubs leave code() untyped.
        return cast(grpc.StatusCode, e.code())

    return None


def raise_rpc_error(e: grpc.RpcError, target: str) -> NoReturn:
    code = status_of(e)
    if code is None:
        raise e

    # Both error types expose details(); only AioRpcError types it as optional.
    details = cast(grpc.Call | grpc.aio.AioRpcError, e).details() or ""

    if code == grpc.StatusCode.UNAVAILABLE:
        raise GoVecConnectionError(
            f"Failed to connect to GoVec gRPC server: {details}"
        ) from e

    if code == grpc.StatusCode.DEADLINE_EXCEEDED:
        # Not an API error: the server never answered. Matches what REST
        # reports for httpx.TimeoutException.
        raise GoVecTimeoutError(
            f"GoVec gRPC server at {target} did not respond within the "
            f"deadline: {details}"
        ) from e

    # code.value is (number, name) -- label it gRPC so a NOT_FOUND does not
    # render as "HTTP 5".
    raise GoVecAPIError(code.value[0], details, status_label="gRPC") from e


# --- requests -----------------------------------------------------------------


def _sparse_to_proto(sparse: SparseVector | None) -> govec_pb2.SparseVector | None:
    if not sparse:
        return None

    return govec_pb2.SparseVector(indices=sparse.indices, values=sparse.values)


def insert_request_to_proto(request: InsertRequest) -> govec_pb2.InsertRequest:
    meta_pb = (
        {k: to_proto_value(v) for k, v in request.metadata.items()}
        if request.metadata
        else None
    )

    return govec_pb2.InsertRequest(
        id=request.id,
        vector=request.vector,
        sparse=_sparse_to_proto(request.sparse_vector),
        metadata=meta_pb,
    )


def search_request_to_proto(request: SearchRequest) -> govec_pb2.SearchRequest:
    filters_pb = (
        {k: to_proto_value(v) for k, v in request.filter.items()}
        if request.filter
        else None
    )

    return govec_pb2.SearchRequest(
        query_vector=request.vector or [],
        sparse_query=_sparse_to_proto(request.sparse_vector),
        k=request.k,
        filters=filters_pb,
    )


# --- responses ----------------------------------------------------------------


def health_from_proto(resp: govec_pb2.HealthResponse) -> HealthResponse:
    return HealthResponse(status=resp.status)


def info_from_proto(resp: govec_pb2.InfoResponse) -> InfoResponse:
    return InfoResponse(
        quantization=resp.quantization,
        index_type=cast(IndexType, resp.index_type),
        distance_metric=cast(DistanceMetric, resp.distance_metric),
        dimensions=resp.dimensions,
        vector_count=resp.vector_count,
        enable_mmap=resp.enable_mmap,
        version=resp.version,
    )


def stats_from_proto(resp: govec_pb2.StatsResponse) -> GetStatsResponse:
    return GetStatsResponse(vector_count=resp.vector_count)


def flush_from_proto(resp: govec_pb2.FlushResponse) -> FlushResponse:
    return FlushResponse(status=resp.status)


def reset_from_proto(resp: govec_pb2.ResetResponse) -> ResetResponse:
    return ResetResponse(status=resp.status)


def get_by_id_from_proto(resp: govec_pb2.GetByIDResponse) -> GetByIdResponse:
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


def insert_from_proto(resp: govec_pb2.InsertResponse) -> InsertResponse:
    return InsertResponse(status=resp.status)


def batch_insert_from_proto(
    resp: govec_pb2.BatchInsertResponse,
) -> BatchInsertResponse:
    return BatchInsertResponse(
        inserted_count=resp.inserted_count,
        errors=[BatchInsertError(id=e.id, error=e.error) for e in resp.errors],
    )


def search_from_proto(resp: govec_pb2.SearchResponse) -> list[SearchResponse]:
    return [
        SearchResponse(
            id=r.id,
            score=r.score,
            # A protobuf map is always present, so an empty one is how gRPC
            # says "no metadata". REST omits the key; both become None.
            meta={k: from_proto_value(v) for k, v in r.meta.items()} or None,
        )
        for r in resp.results
    ]


def delete_from_proto(resp: govec_pb2.DeleteResponse) -> DeleteResponse:
    return DeleteResponse(id=resp.id, status=resp.status)
