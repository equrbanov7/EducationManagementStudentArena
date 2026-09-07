"""QA klonundakı test hesabları (istifadəçi adları sirr deyil; parol kənar fayldan gəlir)."""

from __future__ import annotations

import os
import pathlib
import re

STAFF = "staff"
STUDENT = "student"

#: (username, rol açarı, portal) — TEST_HESABLARI.md ilə eyni sıra.
ACCOUNTS: list[tuple[str, str, str]] = [
    ("staging_admin", "superadmin", STAFF),
    ("qa.rector", "rector", STAFF),
    ("qa.vice_rector", "vice_rector", STAFF),
    ("qa.ikt_rehber", "ikt_rehber", STAFF),
    ("qa.exam_center_head", "exam_center_head", STAFF),
    ("qa.exam_center", "exam_center", STAFF),
    ("qa.teaching_office_head", "teaching_office_head", STAFF),
    ("qa.dean", "dean", STAFF),
    ("qa.chair_head", "chair_head", STAFF),
    ("qa.sec.hr", "hr", STAFF),
    ("qa.sec.exam_center_staff", "exam_center_staff", STAFF),
    ("qa.student_services", "student_services", STAFF),
    ("qa.teaching_office_staff", "teaching_office_staff", STAFF),
    ("qa.teacher", "teacher", STAFF),
    ("qa.program_coordinator", "program_coordinator", STAFF),
    ("qa.lab_assistant", "lab_assistant", STAFF),
    ("qa.sec.assistant", "assistant", STAFF),
    ("qa.tutor", "tutor", STAFF),
    ("qa.lead_student", "lead_student", STUDENT),
    ("qa.sec.member", "member", STAFF),
    ("qa.student", "student", STUDENT),
    ("qa.alumni", "alumni", STUDENT),
    # İzolyasiya variantları
    ("qa.sec.chair_head_b", "chair_head_b", STAFF),
    ("qa.sec.dean_b", "dean_b", STAFF),
    ("qa.sec.ikt_rehber_b", "ikt_rehber_b", STAFF),
    ("qa.sec.teacher_a", "teacher_a", STAFF),
    ("qa.sec.teacher_b", "teacher_b", STAFF),
    ("qa.sec.student_b", "student_b", STUDENT),
    ("qa.sec.inactive_ikt", "inactive_ikt", STAFF),
]

BY_USERNAME = {u: (r, p) for u, r, p in ACCOUNTS}
BY_ROLE = {r: (u, p) for u, r, p in ACCOUNTS}

_ACCOUNTS_FILE = pathlib.Path.home() / "EMSArena-backups" / "TEST_HESABLARI.md"
_PASSWORD_RE = re.compile(r"Parol \(hamısı eyni\):\*\*\s*`([^`]+)`")


def qa_password(username: str = "") -> str:
    """``QA_PASSWORD`` env → əks halda kənar hesab faylından oxu.

    ``qa.sec.*`` hesabları ayrı parolla yaradılıb (``QA_SEC_PASSWORD`` env və ya
    defolt ``QaSec2026!``); əvvəlcə ümumi parol sınanır, uğursuz olsa alternativ.
    """
    env = os.environ.get("QA_PASSWORD")
    if env:
        return env
    if _ACCOUNTS_FILE.exists():
        match = _PASSWORD_RE.search(_ACCOUNTS_FILE.read_text(encoding="utf-8"))
        if match:
            return match.group(1)
    raise SystemExit("QA parolu tapılmadı: QA_PASSWORD env və ya ~/EMSArena-backups/TEST_HESABLARI.md lazımdır")


def qa_sec_password() -> str:
    return os.environ.get("QA_SEC_PASSWORD", "QaSec2026!")


def portal_for(username: str) -> str:
    return BY_USERNAME.get(username, ("", STAFF))[1]


def role_of(username: str) -> str:
    return BY_USERNAME.get(username, (username, STAFF))[0]
