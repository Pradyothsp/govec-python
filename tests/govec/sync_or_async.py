"""Lets one test body drive a sync or an async transport.

A test parametrised over both calls `await settle(transport.search(...))`: the
async transport hands back a coroutine to await, the sync one the answer
itself. That keeps one test per behaviour instead of a copy per flavour, so
the two can't drift apart unnoticed.
"""

from collections.abc import Awaitable
from typing import cast

from govec.transport.base import AsyncBaseTransport, BaseTransport


async def settle[T](result: T | Awaitable[T]) -> T:
    if isinstance(result, Awaitable):
        # isinstance can't recover T from a bare Awaitable.
        return await cast(Awaitable[T], result)

    return result


async def shut(transport: BaseTransport | AsyncBaseTransport) -> None:
    if isinstance(transport, AsyncBaseTransport):
        await transport.aclose()
    else:
        transport.close()
