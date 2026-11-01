"""Only the source-proven9544 seminar grant; existing lecturer identity is held."""

import hashlib
import html
import io
import os
import stat
import unicodedata

from .sbio235_state import RepairError

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
OFFERING = "e09d3997-ac19-4e7d-97fb-e1d170a58bff"
SUBJECT = "028a6dc1-f127-4b16-ae63-0b52ba946c6a"
GROUP = "f488b31c-69a9-44ee-89a2-1f539c0b1538"
ROW = "d0b87edb-a2c9-4977-ba23-72848af9ca92"
TASK = "743c143e-254a-4ef1-bf73-c368a477cc2f"
TEACHER = 9544
OWNER = 8170
ASSIGNMENTS = {
    "28696ec2-c477-4b12-ba5c-3a61e12fcc80": (TEACHER, "seminar", 15),
    "adf0a569-2232-425b-b7b4-96e0f922ecff": (OWNER, "lecture", 30),
}
SOURCE_SHA = "209dfa543720f11421a5aab910318e193e49799b2cf98b8fc27f5ed885fb5b16"
CELL_HASHES = {
    "A98": "c74ca8330529a9db2a78f2ffcca2130a158883d6a992e9375e4bd3e81fb4e4fa",
    "B101": "8ad1b5f38ef898e4159ef8d731106c305edefb5f8f212fea29ebc27daf254cb3",
    "C101": "ba5cb62038fb67dd4287c3aaafcbfdbd997d007f59b1c4558d737e12cc088b0a",
}
GROUP_TEXT_SHA256 = "258872bad38aced71ee539842eeb1e5c70bfa24d71ea2890b208593b1a61adcb"
TEACHER_NAME_SHA = "9391c9dcfc26a18ac2b8b6bc2adb9a2f8d3352af04f8040047b652b8f0e74001"
RESOURCE = "workload.reviewed_biostat_seminar_share"


def normalized(value):
    return (
        " ".join(unicodedata.normalize("NFKC", html.unescape(str(value or ""))).split())
        .replace("İ", "i")
        .replace("I", "ı")
        .lower()
    )


def text_sha(value):
    return hashlib.sha256(normalized(value).encode()).hexdigest()


def teacher_identity_sha(value):
    return text_sha(normalized(value).removesuffix(" qızı").removesuffix(" oğlu"))


def load_source(path, sha256):
    if sha256 != SOURCE_SHA:
        raise RepairError("pinned_official_xlsx_sha_required")
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 10_000_000:
            raise RepairError("private_official_xlsx_required")
        raw = stream.read()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise RepairError("official_xlsx_changed")
    from openpyxl import load_workbook

    book = load_workbook(io.BytesIO(raw), read_only=True, data_only=False)
    try:
        sheet = book["Dərs yükü"]
        if any(text_sha(sheet[cell].value) != expected for cell, expected in CELL_HASHES.items()):
            raise RepairError("official_teacher_subject_group_changed")
        if (
            any(sheet[cell].value not in (None, "") for cell in ("A99", "A100", "A101", "G101", "I101"))
            or sheet["H101"].value != 15
        ):
            raise RepairError("official_seminar_geometry_changed")
        if teacher_identity_sha(sheet["A98"].value) != TEACHER_NAME_SHA:
            raise RepairError("official_teacher_identity_changed")
    finally:
        book.close()
    return SOURCE_SHA
