"""Serve the video or captions belonging to a visible FAQ entry, with byte seeking."""

import re
from functools import partial
from pathlib import Path

from django.core.handlers.asgi import ASGIRequest
from django.http import Http404, HttpResponse, HttpResponseNotFound, StreamingHttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from django.views.decorators.vary import vary_on_cookie

from asgiref.sync import sync_to_async

from .._helpers import _load_user_profile, _role_capabilities
from .faq_catalog import GUIDES, PUBLIC_LOGIN_GUIDES, media_metadata

BUILTIN_DIR = Path(__file__).resolve().parents[2] / "guide_media"
_MIME = {"mp4": "video/mp4", "vtt": "text/vtt; charset=utf-8"}
_CHUNK = 256 * 1024
_SINGLE_RANGE = re.compile(r"bytes=(\d{0,20})-(\d{0,20})\Z", re.ASCII)


def _requested_range(header, size):
    """Inclusive offsets, or None for a full response. Reject unsatisfiable ranges."""
    if not header:
        return None
    match = _SINGLE_RANGE.fullmatch(header.strip())
    if match is None or not any(match.groups()) or not size:
        raise ValueError
    first, last = match.groups()
    if first:
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1
    else:
        start, end = max(0, size - int(last)), size - 1
    if start > end:
        raise ValueError
    return start, end


class _Body:
    def __init__(self, stream, length):
        self.stream = stream
        self.remaining = length

    def read(self):
        chunk = self.stream.read(min(_CHUNK, self.remaining)) if self.remaining else b""
        self.remaining -= len(chunk)
        return chunk

    def __iter__(self):
        return iter(self.read, b"")

    def close(self):
        self.stream.close()


class _AsyncBody(_Body):
    """Django's ASGI adapter would otherwise collect a synchronous iterator in RAM."""

    __iter__ = None

    async def __aiter__(self):
        read = sync_to_async(self.read, thread_sensitive=False)
        while chunk := await read():
            yield chunk


def _stream(request, *, size, open_stream, content_type):
    headers = {"Accept-Ranges": "bytes", "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"}
    # An If-Range validator cannot match: we do not expose reusable resource validators.
    header = None if request.headers.get("If-Range") else request.headers.get("Range")
    try:
        bounds = _requested_range(header, size)
    except ValueError:
        return HttpResponse(status=416, headers={**headers, "Content-Range": f"bytes */{size}"})
    start, end = bounds if bounds else (0, size - 1)
    length = end - start + 1
    headers["Content-Length"] = str(length)
    if bounds:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    options = {"status": 206 if bounds else 200, "content_type": content_type, "headers": headers}
    if request.method == "HEAD" or not length:
        return HttpResponse(**options)
    body = _AsyncBody if isinstance(request, ASGIRequest) else _Body
    return StreamingHttpResponse(body(open_stream(start, end, bool(bounds)), length), **options)


def _local_stream(path, start, end, has_range):
    stream = path.open("rb")
    if start:
        stream.seek(start)
    return stream


def _object_stream(storage, name, start, end, has_range):
    return storage.open_range(name, f"bytes={start}-{end}" if has_range else None)


def _resolve(request, key):
    if not request.user.is_authenticated or not request.user.is_active:
        return None
    from .faq_editor_catalog import resolve_entry

    profile, _ = _load_user_profile(request.user)
    capabilities = _role_capabilities(request.user, profile)
    sections = capabilities["allowed_sections"]
    if "faq" not in sections:
        return None
    return resolve_entry(request, key, sections=sections, base_capabilities=capabilities)


@require_safe
@never_cache
@vary_on_cookie
def faq_media(request, key, extension):
    try:
        return _serve_guide(request, _resolve(request, key), extension)
    except Http404:
        return HttpResponseNotFound()


@require_safe
def login_media(request, key, extension):
    # The sign-in page always serves its shipped guides, even with an existing session.
    guide = next((guide for guide in GUIDES if guide.key == key), None) if key in PUBLIC_LOGIN_GUIDES else None
    return _serve_guide(request, guide, extension)


def _serve_guide(request, guide, extension):
    if extension not in _MIME:
        raise Http404
    if guide is None or (extension == "vtt" and not guide.has_subtitles):
        raise Http404
    upload = getattr(guide, "video_file" if extension == "mp4" else "subtitle_file", None)
    try:
        if upload:
            storage = upload.storage
            name = upload.name
            org_id = getattr(getattr(request, "organization", None), "pk", None)
            if not org_id or not re.fullmatch(
                rf"faq_guides/{re.escape(str(org_id))}/[0-9a-f]{{32}}\.{extension}", name
            ):
                raise Http404
            size = storage.size(name)
            if hasattr(storage, "open_range"):
                open_stream = partial(_object_stream, storage, name)
            else:
                open_stream = partial(_local_stream, Path(storage.path(name)))
        else:
            if guide.video not in media_metadata() or not re.fullmatch(r"[a-zA-Z0-9_-]+", guide.video):
                raise Http404
            path = BUILTIN_DIR / f"{guide.video}.{extension}"
            size = path.stat().st_size

            open_stream = partial(_local_stream, path)
        response = _stream(request, size=size, open_stream=open_stream, content_type=_MIME[extension])
    except FileNotFoundError:
        raise Http404 from None
    return response
