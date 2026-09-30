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
