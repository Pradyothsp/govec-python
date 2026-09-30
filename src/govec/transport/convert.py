"""Conversion between Python values and `google.protobuf.Value`.

Kept separate from `grpc.py` because these are pure functions with no
dependency on the transport or its stub -- the same split govec's own server
makes with `internal/grpcserver/convert`.
"""

from typing import Any

from google.protobuf import struct_pb2


def to_proto_value(val: Any) -> struct_pb2.Value:
    """Converts a Python primitive to a google.protobuf.Value."""
    if val is None:
        return struct_pb2.Value(null_value=struct_pb2.NULL_VALUE)
    if isinstance(val, bool):
        return struct_pb2.Value(bool_value=val)
    if isinstance(val, (int, float)):
        return struct_pb2.Value(number_value=float(val))
    if isinstance(val, str):
        return struct_pb2.Value(string_value=val)
    if isinstance(val, (list, tuple)):
        return struct_pb2.Value(
            list_value=struct_pb2.ListValue(values=[to_proto_value(v) for v in val])
        )
    if isinstance(val, dict):
        return struct_pb2.Value(
            struct_value=struct_pb2.Struct(
                fields={k: to_proto_value(v) for k, v in val.items()}
            )
        )
    raise ValueError(f"Unsupported metadata value type: {type(val)}")


def from_proto_value(val: struct_pb2.Value) -> Any:
    """Converts a google.protobuf.Value to a native Python object."""
    kind = val.WhichOneof("kind")
    if kind == "null_value":
        return None
    if kind in ("bool_value", "number_value", "string_value"):
        return getattr(val, kind)
    if kind == "list_value":
        return [from_proto_value(v) for v in val.list_value.values]
    if kind == "struct_value":
        return {k: from_proto_value(v) for k, v in val.struct_value.fields.items()}
    return None
