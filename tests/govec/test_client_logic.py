import pytest

from govec.client_logic import (
    batches,
    check_all_finite,
    check_batch_widths,
    check_finite,
    check_width,
    merge_batches,
    was_deleted,
)
from govec.models import (
    BatchInsertError,
    BatchInsertResponse,
    DeleteResponse,
    InsertRequest,
    SearchRequest,
    SparseVector,
)


def _request(vector_id: str, width: int = 3) -> InsertRequest:
    return InsertRequest(id=vector_id, vector=[0.1] * width)


# --- width checks -------------------------------------------------------------


def test_check_width__mmap_on_and_width_differs__raises_value_error() -> None:
    # Arrange
    vector = [0.1, 0.2]

    # Act / Assert
    with pytest.raises(ValueError, match="configured for 3 dimensions"):
        check_width(vector, dimensions=3, enable_mmap=True)


def test_check_width__mmap_off_and_width_differs__leaves_it_to_the_server() -> None:
    # Arrange
    vector = [0.1, 0.2]

    # Act / Assert -- no raise: without mmap the server's width is not fixed
    check_width(vector, dimensions=3, enable_mmap=False)


def test_check_batch_widths__one_vector_differs__names_that_vector() -> None:
    # Arrange
    requests = [_request("good"), _request("bad", width=2)]

    # Act / Assert
    with pytest.raises(ValueError, match="Vector bad"):
        check_batch_widths(requests, dimensions=3, enable_mmap=True)


def test_check_batch_widths__mmap_off__leaves_it_to_the_server() -> None:
    # Arrange
    requests = [_request("bad", width=2)]

    # Act / Assert -- no raise
    check_batch_widths(requests, dimensions=3, enable_mmap=False)


# --- NaN and infinity ----------------------------------------------------------
#
# The server accepts both. Over REST orjson writes them as null, which the server
# reads as 0; over gRPC they arrive intact and are stored as NaN.


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_check_finite__vector_has_nan_or_infinity__raises_value_error(
    bad: float,
) -> None:
    # Arrange
    request = SearchRequest(vector=[1.0, bad], k=1)

    # Act / Assert
    with pytest.raises(ValueError, match="vector contains NaN or infinity"):
        check_finite(request)


def test_check_finite__sparse_values_have_nan__raises_value_error() -> None:
    # Arrange
    sparse = SparseVector(indices=[1], values=[float("nan")])
    request = InsertRequest(id="a", vector=[1.0], sparse_vector=sparse)

    # Act / Assert
    with pytest.raises(ValueError, match="sparse_vector contains NaN"):
        check_finite(request)


def test_check_finite__filter_has_infinity__raises_value_error() -> None:
    # Arrange
    request = SearchRequest(vector=[1.0], k=1, filter={"score": float("inf")})

    # Act / Assert
    with pytest.raises(ValueError, match="metadata or filter contains NaN"):
        check_finite(request)


def test_check_finite__metadata_has_none__is_not_mistaken_for_nan() -> None:
    # Arrange
    request = InsertRequest(id="a", vector=[1.0], metadata={"note": None})

    # Act / Assert -- no raise
    check_finite(request)


def test_check_all_finite__nested_metadata_has_nan__raises_value_error() -> None:
    # Arrange
    good = InsertRequest(id="a", vector=[1.0])
    bad = InsertRequest(id="b", vector=[1.0], metadata={"s": [1.0, float("nan")]})

    # Act / Assert
    with pytest.raises(ValueError, match="metadata or filter contains NaN"):
        check_all_finite([good, bad])


# --- batching -----------------------------------------------------------------


def test_batches__count_not_a_multiple_of_size__last_batch_holds_the_rest() -> None:
    # Arrange
    requests = [_request(f"v{i}") for i in range(5)]

    # Act
    result = list(batches(requests, batch_size=2))

    # Assert
    assert [[r.id for r in batch] for batch in result] == [
        ["v0", "v1"],
        ["v2", "v3"],
        ["v4"],
    ]


def test_batches__no_requests__yields_no_batches() -> None:
    # Arrange / Act
    result = list(batches([], batch_size=2))

    # Assert
    assert result == []


@pytest.mark.parametrize("batch_size", [0, -1])
def test_batches__size_below_one__raises_value_error(batch_size: int) -> None:
    # Arrange
    requests = [_request("v0")]

    # Act / Assert
    with pytest.raises(ValueError, match="batch_size must be at least 1"):
        list(batches(requests, batch_size))


def test_merge_batches__several_results__sums_counts_and_keeps_errors_in_order() -> (
    None
):
    # Arrange
    results = [
        BatchInsertResponse(
            inserted_count=2, errors=[BatchInsertError(id="a", error="x")]
        ),
        BatchInsertResponse(inserted_count=0, errors=[]),
        BatchInsertResponse(
            inserted_count=1, errors=[BatchInsertError(id="b", error="y")]
        ),
    ]

    # Act
    merged = merge_batches(results)

    # Assert
    assert merged.inserted_count == 3
    assert [e.id for e in merged.errors] == ["a", "b"]


def test_merge_batches__no_results__reports_nothing_inserted() -> None:
    # Arrange / Act
    merged = merge_batches([])

    # Assert
    assert merged == BatchInsertResponse(inserted_count=0, errors=[])


# --- delete -------------------------------------------------------------------


def test_was_deleted__server_confirms_this_id__returns_true() -> None:
    # Arrange
    response = DeleteResponse(id="doc-1", status="deleted")

    # Act / Assert
    assert was_deleted(response, "doc-1")


def test_was_deleted__server_names_another_id__returns_false() -> None:
    # Arrange
    response = DeleteResponse(id="doc-2", status="deleted")

    # Act / Assert
    assert not was_deleted(response, "doc-1")


def test_was_deleted__status_is_not_deleted__returns_false() -> None:
    # Arrange
    # "ok" was what gRPC used to answer; it is no longer accepted.
    response = DeleteResponse(id="doc-1", status="ok")

    # Act / Assert
    assert not was_deleted(response, "doc-1")
