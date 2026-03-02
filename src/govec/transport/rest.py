from dataclasses import asdict

import httpx

from govec.exceptions import GoVecAPIError
from govec.models import (
    BatchInsertError,
    BatchInsertResponse,
    DeleteResponse,
    InfoResponse,
    InsertRequest,
    InsertResponse,
    SearchRequest,
    SearchResponse,
)

from govec.transport.base import BaseTransport


class RESTTransport(BaseTransport):
    def __init__(
        self, host: str, port: int, api_key: str | None = None, tls: bool = True
    ):
        scheme = "https" if tls else "http"
        self.base_url = f"{scheme}://{host}:{port}/api/v1"
        self.headers = {"Content-Type": "application/json"}

        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

        # Using a persistent client session for connection pooling (much faster!)
        self.client = httpx.Client(headers=self.headers, timeout=10.0)

    def server_info(self) -> InfoResponse:
        response = self.client.get(f"{self.base_url}/info")
        response_json = response.json()

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        return InfoResponse(**response_json["data"])

    def insert(self, request: InsertRequest) -> InsertResponse:
        response = self.client.post(f"{self.base_url}/vectors", json=asdict(request))
        response_json = response.json()

        if response.status_code != 201:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        return InsertResponse(**response_json["data"])

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

    def search(self, request: SearchRequest) -> list[SearchResponse]:
        response = self.client.post(
            f"{self.base_url}/vectors/search", json=asdict(request)
        )
        response_json = response.json()

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        return [SearchResponse(**item) for item in response_json["data"]]

    def delete(self, id: str) -> DeleteResponse:
        response = self.client.delete(f"{self.base_url}/vectors/{id}")
        response_json = response.json()

        if response.status_code != 200:
            raise GoVecAPIError(response.status_code, response_json.get("error", ""))

        return DeleteResponse(**response_json["data"])
