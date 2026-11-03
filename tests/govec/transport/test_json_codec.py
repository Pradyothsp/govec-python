import json

import pytest

from govec.models import InsertRequest, SearchRequest, SparseVector
from govec.transport.json_codec import decode, encode_batch, encode_request

# The standard library parses what the codec wrote, so these check the bytes
# against an independent JSON reader rather than against orjson itself.


def test_encode_request__search__writes_every_field_the_server_reads() -> None:
    # Arrange
    request = SearchRequest(vector=[0.1, -2.5], k=3, filter={"tag": "a"})

    # Act
    body = encode_request(request)

    # Assert
    assert json.loads(body) == {
        "k": 3,
        "filter": {"tag": "a"},
        "sparse_vector": None,
        "vector": [0.1, -2.5],
    }


def test_encode_request__vector_floats__survive_bit_for_bit() -> None:
    # Arrange
    vector = [0.1, 1 / 3, 2.0**-30, -123456.789, 5e-324]

    # Act
    body = encode_request(SearchRequest(vector=vector, k=1))

    # Assert
    assert json.loads(body)["vector"] == vector


def test_encode_batch__records__wraps_them_with_sparse_and_metadata() -> None:
    # Arrange
    record = InsertRequest(
        id="a",
        vector=[1.0],
        sparse_vector=SparseVector(indices=[7], values=[0.5]),
        metadata={"year": 2024, "tags": ("x", "y")},
    )

    # Act
    body = encode_batch([record])

    # Assert
    assert json.loads(body) == {
        "vectors": [
            {
                "id": "a",
                "vector": [1.0],
                "sparse_vector": {"indices": [7], "values": [0.5]},
                "metadata": {"year": 2024, "tags": ["x", "y"]},
            }
        ]
    }


# --- NaN and infinity ------------------------------------------------------------
#
# orjson writes them as null, which the server decodes into a float of 0 without
# complaint. httpx's standard-library encoder refused them; the codec still does.


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_encode_request__vector_has_nan_or_infinity__raises_value_error(
    bad: float,
) -> None:
    # Arrange
    request = SearchRequest(vector=[1.0, bad], k=1)

    # Act / Assert
    with pytest.raises(ValueError, match="vector contains NaN or infinity"):
        encode_request(request)


def test_encode_request__sparse_values_have_nan__raises_value_error() -> None:
    # Arrange
    sparse = SparseVector(indices=[1], values=[float("nan")])
    request = InsertRequest(id="a", vector=[1.0], sparse_vector=sparse)

    # Act / Assert
    with pytest.raises(ValueError, match="sparse_vector contains NaN"):
        encode_request(request)


def test_encode_request__filter_has_infinity__raises_value_error() -> None:
    # Arrange
    request = SearchRequest(vector=[1.0], k=1, filter={"score": float("inf")})

    # Act / Assert
    with pytest.raises(ValueError, match="metadata or filter contains NaN"):
        encode_request(request)


def test_encode_batch__nested_metadata_has_nan__raises_value_error() -> None:
    # Arrange
    good = InsertRequest(id="a", vector=[1.0])
    bad = InsertRequest(id="b", vector=[1.0], metadata={"s": [1.0, float("nan")]})

    # Act / Assert
    with pytest.raises(ValueError, match="metadata or filter contains NaN"):
        encode_batch([good, bad])


def test_encode_request__metadata_has_none__is_not_mistaken_for_nan() -> None:
    # Arrange
    request = InsertRequest(id="a", vector=[1.0], metadata={"note": None})

    # Act
    body = encode_request(request)

    # Assert
    assert json.loads(body)["metadata"] == {"note": None}


def test_decode__response_body__parses_it() -> None:
    # Arrange
    content = b'{"success":true,"data":{"vector_count":3}}'

    # Act
    parsed = decode(content)

    # Assert
    assert parsed == {"success": True, "data": {"vector_count": 3}}
