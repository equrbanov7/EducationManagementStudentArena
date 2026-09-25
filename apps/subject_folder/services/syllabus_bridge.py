"""Təsdiqlənmiş sillabus → qovluq strukturu (mövzular + sərbəst iş slotları).

Yalnız ``APPROVED`` versiya oxunur (jurnalın mövzu mənbəyi ilə eyni qayda —
``apps/registrar/journal_topics.py``): qaralama sillabusun mövzuları qovluğa
sızmır. Sillabus ``apps.syllabus.public`` fasadından oxunur.

Sillabus bir neçə səviyyədə ola bilər (açılış / fənn+semestr / baza). Qovluq
bir müəllimin fənn üzrə İŞ SAHƏSİDİR və bir neçə açılışa təyin olunur; ona
görə mənbə belə seçilir: (1) açıq verilmiş açılış; (2) müəllimin həmin fənn
(və semestr) üzrə TƏSDİQLƏNMİŞ sillabuslu ilk açılışı; (3) semestr/baza
səviyyəli dosye.
"""

from __future__ import annotations

import hashlib
import re

from . import lookups

_SPACE_RE = re.compile(r"\s+")
_WEEK = "week"
_SELF = "self"


def _syllabus():
    from apps.syllabus import public as syllabus_public

    return syllabus_public


def topic_uid(title: str) -> str:
    """Sillabus mövzusunun SABİT açarı — normallaşdırılmış başlığın sha1-i (16 hex)."""
    normalized = _SPACE_RE.sub(" ", str(title or "").strip().casefold())
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]  # noqa: S324 — açar, kriptoqrafiya deyil


def approved_version_for_offering(offering):
    """Açılışın qüvvədə olan TƏSDİQLƏNMİŞ sillabus versiyası və ya ``None``."""
    api = _syllabus()
    syllabus = api.syllabus_for_offering_obj(offering)
    return api.approved_version_for(syllabus)


def approved_version_for_folder(folder, *, offering=None):
    """Qovluğun sinxron mənbəyi — TƏSDİQLƏNMİŞ versiya və ya ``None`` (modul docstring-i)."""
    if offering is not None:
        return approved_version_for_offering(offering)
    offerings = lookups.offering_model().objects.filter(organization=folder.organization, subject=folder.subject)
    if folder.period_id:
        offerings = offerings.filter(period_id=folder.period_id)
    taught = (
        offerings.filter(lookups.taught_offerings_q(folder.owner))
        .select_related("organization", "subject", "period")
        .order_by("-period__start_date", "pk")
    )
    for candidate in taught[:20]:
        version = approved_version_for_offering(candidate)
        if version is not None:
            return version
    api = _syllabus()
    syllabus = api.syllabus_for_offering(
        organization=folder.organization,
        subject_id=folder.subject_id,
        period_id=folder.period_id,
        instructor_id=folder.owner_id,
    )
    return api.approved_version_for(syllabus)


def _sections(version) -> dict:
    return _syllabus().section_data_map(version) if version is not None else {}


def week_topics(version) -> list[dict]:
    """``[{"uid", "title", "week_no", "outcome"}]`` — mövzu BİR DƏFƏ (təkrar başlıq atlanır)."""
    rows = (_sections(version).get(_WEEK) or {}).get("rows") or []
    topics, seen = [], set()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        title = str(row.get("topic") or "").strip()
        if not title:
            continue
        uid = topic_uid(title)
        if uid in seen:
            continue
        seen.add(uid)
        topics.append(
            {"uid": uid, "title": title[:255], "week_no": index, "outcome": str(row.get("outcome") or "")[:32]}
        )
    return topics


def selfwork_structure(version) -> dict | None:
    """Sillabusun sərbəst iş strukturu: ``{"option", "count", "per_score", "titles"}`` və ya ``None``.

    Yalnız siyasətin İCAZƏ VERDİYİ variantlar (``SELFWORK_OPTIONS``) qəbul olunur;
    başqa/boş variant = struktur yoxdur (slot yaradılmır).
    """
    data = _sections(version).get(_SELF) or {}
    option = str(data.get("option") or "").strip()
    config = _syllabus().SELFWORK_OPTIONS.get(option)
    if config is None:
        return None
    titles = [str(row.get("title") or "").strip()[:255] for row in (data.get("topics") or []) if isinstance(row, dict)]
    return {
        "option": option,
        "count": int(config["count"]),
        "per_score": int(config["per_score"]),
        "titles": titles,
    }


def selfwork_total() -> int:
    return int(_syllabus().SELFWORK_TOTAL_SCORE)


__all__ = [
    "approved_version_for_folder",
    "approved_version_for_offering",
    "selfwork_structure",
    "selfwork_total",
    "topic_uid",
    "week_topics",
]
