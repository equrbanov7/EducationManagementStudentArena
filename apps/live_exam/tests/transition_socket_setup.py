"""Bounded scenario setup, independent of measured live-transition windows."""

import asyncio
from contextlib import asynccontextmanager


@asynccontextmanager
async def connected_sockets(sockets, *, timeout=20):
    """All sockets must be admitted before measuring; always release partial setup."""
    failed = False

    async def connect():
        for socket in sockets:
            # One overall setup deadline; do not cancel an admission merely
            # because Channels' default per-communicator 1s expires under xdist.
            await socket.connect(timeout=None)

    try:
        await asyncio.wait_for(connect(), timeout=timeout)
        yield
    except BaseException:
        failed = True
        raise
    finally:
        results = await asyncio.gather(*(socket.close() for socket in sockets), return_exceptions=True)
        if not failed:
            for result in results:
                if isinstance(result, BaseException):
                    raise result
