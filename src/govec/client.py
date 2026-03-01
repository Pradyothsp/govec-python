from typing import Literal

from govec.models import (
    GoVecResponse,
    InfoResponse,
    InsertRequest,
    SparseVector,
)

Protocol = Literal["rest", "grpc"]


class GoVecClient:
    """
    GoVec Official Client for Python.

    This client provides methods to interact with the GoVec API,
    allowing users to perform various operations such as retrieving data, sending requests, and managing their account.

    The client is designed to be straightforward to use and integrates seamlessly with the GoVec platform.
    """

    def __init__(
        self, host: str, port: int, api_key: str, protocol: Protocol, tls: bool = True
    ):
        self.host = host
        self.port = port
        self.protocol = protocol

        if self.protocol == "rest":
            from govec.transport.rest import RESTTransport

            self._transport = RESTTransport(host, port, api_key, tls=tls)

        elif self.protocol == "grpc":
            raise NotImplementedError("gRPC transport is not implemented yet.")

        # The Pre-Flight Handshake
        try:
            self._server_config = self._transport.server_info()

            if not self._server_config.success:
                raise ConnectionError(
                    self._server_config.error or "Server rejected the connection."
                )

            if self._server_config.data is None:
                raise ConnectionError("Server returned no configuration data.")
            self.dimensions = self._server_config.data.dimensions

        except ConnectionError:
            raise
        except Exception:
            raise ConnectionError("Failed to connect to the GoVec server.")

    def info(self) -> GoVecResponse[InfoResponse | None]:
        """
        Retrieve server information.
        """
        return self._transport.server_info()

    def insert(
        self,
        id: str,
        dense_vector: list[float],
        sparse_vector: SparseVector,
        metadata: dict[str, str] | None = None,
    ) -> bool:
        """
        Inserts a single dense vector into the database.
        """
        if len(dense_vector) != self.dimensions:
            raise ValueError(
                f"Dimension mismatch: The GoVec server is configured for {self.dimensions} "
                f"dimensions, but you provided a vector with {len(dense_vector)} dimensions."
            )

        request = InsertRequest(
            id=id, vector=dense_vector, sparse_vector=sparse_vector, metadata=metadata
        )

        return self._transport.insert(request).success
