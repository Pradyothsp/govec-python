"""JSON encoding and decoding for the REST transport.

Kept separate from `rest.py` because these are pure functions with no
dependency on httpx or the connection -- the same split `convert.py` makes for
gRPC's protobuf values.

orjson rather than the standard library: a 1,536-float query took ~1.1 ms to
encode with `json.dumps` in a real query loop and ~0.04 ms with orjson, which
brought a REST search from ~5.4 ms to within ~1 ms of gRPC. orjson also
serializes dataclasses natively, so requests need no `asdict` copy first.
"""

import math
from typing import Any

import orjson

from govec.models import InsertRequest, SearchRequest


def encode_request(request: InsertRequest | SearchRequest) -> bytes:
    _reject_non_finite(request)

    return orjson.dumps(request)


def encode_batch(requests: list[InsertRequest]) -> bytes:
    for request in requests:
        _reject_non_finite(request)

    return orjson.dumps({"vectors": requests})


def decode(content: bytes) -> Any:
    return orjson.loads(content)


def _reject_non_finite(request: InsertRequest | SearchRequest) -> None:
    """Raise ValueError if a request carries NaN or an infinity.

    JSON has no NaN or infinity, and orjson writes them as null rather than
    refusing. The server's decoder leaves a float32 at zero when it reads null,
    so a NaN in a vector would be stored or searched as 0 without any error.
    httpx's own encoder refused these with ValueError, and this keeps that.

    Vectors are checked with `map(math.isfinite)`, which stays in C; the
    recursive walk is only for metadata and filters, which are small.
    """
    if request.vector is not None and not all(map(math.isfinite, request.vector)):
        raise ValueError("vector contains NaN or infinity, which JSON cannot carry")

    sparse = request.sparse_vector
    if sparse is not None and not all(map(math.isfinite, sparse.values)):
        raise ValueError(
            "sparse_vector contains NaN or infinity, which JSON cannot carry"
        )

    extra = request.metadata if isinstance(request, InsertRequest) else request.filter
    if _contains_non_finite(extra):
        raise ValueError(
            "metadata or filter contains NaN or infinity, which JSON cannot carry"
        )


def _contains_non_finite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)

    if isinstance(value, dict):
        return any(_contains_non_finite(v) for v in value.values())

    if isinstance(value, (list, tuple)):
        return any(_contains_non_finite(v) for v in value)

    return False
