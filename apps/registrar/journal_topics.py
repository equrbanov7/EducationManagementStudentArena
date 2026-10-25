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

from django.db.models import prefetch_related_objects

#: Sillabusun həftəlik cədvəlindəki saat növləri — jurnal ``LessonKind`` açarları
#: ilə EYNİ sətirlərdir (``apps.syllabus.constants.LESSON_HOUR_KINDS``).
SYLLABUS_HOUR_KINDS = ("lecture", "seminar", "lab")


def normalize_topic(text) -> str:
    """Mövzu müqayisəsi üçün: boşluqlar sıxılır, registr nəzərə alınmır (``casefold``)."""
    return " ".join(str(text or "").split()).casefold()


def _approved_plan_rows(offering) -> list:
    """Açılışın TƏSDİQLƏNMİŞ sillabusunun ``week.rows`` lüğət sətirləri (sıra saxlanılır)."""
    from apps.syllabus import public as syllabus_services

    syllabus = syllabus_services.syllabus_for_offering_obj(offering)
    version = syllabus_services.approved_version_for(syllabus)
    if version is None:
        return []
    # Jurnal səhifəsi bunu bir neçə dəfə çağırır (mövzu seçimləri, mövzu meta…): bölmələr memo-lanmış
    # versiya obyektinə BİR dəfə prefetch olunur, sonrakı çağırışlar keşdən oxuyur (artıq prefetch
    # olunubsa — məs. ``selfwork_structure`` — sorğu yoxdur).
    prefetch_related_objects([version], "sections")
    week = next((row.data or {} for row in version.sections.all() if row.section_id == "week"), {})
    return syllabus_services.week_plan_rows(week)


def _week_entry(index, entry) -> dict:
    kinds = tuple(kind for kind in SYLLABUS_HOUR_KINDS if _positive(entry.get(kind)))
    return {"week": index, "title": str(entry.get("topic") or "").strip()[:255], "kinds": kinds}


def syllabus_week_rows(offering, *, plan_rows=None) -> list:
    """Həftəlik planın HƏR sətri nömrəsi ilə: ``[{"week": n, "title": str, "kinds": (…)}]``.

    ``week`` — ``Lesson.syllabus_week``-in semantikası: ``week.rows``-da 1-dən sıra, boş mövzulu sətirlər
    də sayılır (``title`` boş qalır). Yalnız ``APPROVED`` versiya; yoxdursa boş siyahı."""
    rows = _approved_plan_rows(offering) if plan_rows is None else plan_rows
    return [_week_entry(index, entry) for index, entry in enumerate(rows, start=1)]


def syllabus_topic_rows(offering):
    """TƏSDİQLƏNMİŞ sillabusun mövzu planı — mövzu bir dəfə, saat növ üzrə.

    Dizayn qaydası §8/0: «Sillabusun həftəlik planında mövzu BİR DƏFƏ yazılır,
    saat isə mühazirə / seminar / laboratoriya üzrə AYRICA saxlanılır.  Jurnalda
    həmin mövzu hər növ üçün ayrı dərs sətri kimi açılır — başlıq eynidir,
    ``kind`` fərqlidir.»

    Nəticə: ``[{"title": str, "kinds": (…), "week": n}]`` — ``week`` başlığın İLK sətrinin nömrəsidir.
    Yalnız ``APPROVED`` versiya oxunur (§8/9 və §6.5) — qaralama versiyanın mövzuları jurnala sızmır.
    Sillabus yoxdursa BOŞ siyahı (çağıran LMS kursuna geri çəkilir).
    """
    rows = []
    seen = set()
    for entry in syllabus_week_rows(offering):
        title = entry["title"]
        if not title or title in seen:
            continue
        seen.add(title)
        rows.append({"title": title, "kinds": entry["kinds"], "week": entry["week"]})
    return rows


def resolve_syllabus_week(offering, topic, *, current=None, week_rows=None):
    """Dərs mövzusunun bağlandığı plan sətri və ya ``None`` (uydurma bağ yoxdur).

    * mövzu ``current`` sətrinin başlığı ilə eynidirsə (normallaşdırılmış) — bağ QALIR (təkrar başlıq);
    * əks halda başlığı DƏQİQ (boşluq/registr normallaşdırılmış) uyğun gələn İLK sətir;
    * uyğun sətir yoxdursa (sərbəst mətn) və ya mövzu boşdursa — ``None``."""
    key = normalize_topic(topic)
    if not key:
        return None
    rows = syllabus_week_rows(offering) if week_rows is None else week_rows
    matches = [row["week"] for row in rows if row["title"] and normalize_topic(row["title"]) == key]
    if current in matches:
        return current
    return matches[0] if matches else None


def posted_topic(post):
    """Modalın mövzusu: sərbəst mətn (``lesson_topic_custom``) doludursa o, yoxdursa plan seçimi.

    ``None`` — sahə ümumiyyətlə göndərilməyib (redaktədə «dəyişmə»)."""
    custom = (post.get("lesson_topic_custom") or "").strip()
    if custom:
        return custom
    return post.get("lesson_topic")


def shown_topic(lesson) -> str:
    """Dərsin göstərilən mövzusu (``Lesson.display_topic``); sadə test obyektlərində ``topic``."""
    return getattr(lesson, "display_topic", None) or getattr(lesson, "topic", "") or ""


def attach_syllabus_topics(lessons, *, offering=None):
    """Mövzusu BOŞ, amma ``syllabus_week``-i olan dərslərə sətrin mövzusunu qoyur (``display_topic``).

    ``offering`` verilsə hamısı o açılışdandır (memo-lanmış sillabus — jurnal səhifəsi); verilməsə
    açılışlar üzrə TOPLU (``approved_week_rows_for_offerings``, ≤ 3 sorğu). Bağlı mövzusuz dərs yoxdursa
    sorğu YOXDUR. Təxirə salınmış (``only``) sahələr oxunmur — dərs başına əlavə sorğu yaranmasın."""
    need = []
    for lesson in lessons:
        state = vars(lesson)
        if state.get("topic") or not state.get("syllabus_week"):
            continue
        need.append(lesson)
    if not need:
        return lessons
    if offering is not None:
        plans = {offering.pk: _approved_plan_rows(offering)}
    else:
        from apps.syllabus import public as syllabus_services

        offerings = {lesson.offering_id: lesson.offering for lesson in need}
        plans = syllabus_services.approved_week_rows_for_offerings(offerings.values())
    for lesson in need:
        rows = plans.get(lesson.offering_id if offering is None else offering.pk) or []
        index = lesson.syllabus_week
        if 1 <= index <= len(rows):
            lesson._syllabus_topic = str(rows[index - 1].get("topic") or "").strip()[:255]
    return lessons


def week_progress(offering, lessons, *, today=None, week_rows=None) -> list:
    """Sillabus planının HƏR sətri üçün «keçilib» statusu (sahib 2026-10-25).

    Dərs sətrə ``syllabus_week`` ilə bağlanır; bağı olmayan dərs mövzusu sətrin başlığı ilə DƏQİQ
    (normallaşdırılmış) eynidirsə həmin başlığın İLK sətrinə sayılır. ``covered`` — bu günə qədər (daxil)
    keçirilmiş ən azı bir dərs; ``planned`` — yalnız gələcək tarixli dərs. Mövzusu boş və heç bir dərsə
    bağlı olmayan sətir göstərilmir. Nəticə: ``[{"week", "title", "kinds", "covered", "planned", "dates",
    "upcoming"}]`` (``dates`` — keçirilmiş dərslərin tarixləri, artan)."""
    from django.utils import timezone

    today = today or timezone.localdate()
    rows = syllabus_week_rows(offering) if week_rows is None else week_rows
    if not rows:
        return []
    first_by_title = {}
    for row in rows:
        if row["title"]:
            first_by_title.setdefault(normalize_topic(row["title"]), row["week"])
    held: dict = {}
    upcoming: dict = {}
    for lesson in lessons:
        linked = getattr(lesson, "syllabus_week", None) or 0
        week = linked if 1 <= linked <= len(rows) else None
        if week is None:
            week = first_by_title.get(normalize_topic(lesson.topic))
        if week is None:
            continue
        (held if lesson.date <= today else upcoming).setdefault(week, set()).add(lesson.date)
    out = []
    for row in rows:
        dates = sorted(held.get(row["week"], ()))
        later = sorted(upcoming.get(row["week"], ()))
        if not row["title"] and not dates and not later:
            continue
        out.append(
            {
                **row,
                "kinds": list(row["kinds"]),
                "covered": bool(dates),
                "planned": not dates and bool(later),
                "dates": dates,
                "upcoming": later,
            }
        )
    return out


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
        topic = shown_topic(lesson)  # mövzusuz, sillabus sətrinə bağlı dərs də sayılır (2026-10-25)
        if not topic:
            continue
        covered.setdefault(topic, lesson.date)
        covered_kinds.setdefault(topic, set()).add(lesson.kind)
    rows = syllabus_topic_rows(offering)
    if not rows:
        rows = [{"title": title, "kinds": (), "week": None} for title in _course_topic_titles(offering)]
    meta = [
        {
            "title": row["title"],
            "covered": row["title"] in covered,
            "date": covered.get(row["title"]),
            "kinds": list(row["kinds"]),
            "kinds_attr": " ".join(row["kinds"]),
            "covered_kinds": sorted(covered_kinds.get(row["title"], ())),
            "week": row.get("week"),
        }
        for row in rows
    ]
    return decorate_topic_choices(meta)


def decorate_topic_choices(rows) -> list:
    """Modal seçicisinin görünüşü (sahib 2026-10-25: «keçirilmiş mövzular səliqəli görünsün»).

    Hər sətrə ``next`` (keçirilməmiş və planlaşdırılmamış İLK mövzu — vurğulanır) və ``subtext`` (seçici
    menyusunda başlığın altındakı sönük sətir: dərs növləri + «✓ keçirilib 04.10» / «planlaşdırılıb» /
    «növbəti mövzu») qoyur. Başlıq (``title``) toxunulmur — seçimin dəyəri odur. ``covered`` dəyişən hər
    yerdən sonra (``journal_lesson_prefill.topics_covered_by``) yenidən çağırılır."""
    from django.utils.translation import pgettext

    labels = {
        "lecture": pgettext("registrar.journal", "mühazirə"),
        "seminar": pgettext("registrar.journal", "seminar"),
        "lab": pgettext("registrar.journal", "laboratoriya"),
    }
    next_index = next((i for i, row in enumerate(rows) if not row.get("covered") and not row.get("planned")), None)
    out = []
    for index, row in enumerate(rows):
        parts = [", ".join(labels[kind] for kind in row.get("kinds") or () if kind in labels)]
        date = row.get("date")
        stamp = f" {date:%d.%m}" if date else ""
        if row.get("covered"):
            parts.append("✓ " + pgettext("registrar.journal", "keçirilib") + stamp)
        elif row.get("planned"):
            parts.append(pgettext("registrar.journal", "planlaşdırılıb") + stamp)
        elif index == next_index:
            parts.append(pgettext("registrar.journal_topics", "növbəti mövzu"))
        out.append({**row, "next": index == next_index, "subtext": " · ".join(part for part in parts if part)})
    return out


__all__ = [
    "SYLLABUS_HOUR_KINDS",
    "attach_syllabus_topics",
    "decorate_topic_choices",
    "lesson_topic_choices",
    "lesson_topic_meta",
    "normalize_topic",
    "posted_topic",
    "resolve_syllabus_week",
    "shown_topic",
    "syllabus_topic_rows",
    "syllabus_week_rows",
    "week_progress",
]
