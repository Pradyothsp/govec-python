"""JSON encoding and decoding for the REST transport.

Kept separate from `rest.py` because these are pure functions with no
dependency on httpx or the connection -- the same split `convert.py` makes for
gRPC's protobuf values.

orjson rather than the standard library: a 1,536-float query took ~1.1 ms to
encode with `json.dumps` in a real query loop and ~0.04 ms with orjson, which
brought a REST search from ~5.4 ms to within ~1 ms of gRPC. orjson also
serializes dataclasses natively, so requests need no `asdict` copy first.

orjson writes NaN and infinity as null rather than refusing them, and the
server reads null into a float32 as 0. Nothing here checks for them: the
client rejects them before any transport sees the request
(`client_logic.check_finite`).
"""

from typing import Any

import orjson

from govec.models import InsertRequest, SearchRequest


def encode_request(request: InsertRequest | SearchRequest) -> bytes:
    return orjson.dumps(request)


def encode_batch(requests: list[InsertRequest]) -> bytes:
    return orjson.dumps({"vectors": requests})


def decode(content: bytes) -> Any:
    return orjson.loads(content)
