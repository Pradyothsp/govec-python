import pytest
from google.protobuf import struct_pb2

from govec.transport.convert import from_proto_value, to_proto_value


def test_to_proto_value__none_value__returns_null_value() -> None:
    # Arrange
    val = None

    # Act
    proto_val = to_proto_value(val)

    # Assert
    assert proto_val.WhichOneof("kind") == "null_value"
    assert proto_val.null_value == struct_pb2.NULL_VALUE


def test_to_proto_value__bool_true__returns_bool_value() -> None:
    # Arrange
    val = True

    # Act
    proto_val = to_proto_value(val)

    # Assert
    assert proto_val.WhichOneof("kind") == "bool_value"
    assert proto_val.bool_value is True


def test_to_proto_value__bool_false__returns_bool_value() -> None:
    # Arrange
    val = False

    # Act
    proto_val = to_proto_value(val)

    # Assert
    assert proto_val.WhichOneof("kind") == "bool_value"
    assert proto_val.bool_value is False


def test_to_proto_value__int_and_float__returns_number_value() -> None:
    # Arrange
    int_val = 42
    float_val = 3.14

    # Act
    int_proto = to_proto_value(int_val)
    float_proto = to_proto_value(float_val)

    # Assert
    assert int_proto.WhichOneof("kind") == "number_value"
    assert int_proto.number_value == 42.0
    assert float_proto.WhichOneof("kind") == "number_value"
    assert float_proto.number_value == 3.14


def test_to_proto_value__string__returns_string_value() -> None:
    # Arrange
    val = "govec-vector"

    # Act
    proto_val = to_proto_value(val)

    # Assert
    assert proto_val.WhichOneof("kind") == "string_value"
    assert proto_val.string_value == "govec-vector"


def test_to_proto_value__nested_list_and_dict__returns_structured_value() -> None:
    # Arrange
    data = {
        "title": "Document A",
        "count": 10,
        "active": True,
        "tags": ["ml", "vector", 42],
        "nested": {"score": 0.99, "published": False},
    }

    # Act
    proto_val = to_proto_value(data)
    recovered = from_proto_value(proto_val)

    # Assert
    assert proto_val.WhichOneof("kind") == "struct_value"
    assert recovered == {
        "title": "Document A",
        "count": 10.0,
        "active": True,
        "tags": ["ml", "vector", 42.0],
        "nested": {"score": 0.99, "published": False},
    }


def test_to_proto_value__unsupported_type__raises_value_error() -> None:
    # Arrange
    class Unsupported:
        pass

    # Act / Assert
    with pytest.raises(ValueError, match="Unsupported metadata value type"):
        to_proto_value(Unsupported())
