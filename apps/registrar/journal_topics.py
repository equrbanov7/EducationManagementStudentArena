"""Jurnal dərs MÖVZUSUNUN mənbəyi — təsdiqlənmiş sillabus, sonra LMS kursu.

README §6.5-in birinci sətri: «Təsdiqlənmiş sillabus → jurnal strukturu
yaranır».  Yəni yeni dərs modalındakı mövzu siyahısı ilk növbədə sillabusun
həftəlik planından gəlir; LMS kursunun mövzuları yalnız GERİ ÇƏKİLMƏ mənbəyidir
(sillabus hələ təsdiqlənməyən köhnə açılışlar üçün).

Modul ``journal_extras``-dan ayrılıb: həmin fayl 600 sətirlik modul-ölçü
büdcəsinə (``scripts/check_module_size.py``) dayanmışdı.  Davranış dəyişmir,
adlar ``journal_extras``-dan da import oluna bilir.

Asılılıq istiqaməti: ``registrar → syllabus`` (bu istiqamət artıq mövcuddur —
``registrar/syllabus_views.py``, ``registrar/public.py``), əks istiqamət YOXDUR.
"""

from __future__ import annotations

#: Sillabusun həftəlik cədvəlindəki saat növləri — jurnal ``LessonKind`` açarları
#: ilə EYNİ sətirlərdir (``apps.syllabus.constants.LESSON_HOUR_KINDS``).
SYLLABUS_HOUR_KINDS = ("lecture", "seminar", "lab")


def syllabus_topic_rows(offering):
    """TƏSDİQLƏNMİŞ sillabusun mövzu planı — mövzu bir dəfə, saat növ üzrə.

    Dizayn qaydası §8/0: «Sillabusun həftəlik planında mövzu BİR DƏFƏ yazılır,
    saat isə mühazirə / seminar / laboratoriya üzrə AYRICA saxlanılır.  Jurnalda
    həmin mövzu hər növ üçün ayrı dərs sətri kimi açılır — başlıq eynidir,
    ``kind`` fərqlidir.»

    Nəticə: ``[{"title": str, "kinds": (…)}]``.  Yalnız ``APPROVED`` versiya
    oxunur (§8/9 və §6.5) — qaralama versiyanın mövzuları jurnala sızmır.
    Sillabus yoxdursa BOŞ siyahı (çağıran LMS kursuna geri çəkilir).
    """
    from apps.syllabus import services as syllabus_services

    syllabus = syllabus_services.syllabus_for_offering(
        organization=offering.organization,
        offering_id=offering.id,
        subject_id=offering.subject_id,
        period_id=offering.period_id,
        instructor_id=offering.instructor_id,
    )
    version = syllabus_services.approved_version_for(syllabus)
    if version is None:
        return []
    week = next((row.data or {} for row in version.sections.all() if row.section_id == "week"), {})
    rows = []
    seen = set()
    for entry in week.get("rows") or []:
        if not isinstance(entry, dict):
            continue
        title = (entry.get("topic") or "").strip()
        if not title or title in seen:
            continue
        kinds = tuple(kind for kind in SYLLABUS_HOUR_KINDS if _positive(entry.get(kind)))
        seen.add(title)
        rows.append({"title": title, "kinds": kinds})
    return rows


def _positive(value) -> bool:
    try:
        return int(value or 0) > 0
    except (TypeError, ValueError):
        return False


def _course_topic_titles(offering):
    """LMS kursunun mövzuları — sillabus YOXDURSA geri çəkilmə mənbəyi."""
    if not offering.course_id:
        return []
    from django.apps import apps as django_apps

    CourseTopic = django_apps.get_model("courses", "CourseTopic")
    return list(
        CourseTopic.objects.filter(course_id=offering.course_id).order_by("order").values_list("title", flat=True)
    )


def lesson_topic_choices(offering):
    """Yeni dərs modalındakı mövzu SİYAHISI.

    MƏNBƏ SIRASI: (1) təsdiqlənmiş sillabusun həftəlik planı — README §6.5
    «Təsdiqlənmiş sillabus → jurnal strukturu yaranır»; (2) sillabus yoxdursa
    LMS kursunun mövzuları (köhnə davranış); (3) heç biri yoxdursa boş siyahı —
    şablon sərbəst mətn sahəsi göstərir.
    """
    rows = syllabus_topic_rows(offering)
    if rows:
        return [row["title"] for row in rows]
    return _course_topic_titles(offering)


def lesson_topic_meta(offering, lessons):
    """Mövzu dropdown-u üçün: hər mövzu + KEÇİRİLİB statusu (+ tarix) + DƏRS NÖVLƏRİ.

    ``kinds`` sillabusun həmin mövzu üçün saat verdiyi növlərdir; modal seçilmiş
    dərs tipinə uyğun olmayan mövzuları gizlədir (§8/0).  Sillabus mənbəyi
    yoxdursa ``kinds`` BOŞ qalır və filtr tətbiq olunmur (köhnə davranış).

    «Keçirilib» bayrağı NÖV NƏZƏRƏ ALINMADAN hesablanır (mövzunun ən azı bir
    dərsi keçilib), ``covered_kinds`` isə hansı növlərin bağlandığını göstərir.
    """
    covered = {}
    covered_kinds = {}
    for lesson in lessons:
        if not lesson.topic:
            continue
        covered.setdefault(lesson.topic, lesson.date)
        covered_kinds.setdefault(lesson.topic, set()).add(lesson.kind)
    rows = syllabus_topic_rows(offering)
    if not rows:
        rows = [{"title": title, "kinds": ()} for title in _course_topic_titles(offering)]
    return [
        {
            "title": row["title"],
            "covered": row["title"] in covered,
            "date": covered.get(row["title"]),
            "kinds": list(row["kinds"]),
            "kinds_attr": " ".join(row["kinds"]),
            "covered_kinds": sorted(covered_kinds.get(row["title"], ())),
        }
        for row in rows
    ]


__all__ = [
    "SYLLABUS_HOUR_KINDS",
    "lesson_topic_choices",
    "lesson_topic_meta",
    "syllabus_topic_rows",
]
