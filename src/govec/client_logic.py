"""What the client does around each transport call: the local width and
NaN/infinity checks, splitting a large insert into batches, and reading the
delete answer.

Kept apart from `client.py` so the sync and async clients share it: the two
differ only in whether the transport call is awaited, and these rules must not
drift between them.
"""

import math
from collections.abc import Iterable, Iterator
from typing import Any

from govec.models import (
    BatchInsertError,
    BatchInsertResponse,
    DeleteResponse,
    InsertRequest,
    SearchRequest,
)


def check_width(dense_vector: list[float], dimensions: int, enable_mmap: bool) -> None:
    """Raise ValueError if the vector's width differs from the server's.

    Only checked with mmap on, where the server's width is fixed. The server
    enforces width either way; this just fails before a round trip.
    """
    if enable_mmap and len(dense_vector) != dimensions:
        raise ValueError(
            f"Dimension mismatch: The GoVec server is configured for {dimensions} "
            f"dimensions, but you provided a vector with {len(dense_vector)} dimensions."
        )


def check_batch_widths(
    requests: list[InsertRequest], dimensions: int, enable_mmap: bool
) -> None:
    if not enable_mmap:
        return

    if bad := next((r for r in requests if len(r.vector) != dimensions), None):
        raise ValueError(f"Vector {bad.id} has wrong dimensions.")


def check_finite(request: InsertRequest | SearchRequest) -> None:
    """Raise ValueError if a request carries NaN or an infinity.

    The server accepts both and neither transport can be trusted to stop
    them. REST: JSON has no NaN, and orjson writes it as null, which the
    server reads into a float32 as 0, so the vector is stored or searched as
    zeros. gRPC: the NaN arrives intact, and the server stores it; a cosine
    distance against it then reads as a zero vector's, and a euclidean one
    breaks ranking. Checked here, before the transport is chosen, so both
    reject it the same way.

    Vectors are checked with `map(math.isfinite)`, which stays in C; the
    recursive walk is only for metadata and filters, which are small.
    """
    if request.vector is not None and not all(map(math.isfinite, request.vector)):
        raise ValueError("vector contains NaN or infinity")

    sparse = request.sparse_vector
    if sparse is not None and not all(map(math.isfinite, sparse.values)):
        raise ValueError("sparse_vector contains NaN or infinity")

    extra = request.metadata if isinstance(request, InsertRequest) else request.filter
    if _contains_non_finite(extra):
        raise ValueError("metadata or filter contains NaN or infinity")


def check_all_finite(requests: list[InsertRequest]) -> None:
    for request in requests:
        check_finite(request)


def _contains_non_finite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)

    if isinstance(value, dict):
        return any(_contains_non_finite(v) for v in value.values())

    if isinstance(value, (list, tuple)):
        return any(_contains_non_finite(v) for v in value)

    return False


def batches(
    requests: list[InsertRequest], batch_size: int
) -> Iterator[list[InsertRequest]]:
    # Without this, a negative size made range() empty, so insert_many sent
    # nothing and reported 0 inserted with no error; 0 failed inside range().
    if batch_size < 1:
        raise ValueError(f"batch_size must be at least 1, got {batch_size}")

    for i in range(0, len(requests), batch_size):
        yield requests[i : i + batch_size]


def merge_batches(results: Iterable[BatchInsertResponse]) -> BatchInsertResponse:
    total_inserted = 0
    all_errors: list[BatchInsertError] = []

    for result in results:
        total_inserted += result.inserted_count
        all_errors.extend(result.errors)

    return BatchInsertResponse(inserted_count=total_inserted, errors=all_errors)


def was_deleted(response: DeleteResponse, vector_id: str) -> bool:
    # Was `in ("deleted", "ok")`: the server used to answer "deleted" over
    # REST and "ok" over gRPC, and accepting both was how the SDK hid that.
    # Both say "deleted" now, so the second value is unreachable.
    return response.id == vector_id and response.status == "deleted"
