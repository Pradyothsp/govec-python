from collections.abc import Callable
from typing import cast

import grpc
import grpc.aio
import pytest

from govec.exceptions import GoVecAPIError, GoVecConnectionError, GoVecTimeoutError
from govec.transport.grpc_mappers import raise_rpc_error, status_of

type BuildError = Callable[[grpc.StatusCode, str], grpc.RpcError]

_TARGET = "testserver:9698"


class _FakeRpcError(grpc.RpcError):
    """A failed sync call, without a server to produce one.

    `grpc.RpcError` carries no status by itself -- the mapping reads the code
    and details off the `grpc.Call` interface, which real sync errors also
    implement. Driving the mapping directly beats provoking each status from a
    live server, which for DEADLINE_EXCEEDED would mean an actually slow
    request.

    Registered as a virtual subclass of `grpc.Call` below rather than
    inheriting from it: the production code only ever calls `code()` and
    `details()`, and inheriting would oblige this to also stub out
    `cancel`, `add_callback`, `is_active` and the rest of the interface --
    six methods of noise that no test reads.
    """

    def __init__(self, code: grpc.StatusCode, details: str = "") -> None:
        self._code = code
        self._details = details

    def code(self) -> grpc.StatusCode:
        return self._code

    def details(self) -> str:
        return self._details


grpc.Call.register(_FakeRpcError)


def _aio_error(code: grpc.StatusCode, details: str) -> grpc.RpcError:
    # The real type grpc.aio raises. It is not a grpc.Call, which is exactly
    # what a fake registered as one would hide.
    return grpc.aio.AioRpcError(code, grpc.aio.Metadata(), grpc.aio.Metadata(), details)


@pytest.fixture(params=[_FakeRpcError, _aio_error], ids=["sync", "aio"])
def build_error(request: pytest.FixtureRequest) -> BuildError:
    return cast(BuildError, request.param)


def test_raise_rpc_error__unavailable__raises_connection_error(
    build_error: BuildError,
) -> None:
    # Arrange
    error = build_error(grpc.StatusCode.UNAVAILABLE, "failed to connect")

    # Act / Assert
    with pytest.raises(GoVecConnectionError):
        raise_rpc_error(error, _TARGET)


def test_raise_rpc_error__deadline_exceeded__raises_timeout_error(
    build_error: BuildError,
) -> None:
    # Arrange
    # Previously reported as GoVecAPIError(4), which claimed the server had
    # answered with an error when it had not answered at all. REST reports a
    # timeout as GoVecTimeoutError and the two transports must agree.
    error = build_error(grpc.StatusCode.DEADLINE_EXCEEDED, "deadline exceeded")

    # Act / Assert
    with pytest.raises(GoVecTimeoutError):
        raise_rpc_error(error, _TARGET)


def test_raise_rpc_error__not_found__raises_api_error_labelled_grpc(
    build_error: BuildError,
) -> None:
    # Arrange
    error = build_error(grpc.StatusCode.NOT_FOUND, "vector not found")

    # Act
    with pytest.raises(GoVecAPIError) as excinfo:
        raise_rpc_error(error, _TARGET)

    # Assert -- labelled so a gRPC NOT_FOUND does not render as "HTTP 5"
    assert excinfo.value.status_label == "gRPC"
    assert str(excinfo.value).startswith("gRPC 5")


def test_raise_rpc_error__invalid_argument__raises_api_error(
    build_error: BuildError,
) -> None:
    # Arrange
    error = build_error(grpc.StatusCode.INVALID_ARGUMENT, "dimension mismatch")

    # Act
    with pytest.raises(GoVecAPIError) as excinfo:
        raise_rpc_error(error, _TARGET)

    # Assert
    assert excinfo.value.status_code == grpc.StatusCode.INVALID_ARGUMENT.value[0]
    assert "dimension mismatch" in excinfo.value.message


def test_status_of__failed_call__returns_its_code(build_error: BuildError) -> None:
    # Arrange
    # get_by_id reads this to turn NOT_FOUND into None on both transports.
    error = build_error(grpc.StatusCode.NOT_FOUND, "vector not found")

    # Act
    code = status_of(error)

    # Assert
    assert code == grpc.StatusCode.NOT_FOUND


def test_status_of__error_without_a_status__returns_none() -> None:
    # Arrange
    error = grpc.RpcError()

    # Act
    code = status_of(error)

    # Assert
    assert code is None
