"""Yeni dərs modalının mövzu siyahısı üçün EHTİYAT mənbə — açılışın təsdiqlənmiş sillabusu yoxdursa.

Sahib 2026-11-10: «müəllimlərin bir çoxunda "sillabus yoxdur" deyir, mövzu gəlmir — düzəlt». Səbəb:
``journal_topics`` mövzunu YALNIZ həmin açılışa uyğun TƏSDİQLƏNMİŞ sillabusdan götürür; müəllimin sillabusu
hələ təsdiqlənməyibsə (qaralama / göndərilib) və ya xarici dil səviyyə qrupunun sillabusu başqa açılışa
yazılıbsa siyahı boş qalırdı.

Ehtiyat sırası (hamısı yalnız MÖVZU BAŞLIQLARIDIR — ``Lesson.syllabus_week`` bağı və «keçilib» statusu yenə
yalnız təsdiqlənmiş sillabusdan gəlir, ``resolve_syllabus_week`` dəyişmir):

1. LMS kursunun mövzuları (köhnə davranış);
2. açılışa uyğun dosyenin ƏN SON versiyası (təsdiqlənməmiş də) — müəllimin öz yazdığı plan;
3. EYNİ fənnin başqa TƏSDİQLƏNMİŞ sillabusu — əvvəlcə eyni müəllim, sonra eyni semestr, sonra ən yenisi.

Nəticə açılış obyektinə memo-lanır (jurnal səhifəsi siyahını bir neçə dəfə istəyir).
"""

from __future__ import annotations

from django.db.models import Case, IntegerField, Value, When

_MEMO_ATTR = "_journal_topic_fallback_memo"


def _version_rows(version) -> list:
    if version is None:
        return []
    from apps.syllabus import public as syllabus_services

    week = next((row.data or {} for row in version.sections.all() if row.section_id == "week"), {})
    return syllabus_services.week_plan_rows(week)


def _rows_to_topics(plan_rows, offering) -> list:
    from .journal_topics import _week_entry
    from .practical_label import offering_is_practical

    practical = offering_is_practical(offering)
    out, seen = [], set()
    for index, entry in enumerate(plan_rows, start=1):
        row = _week_entry(index, entry, practical=practical)
        if not row["title"] or row["title"] in seen:
            continue
        seen.add(row["title"])
        # ``week`` QƏSDƏN boşdur: ehtiyat mənbənin sətri jurnala bağlanmır.
        out.append({"title": row["title"], "kinds": row["kinds"], "week": None, "fallback": True})
    return out


def _own_draft_rows(offering) -> list:
    from apps.syllabus import public as syllabus_services

    syllabus = syllabus_services.syllabus_for_offering_obj(offering)
    if syllabus is None or not syllabus.current_version_id:
        return []
    return _version_rows(syllabus.current_version)


def _peer_approved_rows(offering) -> list:
    from django.apps import apps as django_apps

    Syllabus = django_apps.get_model("syllabus", "Syllabus")
    candidates = Syllabus.objects.filter(
        organization_id=offering.organization_id,
        subject_id=offering.subject_id,
        is_active=True,
        approved_version__isnull=False,
        approved_version__status="approved",
    )
    rank = Case(
        When(author_id=offering.instructor_id, period_id=offering.period_id, then=Value(0)),
        When(author_id=offering.instructor_id, then=Value(1)),
        When(period_id=offering.period_id, then=Value(2)),
        default=Value(3),
        output_field=IntegerField(),
    )
    for syllabus in (
        candidates.select_related("approved_version").annotate(_rank=rank).order_by("_rank", "-updated_at")[:5]
    ):
        rows = _version_rows(syllabus.approved_version)
        if any(str(row.get("topic") or "").strip() for row in rows):
            return rows
    return []


def fallback_topic_rows(offering) -> list:
    """``[{"title", "kinds", "week": None, "fallback": True}]`` — təsdiqlənmiş plan YOXDURSA çağırılır."""
    if offering is None:
        return []
    if hasattr(offering, _MEMO_ATTR):
        return getattr(offering, _MEMO_ATTR)
    from .journal_topics import _course_topic_titles

    rows = [{"title": title, "kinds": (), "week": None} for title in _course_topic_titles(offering)]
    if not rows:
        rows = _rows_to_topics(_own_draft_rows(offering), offering)
    if not rows and offering.subject_id:
        rows = _rows_to_topics(_peer_approved_rows(offering), offering)
    setattr(offering, _MEMO_ATTR, rows)
    return rows
