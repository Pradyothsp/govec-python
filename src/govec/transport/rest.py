from typing import Any, NamedTuple, override

import httpx

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
from govec.transport.base import AsyncBaseTransport, BaseTransport
from govec.transport.json_codec import encode_batch, encode_request

_TIMEOUT_SECONDS = 10.0


class _Endpoint(NamedTuple):
    root_url: str
    base_url: str
    headers: dict[str, str]


def _endpoint(host: str, port: int, api_key: str | None, tls: bool) -> _Endpoint:
    scheme = "https" if tls else "http"
    root_url = f"{scheme}://{host}:{port}"
    headers = {"Content-Type": "application/json"}

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    return _Endpoint(root_url=root_url, base_url=f"{root_url}/api/v1", headers=headers)


class RESTTransport(BaseTransport):
    def __init__(
        self, host: str, port: int, api_key: str | None = None, tls: bool = True
    ):
        self.root_url, self.base_url, self.headers = _endpoint(host, port, api_key, tls)

        # Using a persistent client session for connection pooling (much faster!)
        self.client = httpx.Client(headers=self.headers, timeout=_TIMEOUT_SECONDS)

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
        """
        self._ensure_open()

        try:
            return self.client.request(method, url, **kwargs)
        except httpx.RequestError as e:
            mappers.raise_request_error(e, self.root_url, _TIMEOUT_SECONDS)

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


class AsyncRESTTransport(AsyncBaseTransport):
    """RESTTransport over httpx.AsyncClient.

    Everything but the send is shared with RESTTransport: the URLs and headers
    (`_endpoint`), the error translation and every response mapper. Keep each
    method's path and expected status in step with the sync class above.
    """

    def __init__(
        self, host: str, port: int, api_key: str | None = None, tls: bool = True
    ):
        self.root_url, self.base_url, self.headers = _endpoint(host, port, api_key, tls)

        # Creating an AsyncClient opens nothing and needs no running loop.
        self.client = httpx.AsyncClient(headers=self.headers, timeout=_TIMEOUT_SECONDS)

    @override
    async def _release(self) -> None:
        await self.client.aclose()

    async def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        self._ensure_open()

        try:
            return await self.client.request(method, url, **kwargs)
        except httpx.RequestError as e:
            mappers.raise_request_error(e, self.root_url, _TIMEOUT_SECONDS)

    @override
    async def health(self) -> HealthResponse:
        response = await self._send("GET", f"{self.root_url}/health")
        return mappers.health_from_json(mappers.unwrap(response))

    @override
    async def server_info(self) -> InfoResponse:
        response = await self._send("GET", f"{self.base_url}/info")
        return mappers.info_from_json(mappers.unwrap(response))

    @override
    async def get_stats(self) -> GetStatsResponse:
        response = await self._send("GET", f"{self.base_url}/stats")
        return mappers.stats_from_json(mappers.unwrap(response))

    @override
    async def flush(self) -> FlushResponse:
        response = await self._send("POST", f"{self.base_url}/admin/flush")
        return mappers.flush_from_json(mappers.unwrap(response))

    @override
    async def reset(self) -> ResetResponse:
        response = await self._send("POST", f"{self.base_url}/admin/reset")
        return mappers.reset_from_json(mappers.unwrap(response))

    @override
    async def get_by_id(self, vector_id: str) -> GetByIdResponse | None:
        response = await self._send("GET", f"{self.base_url}/vectors/{vector_id}")

        if response.status_code == 404:
            return None

        return mappers.get_by_id_from_json(mappers.unwrap(response))

    @override
    async def insert(self, request: InsertRequest) -> InsertResponse:
        response = await self._send(
            "POST", f"{self.base_url}/vectors", content=encode_request(request)
        )
        return mappers.insert_from_json(mappers.unwrap(response, expected_status=201))

    @override
    async def insert_batch(self, requests: list[InsertRequest]) -> BatchInsertResponse:
        response = await self._send(
            "POST", f"{self.base_url}/vectors/batch", content=encode_batch(requests)
        )
        return mappers.batch_insert_from_json(mappers.unwrap(response))

    @override
    async def search(self, request: SearchRequest) -> list[SearchResponse]:
        response = await self._send(
            "POST", f"{self.base_url}/vectors/search", content=encode_request(request)
        )
        return mappers.search_from_json(mappers.unwrap(response))

    @override
    async def delete(self, vector_id: str) -> DeleteResponse:
        response = await self._send("DELETE", f"{self.base_url}/vectors/{vector_id}")
        return mappers.delete_from_json(mappers.unwrap(response))
