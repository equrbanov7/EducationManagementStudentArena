"""Validate self-contained ISO BMFF video and plain WebVTT without external decoders."""

import math
import re
import struct

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from core.upload_security import validate_uploaded_file

MAX_VIDEO_MIB = 200
MAX_FORM_BYTES = 208 * 1024 * 1024


def _boxes(upload, start, end, budget):
    while start < end:
        if end - start < 8 or budget[0] <= 0:
            raise ValueError
        budget[0] -= 1
        upload.seek(start)
        size, kind = struct.unpack(">I4s", upload.read(8))
        header = 8
        if size == 1:
            size = struct.unpack(">Q", upload.read(8))[0]
            header = 16
        if size == 0:
            size = end - start
        if size < header or start + size > end:
            raise ValueError
        yield kind, start + header, start + size
        start += size


def _movie(upload, start, end, budget):
    duration, video = 0, False
    for kind, data, stop in _boxes(upload, start, end, budget):
        if kind == b"mvhd":
            upload.seek(data)
            raw = upload.read(min(32, stop - data))
            if raw[0] not in (0, 1):
                raise ValueError
            clock, length = struct.unpack_from(">IQ" if raw[0] else ">II", raw, 20 if raw[0] else 12)
            duration = length / clock
        elif kind == b"trak":
            for k, off, finish in _boxes(upload, data, stop, budget):
                if k != b"mdia":
                    continue
                for atom, pos, last in _boxes(upload, off, finish, budget):
                    if atom == b"hdlr" and last - pos >= 12:
                        upload.seek(pos + 8)
                        video |= upload.read(4) == b"vide"
    return duration if video else 0


def video_duration(upload):
    validate_uploaded_file(
        upload,
        allowed_extensions={"mp4"},
        allowed_mime_types={"video/mp4"},
        allowed_mime_prefixes=(),
        max_size_mb=MAX_VIDEO_MIB,
    )
    try:
        budget, duration, payload, mp4 = [10000], 0, False, False
        for kind, start, end in _boxes(upload, 0, upload.size, budget):
            if kind == b"ftyp" and start <= 16 and 8 <= end - start <= 512:
                upload.seek(start)
                brands = upload.read(end - start)
                tags = [brands[:4], *(brands[i : i + 4] for i in range(8, len(brands), 4))]
                mp4 = bool({b"isom", b"iso2", b"iso5", b"iso6", b"avc1", b"mp41", b"mp42", b"M4V "} & set(tags))
            elif kind == b"moov":
                duration = _movie(upload, start, end, budget)
            elif kind == b"mdat":
                payload |= end > start
        if not (mp4 and payload and math.isfinite(duration) and 0 < duration <= 86400):
            raise ValueError
        return duration
    except (ValueError, IndexError, ZeroDivisionError, struct.error, OSError) as exc:
        raise ValidationError(_("Oxuna bilən video treki və müddəti olan MP4 faylı seçin.")) from exc
    finally:
        upload.seek(0)


def _vtt_time(value):
    parts = value.split(":")
    return sum(float(bit) * 60**i for i, bit in enumerate(reversed(parts)))


def check_vtt(upload, duration):
    validate_uploaded_file(
        upload,
        allowed_extensions={"vtt"},
        allowed_mime_types={"text/vtt", "text/plain", "application/octet-stream"},
        allowed_mime_prefixes=(),
        max_size_mb=1,
    )
    try:
        upload.seek(0)
        text = upload.read().decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        blocks = re.split(r"\n[ \t]*\n", text.strip())
        if len(blocks) < 2 or blocks[0] != "WEBVTT" or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", text):
            raise ValueError
        stamp = r"(?:(?:\d{2,}):)?[0-5]\d:[0-5]\d\.\d{3}"
        for block in blocks[1:]:
            lines = block.splitlines()
            if "-->" not in lines[0]:
                lines = lines[1:]
            match = re.fullmatch(f"({stamp}) --> ({stamp})", lines[0])
            if not match or len(lines) < 2 or any("<" in line or ">" in line for line in lines[1:]):
                raise ValueError
            begin, end = map(_vtt_time, match.groups())
            if not (begin < end <= duration + 0.2):
                raise ValueError
    except (ValueError, IndexError) as exc:
        raise ValidationError(
            _("UTF-8 formatında, videonun müddətinə uyğun vaxtlı və sadə mətnli WebVTT faylı seçin.")
        ) from exc
    finally:
        upload.seek(0)
