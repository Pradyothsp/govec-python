from dataclasses import asdict
from typing import Any, override

import httpx

from govec.exceptions import GoVecAPIError, GoVecConnectionError, GoVecTimeoutError
from govec.models import (
    BatchInsertError,
    BatchInsertResponse,
    DeleteResponse,
    GetByIdResponse,
    InfoResponse,
    InsertRequest,
    InsertResponse,
    ResetResponse,
    SearchRequest,
    SearchResponse,
    SparseVector,
    GetStatsResponse,
    FlushResponse,
    HealthResponse,
)

from govec.transport.base import BaseTransport


class RESTTransport(BaseTransport):
    def __init__(
        self, host: str, port: int, api_key: str | None = None, tls: bool = True
    ):
        scheme = "https" if tls else "http"
        self.root_url = f"{scheme}://{host}:{port}"
        self.base_url = f"{self.root_url}/api/v1"
        self.headers = {"Content-Type": "application/json"}

        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

        # Using a persistent client session for connection pooling (much faster!)
        self.client = httpx.Client(headers=self.headers, timeout=10.0)

    @override
    def _release(self) -> None:
        self.client.close()

    def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Issue a request, translating httpx failures into govec exceptions.

        Every request goes through here so that callers never see an httpx
        type. Without it the SDK wrapped a connection failure only during the
        client's preflight handshake, and let `httpx.ConnectError` escape from
        every call made afterwards -- so the same failure had two different
        exception types depending on when it happened, and REST disagreed with
        gRPC, which has always mapped UNAVAILABLE itself.

        Only failures to *complete* a request are translated. A response that
        arrives carrying an error status is the server answering, and each
        caller turns that into GoVecAPIError with the detail it has.
        """
        self._ensure_open()

        try:
            return self.client.request(method, url, **kwargs)
        except httpx.TimeoutException as e:
            # Checked first: TimeoutException is a subclass of RequestError.
            raise GoVecTimeoutError(
                f"GoVec server at {self.root_url} did not respond within "
                f"{self.client.timeout.read}s: {e}"
            ) from e
        except httpx.RequestError as e:
            raise GoVecConnectionError(
                f"Failed to reach the GoVec server at {self.root_url}: {e}"
            ) from e

    @override
    def health(self) -> HealthResponse:
        # /health sits at the root, not under /api/v1 like everything else.
        response = self._send("GET", f"{self.root_url}/health")
        response_json = response.json()

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        return HealthResponse(status=response_json["data"]["status"])

    @override
    def server_info(self) -> InfoResponse:
        response = self._send("GET", f"{self.base_url}/info")
        response_json = response.json()

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        # Responses are built field by field, never by splatting the JSON: a field
        # the server adds in a later release must not break a client built before it.
        data = response_json["data"]
        return InfoResponse(
            quantization=data["quantization"],
            index_type=data["index_type"],
            distance_metric=data["distance_metric"],
            dimensions=data["dimensions"],
            vector_count=data["vector_count"],
            enable_mmap=data["enable_mmap"],
            version=data["version"],
        )

    @override
    def get_stats(self) -> GetStatsResponse:
        response = self._send("GET", f"{self.base_url}/stats")
        response_json = response.json()

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        return GetStatsResponse(vector_count=response_json["data"]["vector_count"])

    @override
    def flush(self) -> FlushResponse:
        response = self._send("POST", f"{self.base_url}/admin/flush")
        response_json = response.json()

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        return FlushResponse(status=response_json["data"]["status"])

    @override
    def reset(self) -> ResetResponse:
        response = self._send("POST", f"{self.base_url}/admin/reset")
        response_json = response.json()

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        return ResetResponse(status=response_json["data"]["status"])

    @override
    def get_by_id(self, vector_id: str) -> GetByIdResponse | None:
        response = self._send("GET", f"{self.base_url}/vectors/{vector_id}")
        response_json = response.json()

        if response.status_code == 404:
            return None

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        data = response_json["data"]

        # A dense-only record omits sparse_vector entirely.
        sparse = data.get("sparse_vector")
        sparse_vector = (
            SparseVector(indices=sparse["indices"], values=sparse["values"])
            if sparse
            else None
        )

        return GetByIdResponse(
            id=data["id"],
            vector=data["vector"],
            sparse_vector=sparse_vector,
            metadata=data.get("metadata"),
        )

    @override
    def insert(self, request: InsertRequest) -> InsertResponse:
        response = self._send("POST", f"{self.base_url}/vectors", json=asdict(request))
        response_json = response.json()

        if response.status_code != 201:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        return InsertResponse(status=response_json["data"]["status"])

    @override
    def insert_batch(self, requests: list[InsertRequest]) -> BatchInsertResponse:
        response = self._send(
            "POST",
            f"{self.base_url}/vectors/batch",
            json={"vectors": [asdict(r) for r in requests]},
        )
        response_json = response.json()

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        data = response_json["data"]
        return BatchInsertResponse(
            inserted_count=data["inserted_count"],
            errors=[
                BatchInsertError(id=e["id"], error=e["error"])
                for e in data.get("errors", [])
            ],
        )

    @override
    def search(self, request: SearchRequest) -> list[SearchResponse]:
        response = self._send(
            "POST", f"{self.base_url}/vectors/search", json=asdict(request)
        )
        response_json = response.json()

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        return [
            SearchResponse(id=item["id"], score=item["score"], meta=item.get("meta"))
            for item in response_json["data"]
        ]

    @override
    def delete(self, vector_id: str) -> DeleteResponse:
        response = self._send("DELETE", f"{self.base_url}/vectors/{vector_id}")
        response_json = response.json()

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        data = response_json["data"]
        return DeleteResponse(id=data["id"], status=data["status"])
