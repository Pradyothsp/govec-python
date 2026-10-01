from dataclasses import asdict
from typing import override

import httpx

from govec.exceptions import GoVecAPIError
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
    def health(self) -> HealthResponse:
        # /health sits at the root, not under /api/v1 like everything else.
        response = self.client.get(f"{self.root_url}/health")
        response_json = response.json()

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        return HealthResponse(status=response_json["data"]["status"])

    @override
    def server_info(self) -> InfoResponse:
        response = self.client.get(f"{self.base_url}/info")
        response_json = response.json()

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        return InfoResponse(**response_json["data"])

    @override
    def get_stats(self) -> GetStatsResponse:
        response = self.client.get(f"{self.base_url}/stats")
        response_json = response.json()

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        return GetStatsResponse(vector_count=response_json["data"]["vector_count"])

    @override
    def flush(self) -> FlushResponse:
        response = self.client.post(f"{self.base_url}/admin/flush")
        response_json = response.json()

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        return FlushResponse(status=response_json["data"]["status"])

    @override
    def reset(self) -> ResetResponse:
        response = self.client.post(f"{self.base_url}/admin/reset")
        response_json = response.json()

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        return ResetResponse(status=response_json["data"]["status"])

    @override
    def get_by_id(self, vector_id: str) -> GetByIdResponse | None:
        response = self.client.get(f"{self.base_url}/vectors/{vector_id}")
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
        response = self.client.post(f"{self.base_url}/vectors", json=asdict(request))
        response_json = response.json()

        if response.status_code != 201:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        return InsertResponse(**response_json["data"])

    @override
    def insert_batch(self, requests: list[InsertRequest]) -> BatchInsertResponse:
        response = self.client.post(
            f"{self.base_url}/vectors/batch",
            json={"vectors": [asdict(r) for r in requests]},
        )
        response_json = response.json()

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        data = response_json["data"]
        return BatchInsertResponse(
            inserted_count=data["inserted_count"],
            errors=[BatchInsertError(**e) for e in data.get("errors", [])],
        )

    @override
    def search(self, request: SearchRequest) -> list[SearchResponse]:
        response = self.client.post(
            f"{self.base_url}/vectors/search", json=asdict(request)
        )
        response_json = response.json()

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        return [SearchResponse(**item) for item in response_json["data"]]

    @override
    def delete(self, vector_id: str) -> DeleteResponse:
        response = self.client.delete(f"{self.base_url}/vectors/{vector_id}")
        response_json = response.json()

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        return DeleteResponse(**response_json["data"])
