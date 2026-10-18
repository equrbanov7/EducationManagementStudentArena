"""Tədris planı sətrinin SEÇMƏ sahələri (ekran 05 dialoqu) — oxuma, doğrulama, blok sinxronu.

2026-10-19 düzəlişi: sətir dialoqunda «Seçmə fənn» / «Seçmə bloku» / «Seçiləcək
fənn sayı» sahələri YOX idi, server isə ``is_elective``-i hər yazıda
``POST.get(...) == "1"`` ilə oxuyurdu — seçmə sətrin saatını redaktə etmək onu
səssizcə MƏCBURİ fənnə çevirirdi. Qaydalar:

* **Qismən yeniləmə təhlükəsizdir** — POST-da OLMAYAN sahə sətrin MÖVCUD
  dəyərini saxlayır (köhnə klient / başqa forma bayrağı silmir).
* **Məcburi sətirdə** blok və say tətbiq olunmur: blok boş, say 1.
* **Seçmə sətirdə** blok məcburidir (blok olmadan seçim qurulmur —
  ``workload.offering_electives`` boş bloku nəzərə almır), say 1–20.
* Eyni blokun (plan + semestr + blok) sətirləri EYNİ «seçiləcək say»ı daşıyır —
  ``registrar.services`` bloku ilk sətrin sayı ilə qurur, ona görə yazıdan sonra
  qalan sətirlər sinxronlaşdırılır.

``curriculum_actions.py`` 600 sətir büdcəsinə yaxın olduğu üçün ayrı moduldur.
"""

from __future__ import annotations

from django.utils.translation import pgettext

from .models import CurriculumSubject

_CTX = "accounts.curriculum"

#: Seçmə blokdan seçiləcək fənn sayının yuxarı həddi (dialoqdakı `max` ilə eyni).
MAX_REQUIRED_CHOICES = 20


class ElectiveFieldError(Exception):
    """Seçmə sahəsi doğrulanmadı — HTTP qatı 400 + ``field`` qaytarır (pozisional konstruktor, B042)."""

    def __init__(self, code: str, message: str, field: str):
        super().__init__(code, message, field)
        self.code = code
        self.message = message
        self.field = field


def elective_snapshot(row) -> dict:
    """Audit üçün sətrin seçmə vəziyyəti."""
    return {
        "is_elective": bool(row.is_elective),
        "elective_group": row.elective_group or "",
        "required_choices": row.required_choices,
    }


def elective_fields(post, instance) -> dict:
    """POST + mövcud sətirdən yekun seçmə sahələri; uyğunsuzluqda :class:`ElectiveFieldError`."""
    if "is_elective" in post:
        is_elective = (post.get("is_elective") or "") == "1"
    else:
        is_elective = bool(instance.is_elective)
    if not is_elective:
        return {"is_elective": False, "elective_group": "", "required_choices": 1}

    if "elective_group" in post:
        group = (post.get("elective_group") or "").strip()[:50]
    else:
        group = instance.elective_group or ""
    if not group:
        raise ElectiveFieldError(
            "elective_group_required",
            pgettext(_CTX, "Seçmə fənn üçün seçmə bloku göstərilməlidir."),
            "elective_group",
        )

    raw = (post.get("required_choices") or "").strip() if "required_choices" in post else ""
    try:
        choices = int(raw) if raw else (instance.required_choices or 1)
    except ValueError:
        choices = 0
    if not 1 <= choices <= MAX_REQUIRED_CHOICES:
        raise ElectiveFieldError(
            "bad_required_choices",
            pgettext(_CTX, "Seçiləcək fənn sayı 1–20 aralığında olmalıdır."),
            "required_choices",
        )
    return {"is_elective": True, "elective_group": group, "required_choices": choices}


def sync_block_choices(row) -> int:
    """Blokun DİGƏR sətirlərinə eyni «seçiləcək say»ı yazır; yenilənən sətir sayını qaytarır."""
    if not row.is_elective or not row.elective_group:
        return 0
    return (
        CurriculumSubject.objects.filter(
            curriculum_id=row.curriculum_id,
            semester_number=row.semester_number,
            is_elective=True,
            elective_group=row.elective_group,
        )
        .exclude(pk=row.pk)
        .exclude(required_choices=row.required_choices)
        .update(required_choices=row.required_choices)
    )


__all__ = [
    "MAX_REQUIRED_CHOICES",
    "ElectiveFieldError",
    "elective_fields",
    "elective_snapshot",
    "sync_block_choices",
]
