import grpc
import pytest

from govec.exceptions import GoVecAPIError, GoVecConnectionError, GoVecTimeoutError
from govec.transport.grpc import GRPCTransport


class _FakeRpcError(grpc.RpcError):
    """A gRPC failure, without a server to produce one.

    `grpc.RpcError` carries no status by itself -- `_handle_rpc_error` reads
    the code and details off the `grpc.Call` interface, which real errors also
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


@pytest.fixture
def transport() -> GRPCTransport:
    # Creating a channel does not connect, so this needs no server.
    return GRPCTransport("testserver", 9698, tls=False)


def test_handle_rpc_error__unavailable__raises_connection_error(
    transport: GRPCTransport,
) -> None:
    # Arrange
    error = _FakeRpcError(grpc.StatusCode.UNAVAILABLE, "failed to connect")

    # Act / Assert
    with pytest.raises(GoVecConnectionError):
        transport._handle_rpc_error(error)


def test_handle_rpc_error__deadline_exceeded__raises_timeout_error(
    transport: GRPCTransport,
) -> None:
    # Previously reported as GoVecAPIError(4), which claimed the server had
    # answered with an error when it had not answered at all. REST reports a
    # timeout as GoVecTimeoutError and the two transports must agree.
    error = _FakeRpcError(grpc.StatusCode.DEADLINE_EXCEEDED, "deadline exceeded")

    # Act / Assert
    with pytest.raises(GoVecTimeoutError):
        transport._handle_rpc_error(error)


def test_handle_rpc_error__not_found__raises_api_error_labelled_grpc(
    transport: GRPCTransport,
) -> None:
    # Arrange
    error = _FakeRpcError(grpc.StatusCode.NOT_FOUND, "vector not found")

    # Act
    with pytest.raises(GoVecAPIError) as excinfo:
        transport._handle_rpc_error(error)

    # Assert -- labelled so a gRPC NOT_FOUND does not render as "HTTP 5"
    assert excinfo.value.status_label == "gRPC"
    assert str(excinfo.value).startswith("gRPC 5")


def test_handle_rpc_error__invalid_argument__raises_api_error(
    transport: GRPCTransport,
) -> None:
    # Arrange
    error = _FakeRpcError(grpc.StatusCode.INVALID_ARGUMENT, "dimension mismatch")

    # Act
    with pytest.raises(GoVecAPIError) as excinfo:
        transport._handle_rpc_error(error)

    # Assert
    assert excinfo.value.status_code == grpc.StatusCode.INVALID_ARGUMENT.value[0]
    assert "dimension mismatch" in excinfo.value.message
