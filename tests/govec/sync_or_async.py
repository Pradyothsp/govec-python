"""Lets one test body drive a sync or an async transport or client.

A test parametrised over both calls `await settle(thing.search(...))`: the
async one hands back a coroutine to await, the sync one the answer itself.
That keeps one test per behaviour instead of a copy per flavour, so the two
can't drift apart unnoticed.
"""

from collections.abc import Awaitable
from typing import Literal, Protocol, cast, runtime_checkable

from govec.async_client import AsyncGoVecClient
from govec.client import GoVecClient
from govec.client import Protocol as WireProtocol
from govec.transport.base import DEFAULT_BATCH_TIMEOUT, DEFAULT_TIMEOUT

type ClientKind = Literal["sync", "async"]
type AnyClient = GoVecClient | AsyncGoVecClient
CLIENT_KINDS: list[ClientKind] = ["sync", "async"]


@runtime_checkable
class _Closes(Protocol):
    def close(self) -> None: ...


@runtime_checkable
class _AsyncCloses(Protocol):
    async def aclose(self) -> None: ...


async def settle[T](result: T | Awaitable[T]) -> T:
    if isinstance(result, Awaitable):
        # isinstance can't recover T from a bare Awaitable.
        return await cast(Awaitable[T], result)

    return result


async def shut(thing: _Closes | _AsyncCloses) -> None:
    if isinstance(thing, _AsyncCloses):
        await thing.aclose()
    else:
        thing.close()


async def connect_client(
    kind: ClientKind,
    host: str,
    port: int,
    protocol: WireProtocol,
    timeout: float | None = DEFAULT_TIMEOUT,
    batch_timeout: float | None = DEFAULT_BATCH_TIMEOUT,
) -> AnyClient:
    """Connect a client of the given kind, exactly as a caller would."""
    if kind == "sync":
        return GoVecClient.connect(
            host,
            port,
            "",
            protocol,
            tls=False,
            timeout=timeout,
            batch_timeout=batch_timeout,
        )

    return await AsyncGoVecClient.connect(
        host,
        port,
        "",
        protocol,
        tls=False,
        timeout=timeout,
        batch_timeout=batch_timeout,
    )
