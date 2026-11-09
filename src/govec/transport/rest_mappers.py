"""Maps REST responses onto the SDK's models, and httpx failures onto GoVec
exceptions.

Kept apart from `rest.py` so the sync and async REST transports share them:
the two differ only in how a request is sent, and everything after the
response arrives lives here once.

Responses are built field by field, never by splatting the JSON: a field the
server adds in a later release must not break a client built before it.
"""

from typing import Any, NoReturn

import httpx
import orjson

from govec.exceptions import GoVecAPIError, GoVecConnectionError, GoVecTimeoutError
from govec.models import (
    BatchInsertError,
    BatchInsertResponse,
    DeleteResponse,
    FlushResponse,
    GetByIdResponse,
    GetStatsResponse,
    HealthResponse,
    InfoResponse,
    InsertResponse,
    ResetResponse,
    SearchResponse,
    SparseVector,
)
from govec.transport.json_codec import decode


def raise_request_error(
    e: httpx.RequestError, root_url: str, read_timeout: float | None
) -> NoReturn:
    """Translate a request that never completed into a GoVec exception.

    Only failures to *complete* a request come here. A response carrying an
    error status is the server answering, and unwrap() reports that.
    """
    # Checked first: TimeoutException is a subclass of RequestError.
    if isinstance(e, httpx.TimeoutException):
        raise GoVecTimeoutError(
            f"GoVec server at {root_url} did not respond within {read_timeout}s: {e}"
        ) from e

    raise GoVecConnectionError(
        f"Failed to reach the GoVec server at {root_url}: {e}"
    ) from e


_SNIPPET_CHARS = 200


def unwrap(response: httpx.Response, expected_status: int = 200) -> Any:
    """Return the envelope's `data`, or raise GoVecAPIError.

    Not every response comes from GoVec: a proxy or load balancer in front of
    it answers with its own HTML page, or an empty body, for a 502 or 503.
    Decoding those used to leak orjson.JSONDecodeError, and a body that was
    JSON but not GoVec's envelope leaked KeyError or AttributeError. Whatever
    arrives, the caller gets GoVecAPIError carrying the status, and the
    server's message or else the start of the body.
    """
    try:
        body = decode(response.content)
    except orjson.JSONDecodeError:
        body = None

    if response.status_code != expected_status:
        raise GoVecAPIError(response.status_code, _error_message(body, response))

    if not isinstance(body, dict) or "data" not in body:
        raise GoVecAPIError(
            response.status_code,
            f"expected a GoVec JSON response, got: {_snippet(response)}",
        )

    return body["data"]


def _error_message(body: Any, response: httpx.Response) -> str:
    if isinstance(body, dict) and isinstance(error := body.get("error"), str):
        return error

    return _snippet(response)


def _snippet(response: httpx.Response) -> str:
    text = response.text.strip()
    if not text:
        return "(empty body)"

    if len(text) > _SNIPPET_CHARS:
        return text[:_SNIPPET_CHARS] + "..."

    return text


def health_from_json(data: Any) -> HealthResponse:
    return HealthResponse(status=data["status"])


def info_from_json(data: Any) -> InfoResponse:
    return InfoResponse(
        quantization=data["quantization"],
        index_type=data["index_type"],
        distance_metric=data["distance_metric"],
        dimensions=data["dimensions"],
        vector_count=data["vector_count"],
        enable_mmap=data["enable_mmap"],
        version=data["version"],
    )


def stats_from_json(data: Any) -> GetStatsResponse:
    return GetStatsResponse(vector_count=data["vector_count"])


def flush_from_json(data: Any) -> FlushResponse:
    return FlushResponse(status=data["status"])


def reset_from_json(data: Any) -> ResetResponse:
    return ResetResponse(status=data["status"])


def get_by_id_from_json(data: Any) -> GetByIdResponse:
    # A dense-only record omits sparse_vector entirely.
    sparse = data.get("sparse_vector")
    sparse_vector = (
        SparseVector(indices=sparse["indices"], values=sparse["values"])
        if sparse
        else None
    )

    return GetByIdResponse(
        id=data["id"],
        vector=data["vector"],
        sparse_vector=sparse_vector,
        metadata=data.get("metadata"),
    )


def insert_from_json(data: Any) -> InsertResponse:
    return InsertResponse(status=data["status"])


def batch_insert_from_json(data: Any) -> BatchInsertResponse:
    return BatchInsertResponse(
        inserted_count=data["inserted_count"],
        errors=[
            BatchInsertError(id=e["id"], error=e["error"])
            for e in data.get("errors", [])
        ],
    )


def search_from_json(data: Any) -> list[SearchResponse]:
    return [
        SearchResponse(id=item["id"], score=item["score"], meta=item.get("meta"))
        for item in data
    ]


def delete_from_json(data: Any) -> DeleteResponse:
    return DeleteResponse(id=data["id"], status=data["status"])
