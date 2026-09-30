from typing import Any, Literal, assert_never

import httpx

from govec.exceptions import GoVecConnectionError
from govec.models import (
    BatchInsertError,
    BatchInsertResponse,
    GetByIdResponse,
    InfoResponse,
    InsertRequest,
    ResetResponse,
    SearchRequest,
    SearchResponse,
    SparseVector,
    GetStatsResponse,
    FlushResponse,
    HealthResponse,
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
            from govec.transport.grpc import GRPCTransport

            self._transport = GRPCTransport(host, port, api_key, tls=tls)

        else:
            assert_never(self.protocol)

        # The Pre-Flight Handshake
        try:
            server_config = self._transport.server_info()
            self.dimensions = server_config.dimensions
            self.enable_mmap = server_config.enable_mmap

        except httpx.HTTPError as e:
            raise GoVecConnectionError("Failed to connect to the GoVec server.") from e

    def health(self) -> HealthResponse:
        """
        Check that the server is reachable and serving.
        """
        return self._transport.health()

    def info(self) -> InfoResponse:
        """
        Retrieve server information.
        """
        return self._transport.server_info()

    def get_stats(self) -> GetStatsResponse:
        """
        Retrieve collection statistics, such as the total number of vectors stored.
        """
        return self._transport.get_stats()

    def flush(self) -> FlushResponse:
        """
        Forces the database to flush in-memory structures (like the HNSW graph) to disk.
        """
        return self._transport.flush()

    def reset(self) -> ResetResponse:
        """
        Clears all vectors, ID mappings, and the WAL. Does not persist the cleared
        state to disk -- call flush() afterward if the reset should survive a restart.
        """
        return self._transport.reset()

    def get_by_id(self, vector_id: str) -> GetByIdResponse | None:
        """
        Retrieve a vector by its ID.
        """
        return self._transport.get_by_id(vector_id)

    def insert(
        self,
        vector_id: str,
        dense_vector: list[float],
        sparse_vector: SparseVector | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Inserts a single dense vector into the database.
        """
        if self.enable_mmap and len(dense_vector) != self.dimensions:
            raise ValueError(
                f"Dimension mismatch: The GoVec server is configured for {self.dimensions} "
                f"dimensions, but you provided a vector with {len(dense_vector)} dimensions."
            )

        request = InsertRequest(
            id=vector_id,
            vector=dense_vector,
            sparse_vector=sparse_vector,
            metadata=metadata,
        )

        self._transport.insert(request)
        return True

    def insert_many(
        self, requests: list[InsertRequest], batch_size: int = 500
    ) -> BatchInsertResponse:
        """
        Chunks a large list of vectors and inserts them in optimized batches.
        Returns a BatchInsertResponse with the total inserted count and any per-vector errors.
        """

        if self.enable_mmap:
            if bad := next(
                (r for r in requests if len(r.vector) != self.dimensions), None
            ):
                raise ValueError(f"Vector {bad.id} has wrong dimensions.")

        total_inserted = 0
        all_errors: list[BatchInsertError] = []

        for i in range(0, len(requests), batch_size):
            batch = requests[i : i + batch_size]
            result = self._transport.insert_batch(batch)
            total_inserted += result.inserted_count
            all_errors.extend(result.errors)

        return BatchInsertResponse(inserted_count=total_inserted, errors=all_errors)

    def search(
        self,
        dense_vector: list[float] | None = None,
        sparse_vector: SparseVector | None = None,
        k: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> list[SearchResponse]:
        """
        Search for the nearest vectors.
        """
        request = SearchRequest(
            vector=dense_vector,
            sparse_vector=sparse_vector,
            k=k,
            filter=filter,
        )

        return self._transport.search(request)

    def delete(self, vector_id: str) -> bool:
        """
        Deletes a vector by its ID.
        """
        response = self._transport.delete(vector_id)

        if response.id == vector_id and response.status in ("deleted", "ok"):
            return True
        else:
            return False
