"""An in-process GoVec gRPC server for unit tests: the gRPC side's respx.

The `grpc_server` fixture in `tests/conftest.py` starts one on a free port.
The real transports talk to it over a real channel; only the server is
replaced. It answers every RPC with a canned reply, which a test can swap
per RPC, or fails one with a status, and it records what each call carried.
"""

from collections.abc import Iterator
from typing import NamedTuple, cast, override

import grpc
from google.protobuf.message import Message

from govec.proto import govec_pb2, govec_pb2_grpc

HOST = "localhost"

# How the server reports a call that carried no deadline: time_remaining() is
# the distance to "infinite future", about 9.2e18 s, rather than None.
_NO_DEADLINE_AFTER_SECONDS = 1e12


class Call(NamedTuple):
    rpc: str
    request: Message | list[Message]
    metadata: dict[str, str]
    # Seconds left on the call's deadline when it arrived; None if it had none.
    time_remaining: float | None


class Failure(NamedTuple):
    code: grpc.StatusCode
    details: str


def default_replies() -> dict[str, Message]:
    return {
        "Health": govec_pb2.HealthResponse(status="ok"),
        "Info": govec_pb2.InfoResponse(
            quantization="none",
            index_type="brute",
            distance_metric="cosine",
            dimensions=3,
            vector_count=0,
            enable_mmap=False,
            version="dev",
        ),
        "Stats": govec_pb2.StatsResponse(vector_count=0),
        "Flush": govec_pb2.FlushResponse(status="flushed"),
        "Reset": govec_pb2.ResetResponse(status="reset"),
        "GetByID": govec_pb2.GetByIDResponse(id="a", vector=[1.0]),
        "Insert": govec_pb2.InsertResponse(status="inserted"),
        "BatchInsert": govec_pb2.BatchInsertResponse(inserted_count=0),
        "Search": govec_pb2.SearchResponse(),
        "Delete": govec_pb2.DeleteResponse(id="a", status="deleted"),
    }


def _deadline(context: grpc.ServicerContext) -> float | None:
    # grpc's stubs leave time_remaining() untyped.
    remaining = cast(float | None, context.time_remaining())
    if remaining is None or remaining > _NO_DEADLINE_AFTER_SECONDS:
        return None

    return remaining


class GoVecServicer(govec_pb2_grpc.GoVecServiceServicer):
    def __init__(self) -> None:
        self.calls: list[Call] = []
        self.replies = default_replies()
        self.failures: dict[str, Failure] = {}

    def _answer(
        self,
        rpc: str,
        request: Message | list[Message],
        context: grpc.ServicerContext,
    ) -> Message:
        self.calls.append(
            Call(
                rpc=rpc,
                request=request,
                metadata={m.key: m.value for m in context.invocation_metadata()},
                time_remaining=_deadline(context),
            )
        )

        if failure := self.failures.get(rpc):
            context.abort(failure.code, failure.details)

        return self.replies[rpc]

    @override
    def Health(self, request: Message, context: grpc.ServicerContext) -> Message:
        return self._answer("Health", request, context)

    @override
    def Info(self, request: Message, context: grpc.ServicerContext) -> Message:
        return self._answer("Info", request, context)

    @override
    def Stats(self, request: Message, context: grpc.ServicerContext) -> Message:
        return self._answer("Stats", request, context)

    @override
    def Flush(self, request: Message, context: grpc.ServicerContext) -> Message:
        return self._answer("Flush", request, context)

    @override
    def Reset(self, request: Message, context: grpc.ServicerContext) -> Message:
        return self._answer("Reset", request, context)

    @override
    def GetByID(self, request: Message, context: grpc.ServicerContext) -> Message:
        return self._answer("GetByID", request, context)

    @override
    def Insert(self, request: Message, context: grpc.ServicerContext) -> Message:
        return self._answer("Insert", request, context)

    @override
    def BatchInsert(
        self, request_iterator: Iterator[Message], context: grpc.ServicerContext
    ) -> Message:
        return self._answer("BatchInsert", list(request_iterator), context)

    @override
    def Search(self, request: Message, context: grpc.ServicerContext) -> Message:
        return self._answer("Search", request, context)

    @override
    def Delete(self, request: Message, context: grpc.ServicerContext) -> Message:
        return self._answer("Delete", request, context)


class RunningServer(NamedTuple):
    servicer: GoVecServicer
    port: int
