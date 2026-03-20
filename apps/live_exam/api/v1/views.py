"""
apps/live_exam/api/v1/views.py

Version 1 API views for the live exam app.
These thin wrappers delegate to the existing view implementations and add
the ``X-API-Version`` response header so clients can detect the version.
"""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse

from apps.live_exam.views.api import live_state_json as _live_state_json

_API_VERSION = "1"


def _versioned(response: JsonResponse) -> JsonResponse:
    """Attach the ``X-API-Version`` header to *response* and return it."""
    response["X-API-Version"] = _API_VERSION
    return response


def live_state_json_v1(request: HttpRequest, pin: str) -> JsonResponse:
    """
    GET /api/v1/live/<pin>/state/

    Returns the current state of a live exam session.
    Delegates to the canonical ``live_state_json`` implementation and adds
    the ``X-API-Version: 1`` response header.
    """
    return _versioned(_live_state_json(request, pin))
