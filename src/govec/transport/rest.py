from typing import Any, override

import httpx

from govec.exceptions import GoVecConnectionError, GoVecTimeoutError
from govec.models import (
    BatchInsertResponse,
    DeleteResponse,
    GetByIdResponse,
    InfoResponse,
    InsertRequest,
    InsertResponse,
    ResetResponse,
    SearchRequest,
    SearchResponse,
    GetStatsResponse,
    FlushResponse,
    HealthResponse,
)

from govec.transport import rest_mappers as mappers
from govec.transport.base import BaseTransport
from govec.transport.json_codec import encode_batch, encode_request


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
        return mappers.health_from_json(mappers.unwrap(response))

    @override
    def server_info(self) -> InfoResponse:
        response = self._send("GET", f"{self.base_url}/info")
        return mappers.info_from_json(mappers.unwrap(response))

    @override
    def get_stats(self) -> GetStatsResponse:
        response = self._send("GET", f"{self.base_url}/stats")
        return mappers.stats_from_json(mappers.unwrap(response))

    @override
    def flush(self) -> FlushResponse:
        response = self._send("POST", f"{self.base_url}/admin/flush")
        return mappers.flush_from_json(mappers.unwrap(response))

    @override
    def reset(self) -> ResetResponse:
        response = self._send("POST", f"{self.base_url}/admin/reset")
        return mappers.reset_from_json(mappers.unwrap(response))

    @override
    def get_by_id(self, vector_id: str) -> GetByIdResponse | None:
        response = self._send("GET", f"{self.base_url}/vectors/{vector_id}")

        # Checked before the body is decoded: a 404 is the answer, whatever
        # the body says, so a proxy's non-JSON 404 page must not raise here.
        if response.status_code == 404:
            return None

        return mappers.get_by_id_from_json(mappers.unwrap(response))

    @override
    def insert(self, request: InsertRequest) -> InsertResponse:
        response = self._send(
            "POST", f"{self.base_url}/vectors", content=encode_request(request)
        )
        return mappers.insert_from_json(mappers.unwrap(response, expected_status=201))

    @override
    def insert_batch(self, requests: list[InsertRequest]) -> BatchInsertResponse:
        response = self._send(
            "POST", f"{self.base_url}/vectors/batch", content=encode_batch(requests)
        )
        return mappers.batch_insert_from_json(mappers.unwrap(response))

    @override
    def search(self, request: SearchRequest) -> list[SearchResponse]:
        response = self._send(
            "POST", f"{self.base_url}/vectors/search", content=encode_request(request)
        )
        return mappers.search_from_json(mappers.unwrap(response))

    @override
    def delete(self, vector_id: str) -> DeleteResponse:
        response = self._send("DELETE", f"{self.base_url}/vectors/{vector_id}")
        return mappers.delete_from_json(mappers.unwrap(response))
