class GoVecError(Exception):
    """Base exception for all GoVec errors."""


class GoVecAPIError(GoVecError):
    """Raised when the GoVec server returns an error response.

    `status_code` is whatever the transport reports: an HTTP status over REST,
    a gRPC status code over gRPC. `status_label` names which, so a gRPC
    NOT_FOUND does not render as "HTTP 5".
    """

    def __init__(self, status_code: int, message: str, status_label: str = "HTTP"):
        self.status_code = status_code
        self.message = message
        self.status_label = status_label
        super().__init__(f"{status_label} {status_code}: {message}")


class GoVecConnectionError(GoVecError):
    """Raised when the client cannot reach the GoVec server."""


class GoVecTimeoutError(GoVecError):
    """Raised when the server did not answer within the client's timeout.

    Kept apart from `GoVecConnectionError` because the two call for different
    responses: an unreachable server will not improve on retry of the same
    request, while a timeout often means the one query was too expensive and a
    smaller `k` or a narrower filter would succeed. Both transports raise this
    -- REST from `httpx.TimeoutException`, gRPC from `DEADLINE_EXCEEDED`.
    """


class GoVecClientClosedError(GoVecError):
    """Raised when a closed client or transport is used again.

    This is a programming error, not a server condition, so it is reported the
    same way on both transports rather than as whatever httpx or grpc would
    have said from deep inside their own machinery.
    """
