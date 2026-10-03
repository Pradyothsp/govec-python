from typing import override

import pytest

from govec.client import GoVecClient
from govec.exceptions import GoVecConnectionError
from govec.models import (
    BatchInsertResponse,
    DeleteResponse,
    FlushResponse,
    GetByIdResponse,
    GetStatsResponse,
    HealthResponse,
    InfoResponse,
    InsertRequest,
    InsertResponse,
    ResetResponse,
    SearchRequest,
    SearchResponse,
)
from govec.transport.base import BaseTransport


class _RecordingTransport(BaseTransport):
    """A transport that answers the preflight and records that it was closed.

    A real transport would need a server; what these tests are about is the
    client's own lifecycle handling, which sits above the wire. Only
    server_info is given a real answer because that is what the preflight
    handshake calls.
    """

    def __init__(self, *, fail_preflight: bool = False) -> None:
        self.released = False
        self._fail_preflight = fail_preflight

    @override
    def _release(self) -> None:
        self.released = True

    @override
    def server_info(self) -> InfoResponse:
        if self._fail_preflight:
            raise GoVecConnectionError("server is down")

        return InfoResponse(
            quantization="none",
            index_type="brute",
            distance_metric="cosine",
            dimensions=1536,
            vector_count=0,
            enable_mmap=False,
            version="dev",
        )

    @override
    def health(self) -> HealthResponse:
        self._ensure_open()
        return HealthResponse(status="ok")

    @override
    def get_stats(self) -> GetStatsResponse:
        raise NotImplementedError

    @override
    def flush(self) -> FlushResponse:
        raise NotImplementedError

    @override
    def reset(self) -> ResetResponse:
        raise NotImplementedError

    @override
    def get_by_id(self, vector_id: str) -> GetByIdResponse | None:
        raise NotImplementedError

    @override
    def insert(self, request: InsertRequest) -> InsertResponse:
        raise NotImplementedError

    @override
    def insert_batch(self, requests: list[InsertRequest]) -> BatchInsertResponse:
        raise NotImplementedError

    @override
    def search(self, request: SearchRequest) -> list[SearchResponse]:
        raise NotImplementedError

    @override
    def delete(self, vector_id: str) -> DeleteResponse:
        raise NotImplementedError


@pytest.fixture
def client_with(monkeypatch: pytest.MonkeyPatch):
    """Builds a GoVecClient over a recording transport instead of a real one."""

    def _build(
        *, fail_preflight: bool = False
    ) -> tuple[GoVecClient, _RecordingTransport]:
        transport = _RecordingTransport(fail_preflight=fail_preflight)
        monkeypatch.setattr(
            "govec.transport.rest.RESTTransport",
            lambda *args, **kwargs: transport,
        )
        client = GoVecClient(
            host="testserver", port=9697, api_key="", protocol="rest", tls=False
        )
        return client, transport

    return _build


def test_close__called__releases_the_transport(client_with) -> None:
    # Arrange
    client, transport = client_with()

    # Act
    client.close()

    # Assert
    assert transport.released


def test_close__called_twice__does_not_raise(client_with) -> None:
    # Arrange
    client, transport = client_with()

    # Act
    client.close()
    client.close()

    # Assert
    assert transport.released


def test_context_manager__block_exits__releases_the_transport(client_with) -> None:
    # Arrange
    client, transport = client_with()

    # Act
    with client as entered:
        assert entered is client
        assert not transport.released

    # Assert
    assert transport.released


def test_context_manager__block_raises__still_releases_and_propagates(
    client_with,
) -> None:
    # Arrange
    client, transport = client_with()

    # Act / Assert
    with pytest.raises(ValueError):
        with client:
            raise ValueError("boom")

    assert transport.released


def test_init__preflight_handshake_fails__closes_the_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The constructor raises rather than returning an object, so the caller has
    # nothing to close. Without this the httpx pool or gRPC channel the
    # transport already opened would leak on every failed connection attempt.
    # Built inline rather than through the fixture so the transport is still
    # reachable after the construction that threw.
    transport = _RecordingTransport(fail_preflight=True)
    monkeypatch.setattr(
        "govec.transport.rest.RESTTransport", lambda *args, **kwargs: transport
    )

    # Act
    with pytest.raises(GoVecConnectionError):
        GoVecClient(
            host="testserver", port=9697, api_key="", protocol="rest", tls=False
        )

    # Assert
    assert transport.released


def test_init__unknown_protocol__is_rejected() -> None:
    # Arrange / Act / Assert
    with pytest.raises(Exception):
        GoVecClient(
            host="testserver",
            port=9697,
            api_key="",
            protocol="carrier-pigeon",  # ty: ignore[invalid-argument-type]
            tls=False,
        )
