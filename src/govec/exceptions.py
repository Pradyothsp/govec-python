class GoVecError(Exception):
    """Base exception for all GoVec errors."""


class GoVecAPIError(GoVecError):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP {status_code}: {message}")


class GoVecConnectionError(GoVecError):
    """Raised when the client cannot reach the GoVec server."""
