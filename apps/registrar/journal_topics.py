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

import re

from django.db.models import prefetch_related_objects

#: Sillabusun həftəlik cədvəlindəki saat növləri — jurnal ``LessonKind`` açarları
#: ilə EYNİ sətirlərdir (``apps.syllabus.constants.LESSON_HOUR_KINDS``).
SYLLABUS_HOUR_KINDS = ("lecture", "seminar", "lab")


#: Təkrar başlıqlı plan sətrinin seçim dəyəri: ``§<sətir>§<başlıq>`` (MR-000377, 2026-11-16). Başlığın İLK
#: sətrinin dəyəri təmiz başlıqdır (köhnə formalar, redaktə, «Aktivləşdir» dəyişmir); sonrakı sətirlər
#: menyuda ayrıca seçim olsun deyə sətir nömrəsi ilə işarələnir. Server ``posted_topic`` ilə başlığı,
#: ``posted_topic_week`` ilə sətri ayırır.
_WEEK_VALUE = re.compile(r"^§(\d{1,4})§(.*)$", re.DOTALL)


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


def _week_entry(index, entry, *, practical=False) -> dict:
    kinds = tuple(
        kind
        for kind in SYLLABUS_HOUR_KINDS
        if _positive(entry.get(kind)) or kind == "seminar" and practical and _positive(entry.get("practical"))
    )
    return {"week": index, "title": str(entry.get("topic") or "").strip(), "kinds": kinds}


def syllabus_week_rows(offering, *, plan_rows=None) -> list:
    """Həftəlik planın HƏR sətri nömrəsi ilə: ``[{"week": n, "title": str, "kinds": (…)}]``.

    ``week`` — ``Lesson.syllabus_week``-in semantikası: ``week.rows``-da 1-dən sıra, boş mövzulu sətirlər
    də sayılır (``title`` boş qalır). Yalnız ``APPROVED`` versiya; yoxdursa boş siyahı."""
    rows = _approved_plan_rows(offering) if plan_rows is None else plan_rows
    from .practical_label import offering_is_practical

    practical = offering_is_practical(offering)
    return [_week_entry(index, entry, practical=practical) for index, entry in enumerate(rows, start=1)]


def syllabus_topic_rows(offering):
    """TƏSDİQLƏNMİŞ sillabusun mövzu planı — mövzu bir dəfə, saat növ üzrə.

    Dizayn qaydası §8/0: «Sillabusun həftəlik planında mövzu BİR DƏFƏ yazılır,
    saat isə mühazirə / seminar / laboratoriya üzrə AYRICA saxlanılır.  Jurnalda
    həmin mövzu hər növ üçün ayrı dərs sətri kimi açılır — başlıq eynidir,
    ``kind`` fərqlidir.»

    Nəticə: ``[{"title": str, "kinds": (…), "week": n}]`` — başlığı dolu HƏR plan sətri. Planda təkrarlanan
    başlıq («Test», «Hauslektüre», «Teil D. Rückblick» — MR-000377, 2026-11-16) hər sətri üçün AYRICA gəlir:
    əvvəl başlığa görə birləşdirilirdi və ikinci «Test» ilk istifadədən sonra siyahıdan itirdi.
    Yalnız ``APPROVED`` versiya oxunur (§8/9 və §6.5) — qaralama versiyanın mövzuları jurnala sızmır.
    Sillabus yoxdursa BOŞ siyahı (çağıran LMS kursuna geri çəkilir).
    """
    return [
        {"title": entry["title"], "kinds": entry["kinds"], "week": entry["week"]}
        for entry in syllabus_week_rows(offering)
        if entry["title"]
    ]


def lesson_topic_rows(offering) -> list:
    """Modalın mövzu SƏTİRLƏRİ: təsdiqlənmiş plan, yoxdursa ehtiyat mənbə (``journal_topic_fallback``)."""
    rows = syllabus_topic_rows(offering)
    if rows:
        return rows
    from .journal_topic_fallback import fallback_topic_rows

    return fallback_topic_rows(offering)


def row_key(row):
    """Plan sətrinin açarı: sətir nömrəsi (``week``), nömrəsi olmayan ehtiyat mənbədə başlıq."""
    week = row.get("week")
    return ("week", week) if week else ("title", row["title"])


def lesson_row_matcher(rows):
    """Dərs → plan sətrinin açarı (``row_key``) və ya ``None``.

    Qayda ``week_progress`` ilə eynidir: ``Lesson.syllabus_week`` başlığı dolu sətrə bağlıdırsa O sətir;
    bağsız dərs başlığı (normallaşdırılmış) uyğun gələn İLK sətrə sayılır. Beləliklə təkrar başlığın hər sətri
    öz statusunu alır — ikinci «Test» birincinin dərsi ilə «keçirilib» görünmür."""
    weeks = {row["week"] for row in rows if row.get("week")}
    first: dict = {}
    for row in rows:
        first.setdefault(normalize_topic(row["title"]), row_key(row))

    def match(lesson):
        linked = getattr(lesson, "syllabus_week", None)
        if linked and linked in weeks:
            return ("week", linked)
        topic = shown_topic(lesson)
        return first.get(normalize_topic(topic)) if topic else None

    return match


def topic_choice_value(rows) -> list:
    """Hər sətrə seçim dəyəri (``value``) qoyur: başlığın ilk sətri — başlıq, təkrarı — ``§n§başlıq``."""
    seen = set()
    out = []
    for row in rows:
        title = row["title"]
        repeat = title in seen and row.get("week")
        seen.add(title)
        out.append({**row, "value": f"§{row['week']}§{title}" if repeat else title})
    return out


def add_coverage(covered: dict, lesson) -> None:
    """``next_topic`` üçün əhatə lüğətinə dərsi əlavə edir (``journal_activation.lesson_facts``).

    Açarlar: başlıq (köhnə, növsüz mənbə üçün), ``("week", n)`` — sətrə bağlı dərs, ``("free", başlıq)`` —
    bağsız dərs (başlığın İLK sətrinə sayılır). Dəyər — keçirilmiş dərs növləri."""
    topic = shown_topic(lesson)
    if topic:
        covered.setdefault(topic, set()).add(lesson.kind)
    week = getattr(lesson, "syllabus_week", None)
    if week:
        covered.setdefault(("week", week), set()).add(lesson.kind)
    elif topic:
        covered.setdefault(("free", normalize_topic(topic)), set()).add(lesson.kind)


def row_done_kinds(rows, covered: dict) -> list:
    """Hər sətrin keçirilmiş növləri (``add_coverage`` lüğətindən), ``rows`` ilə eyni sırada.

    Sətir nömrəsi olan sətir: ona bağlı dərslər + (başlığın İLK sətridirsə) bağsız dərslər. Nömrəsiz (köhnə,
    ehtiyat mənbə) sətir: başlığın bütün dərsləri."""
    first_seen: set = set()
    out = []
    for row in rows:
        week = row.get("week")
        if not week:
            out.append(set(covered.get(row["title"], ())))
            continue
        done = set(covered.get(("week", week), ()))
        key = normalize_topic(row["title"])
        if key not in first_seen:
            first_seen.add(key)
            done |= covered.get(("free", key), set())
        out.append(done)
    return out


def resolve_syllabus_week(offering, topic, *, current=None, week_rows=None, kind=None, taken=None):
    """Dərs mövzusunun bağlandığı plan sətri və ya ``None`` (uydurma bağ yoxdur).

    * mövzu ``current`` sətrinin başlığı ilə eynidirsə (normallaşdırılmış) — bağ QALIR (təkrar başlıq,
      modalda seçilmiş konkret sətir — ``posted_topic_week``);
    * əks halda başlığı DƏQİQ (boşluq/registr normallaşdırılmış) uyğun gələn sətirlərdən: ``kind`` verilibsə
      həmin növə saat verən sətirlər üstündür, ``taken`` (bu növün dərsi artıq olan sətirlər — çağırılan
      funksiya, yalnız başlıq təkrarlananda çağırılır) çıxılır və İLK boş sətir seçilir (MR-000377: ikinci
      «Test» dərsi ikinci «Test» sətrinə bağlanır); hamısı tutulubsa — uyğun İLK sətir;
    * uyğun sətir yoxdursa (sərbəst mətn) və ya mövzu boşdursa — ``None``."""
    key = normalize_topic(topic)
    if not key:
        return None
    rows = syllabus_week_rows(offering) if week_rows is None else week_rows
    matches = [row for row in rows if row["title"] and normalize_topic(row["title"]) == key]
    weeks = [row["week"] for row in matches]
    if current in weeks:
        return current
    if len(weeks) <= 1:
        return weeks[0] if weeks else None
    preferred = [row["week"] for row in matches if kind and kind in row["kinds"]] or weeks
    busy = set(taken(weeks)) if callable(taken) else set(taken or ())
    free = [week for week in preferred if week not in busy]
    return (free or preferred)[0]


def posted_topic(post):
    """Modalın mövzusu: sərbəst mətn (``lesson_topic_custom``) doludursa o, yoxdursa plan seçimi.

    ``None`` — sahə ümumiyyətlə göndərilməyib (redaktədə «dəyişmə»)."""
    custom = (post.get("lesson_topic_custom") or "").strip()
    if custom:
        return custom
    value = post.get("lesson_topic")
    match = _WEEK_VALUE.match(value or "")
    return match.group(2) if match else value


def posted_topic_week(post):
    """Modalda seçilmiş TƏKRAR başlıqlı plan sətrinin nömrəsi (``§n§başlıq`` dəyəri), yoxdursa ``None``."""
    if (post.get("lesson_topic_custom") or "").strip():
        return None
    match = _WEEK_VALUE.match(post.get("lesson_topic") or "")
    return int(match.group(1)) if match else None


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
            lesson._syllabus_topic = str(rows[index - 1].get("topic") or "").strip()
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
    """Yeni dərs modalındakı mövzu SİYAHISI (başlıqlar, plan sırası ilə — təkrar başlıq hər sətri üçün).

    MƏNBƏ SIRASI: (1) təsdiqlənmiş sillabusun həftəlik planı — README §6.5
    «Təsdiqlənmiş sillabus → jurnal strukturu yaranır»; (2) sillabus yoxdursa
    ehtiyat mənbə (LMS kursu, ``journal_topic_fallback``); (3) heç biri yoxdursa boş siyahı —
    şablon sərbəst mətn sahəsi göstərir.
    """
    return [row["title"] for row in lesson_topic_rows(offering)]


def lesson_topic_meta(offering, lessons):
    """Mövzu dropdown-u üçün: hər plan SƏTRİ + KEÇİRİLİB statusu (+ tarix) + DƏRS NÖVLƏRİ.

    ``kinds`` sillabusun həmin sətir üçün saat verdiyi növlərdir; modal seçilmiş
    dərs tipinə uyğun olmayan mövzuları gizlədir (§8/0).  Sillabus mənbəyi
    yoxdursa ``kinds`` BOŞ qalır və filtr tətbiq olunmur (köhnə davranış).

    «Keçirilib» bayrağı NÖV NƏZƏRƏ ALINMADAN hesablanır (sətrin ən azı bir
    dərsi keçilib), ``covered_kinds`` isə hansı növlərin bağlandığını göstərir.
    Dərs sətrə ``lesson_row_matcher`` ilə sayılır (``syllabus_week``, bağsız — başlığın ilk sətri);
    ``value`` — seçimin dəyəri (``topic_choice_value``).
    """
    rows = lesson_topic_rows(offering)
    # 2026-11-10 (sahib): təsdiqlənmiş sillabus yoxdursa mövzular ehtiyat mənbədən (LMS kursu → öz
    # təsdiqlənməmiş sillabusu → eyni fənnin təsdiqlənmiş sillabusu) — bax ``journal_topic_fallback``.
    match = lesson_row_matcher(rows)
    covered = {}
    covered_kinds = {}
    for lesson in lessons:
        key = match(lesson)  # mövzusuz, sillabus sətrinə bağlı dərs də sayılır (2026-10-25)
        if key is None:
            continue
        covered.setdefault(key, lesson.date)
        covered_kinds.setdefault(key, set()).add(lesson.kind)
    meta = [
        {
            "title": row["title"],
            "value": row["value"],
            "covered": row_key(row) in covered,
            "date": covered.get(row_key(row)),
            "kinds": list(row["kinds"]),
            "kinds_attr": " ".join(row["kinds"]),
            "covered_kinds": sorted(covered_kinds.get(row_key(row), ())),
            "week": row.get("week"),
            "fallback": bool(row.get("fallback")),
        }
        for row in topic_choice_value(rows)
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
    "add_coverage",
    "attach_syllabus_topics",
    "decorate_topic_choices",
    "lesson_row_matcher",
    "lesson_topic_choices",
    "lesson_topic_meta",
    "lesson_topic_rows",
    "normalize_topic",
    "posted_topic",
    "posted_topic_week",
    "resolve_syllabus_week",
    "row_done_kinds",
    "row_key",
    "shown_topic",
    "syllabus_topic_rows",
    "syllabus_week_rows",
    "topic_choice_value",
    "week_progress",
]
