"""What the client does around each transport call: the local width checks,
splitting a large insert into batches, and reading the delete answer.

Kept apart from `client.py` so the sync and async clients share it: the two
differ only in whether the transport call is awaited, and these rules must not
drift between them.
"""

from collections.abc import Iterable, Iterator

from govec.models import (
    BatchInsertError,
    BatchInsertResponse,
    DeleteResponse,
    InsertRequest,
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
