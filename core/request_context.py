"""
Thread-local request context storage.

Provides a lightweight mechanism to store per-request values (such as the
correlation/request ID) in a thread-local so that logging formatters and
filters can access them without being passed the request object explicitly.

Usage
-----
In middleware::

    from core.request_context import set_request_id, clear_request_id
    set_request_id("abc-123")
    ...
    clear_request_id()

In code that only needs to read the ID::

    from core.request_context import get_request_id
    rid = get_request_id()   # returns None when outside a request
"""

from __future__ import annotations

import threading

_local = threading.local()


def set_request_id(request_id: str | None) -> None:
    """Store *request_id* in the current thread's local storage."""
    _local.request_id = request_id


def get_request_id() -> str | None:
    """Return the request ID stored for the current thread, or ``None``."""
    return getattr(_local, "request_id", None)


def clear_request_id() -> None:
    """Remove the request ID from the current thread's local storage."""
    try:
        del _local.request_id
    except AttributeError:
        pass
