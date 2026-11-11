"""«Keçilmiş dərslər» → «Cədvəl formasında bax»: bir müəllimin keçdiyi dərslərin icmal cədvəli (sahib 2026-11-11).

Bir sətir = (qrup və ya PATOK × fənn × dərs növü): «234 K, 234 İT · Proqramlaşdırma · mühazirə · 16 saat (8 dərs)».
Altda cəmlər: ümumi, növ üzrə (mühazirə / seminar / laboratoriya) və tədris dili (bölmə) üzrə (az / ing / rus).

PATOK NECƏ TANINIR (de-duplikasiya qaydası)
-------------------------------------------
Bu kod bazasında birgə (axın) dərsin dərs səviyyəsində AÇIQ bağı YOXDUR: ``Lesson`` həmişə BİR açılışa
(``CourseOffering`` = fənn × semestr × QRUP) aiddir, yəni iki qrupa birlikdə keçilən bir mühazirə iki jurnalda
İKİ ``Lesson`` sətridir. Açıq bağ yalnız dərs yükündədir (``TeachingTaskRow.patok_lead`` —
``apps/workload/services/patok.py``): o, PLANI (saat bölgüsünü) təsvir edir, keçilmiş dərsi yox, və köhnə
sistemdən gələn / yüksüz jurnallarda ümumiyyətlə yoxdur. Ona görə keçilmiş dərslər cədvəlin öz qaydası ilə
birləşdirilir (``schedule.is_joint_lecture`` — eyni müəllim + eyni fənn + EYNİ növ + eyni vaxt) və sahibin
2026-11-08 qərarı ilə («vaxtlar fərqlidirsə patok deyil, saatlar toplanır»):

    eyni (dərsi keçən müəllim, fənn, dərs növü, TARİX, BAŞLAMA SAATI), FƏRQLİ açılışlar  →  BİR dərs.

* **Müəllim** — dərsin öz ``instructor``-u, boşdursa açılışın müəllimi (bölmənin «Müəllim» filtri ilə eyni).
* **Fənn** — adın normallaşdırılmış forması (boşluq + registr): köhnə kataloqda eyni fənn ixtisas başına ayrı
  ``Subject`` sətri ola bilər; müəllim eyni anda eyni adlı iki fərqli dərs keçə bilməz.
* **Saatı yazılmamış dərs** (``start_time`` boş): MÜHAZİRƏ eyni gündə birgə sayılır (eyni mühazirəni bir gündə
  iki qrupa ayrı-ayrı oxumaq istisnadır), seminar / laboratoriya isə AYRI sayılır (eyni gündə hər qrupa ayrı
  məşğələ adi haldır) — saat yoxdursa müəllimin saatı azaldılmır.
* **Eyni jurnalın** iki dərsi heç vaxt birləşmir (qoşa dərs, Lab-1 / Lab-2 eyni saatda — hər biri ayrı dərsdir).
* Birgə dərsin saatı BİR dəfə sayılır (üzvlərin ``hours``-unun ən böyüyü, adətən 2 akademik saat).

Sətir = iştirakçı dəsti (açılış + lab / seminar alt qrupu) × fənn × növ: mühazirə «234 K, 234 İT» birgədirsə bir
sətir, seminar qrup başına keçilirsə iki ayrı sətir, laboratoriya alt qrupları («234 K · Lab-1») öz sətrində.

ƏHATƏ: giriş queryset-ləri çağıranın əhatəsindən (``lessons_log.scoped_lessons``) gəlir — nəzarətçi əhatəsindən
kənar qrupu (patokun o biri qrupu başqa fakültədədirsə) GÖRMÜR və o qrup sətirdə yazılmır.

SÜZGƏCLƏR: birgə dərs müəllimin dövrdəki BÜTÜN (əhatədəki) dərslərindən qurulur, sonra yalnız ən azı bir üzvü
bölmənin süzgəclərinə (qrup, fənn, növ, axtarış, fakültə …) uyğun gələn dərslər saxlanılır — «Qrup: 234 K»
süzgəci patokun adını «234 K, 234 İT»dən «234 K»ya qısaltmır.

Sorğu büdcəsi: dərslər 1 + süzgəc id-ləri 1 + (varsa) lab / seminar alt qrup adları 2; təfərrüatda əlavə olaraq
xana aqreqatı 1 + sillabus mövzuları ≤ 3. Sətir-sətir sorğu yoxdur.
"""

from __future__ import annotations

import hashlib

from django.utils.dates import WEEKDAYS
from django.utils.translation import pgettext

from apps.registrar.models import LessonKind

_CTX = "registrar.lessons_log"

KIND_ORDER = (LessonKind.LECTURE, LessonKind.SEMINAR, LessonKind.LAB)
#: Tədris dili bölmələrinin göstərilmə sırası; qalanı (naməlum kod) əlifba ilə, «qarışıq» ən sonda.
SECTOR_ORDER = ("az", "ing", "rus")
SECTOR_MIXED = "mixed"
#: Müəllimin bir dövrdə oxunan dərs tavanı (qoruyucu — real müəllimdə semestrdə bir neçə yüzdür).
LESSON_CAP = 5000


def _subject_key(subject) -> str:
    name = " ".join(str(getattr(subject, "name", "") or "").split()).casefold()
    return name or str(getattr(subject, "pk", ""))


def _sub_of(lesson):
    """Dərsin alt qrupu: ``("lab", n)`` / ``("seminar", n)`` / ``None`` (bütün qrup)."""
    if lesson.kind == LessonKind.LAB and lesson.lab_group:
        return ("lab", int(lesson.lab_group))
    if lesson.kind == LessonKind.SEMINAR and lesson.seminar_group:
        return ("seminar", int(lesson.seminar_group))
    return None


def _joint_key(lesson) -> tuple:
    """Birgə dərs açarı (modul sənədi «PATOK NECƏ TANINIR»); müəllim girişdə artıq sabitdir."""
    base = (_subject_key(lesson.offering.subject), lesson.kind, lesson.date)
    if lesson.start_time is not None:
        return (*base, lesson.start_time)
    if lesson.kind == LessonKind.LECTURE:
        return (*base, None)
    return (*base, None, lesson.pk)  # saatsız seminar / lab — heç nə ilə birləşmir


def build_events(lessons) -> list:
    """Dərs sətirlərindən BİRGƏ dərslər: ``[{"lessons": [Lesson…], "hours", "date", …}]`` (tarix sırası ilə).

    Eyni açarda eyni açılışın ikinci dərsi YENİ hadisə açır (eyni jurnalın dərsləri birləşmir)."""
    buckets: dict = {}
    for lesson in lessons:
        events = buckets.setdefault(_joint_key(lesson), [])
        for event in events:
            if lesson.offering_id not in event["offerings"]:
                event["lessons"].append(lesson)
                event["offerings"].add(lesson.offering_id)
                break
        else:
            events.append({"lessons": [lesson], "offerings": {lesson.offering_id}})
    out = []
    for events in buckets.values():
        for event in events:
            first = event["lessons"][0]
            members = sorted(event["lessons"], key=lambda item: (str(item.offering_id), str(item.pk)))
            out.append(
                {
                    "lessons": members,
                    "ids": [item.pk for item in members],
                    "date": first.date,
                    "start_time": first.start_time,
                    "end_time": next((item.end_time for item in members if item.end_time), None),
                    "kind": first.kind,
                    "hours": max(int(item.hours or 0) for item in members),
                    "subject": first.offering.subject,
                    "participants": tuple(
                        sorted((str(item.offering_id), _sub_of(item) or ("", 0)) for item in members)
                    ),
                }
            )
    out.sort(
        key=lambda event: (event["date"], event["start_time"] is None, event["start_time"] or 0, event["ids"][0].hex)
    )
    return out


def _row_key(event) -> str:
    raw = "|".join(
        [_subject_key(event["subject"]), str(event["kind"])]
        + [f"{offering}:{sub[0]}:{sub[1]}" for offering, sub in event["participants"]]
    )
    return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()[:20]


def _sub_names(events) -> dict:
    """``{("lab"|"seminar", açılış_id, n): ad}`` — yalnız alt qruplu dərs varsa, növ başına BİR sorğu."""
    from apps.registrar.models.lab_group import LabGroup
    from apps.registrar.models.seminar_group import SeminarGroup

    wanted: dict = {"lab": set(), "seminar": set()}
    for event in events:
        for lesson in event["lessons"]:
            sub = _sub_of(lesson)
            if sub is not None:
                wanted[sub[0]].add(lesson.offering_id)
    names: dict = {}
    for kind, model in (("lab", LabGroup), ("seminar", SeminarGroup)):
        if not wanted[kind]:
            continue
        for offering_id, number, name in model.objects.filter(offering_id__in=wanted[kind]).values_list(
            "offering_id", "number", "name"
        ):
            if name:
                names[(kind, offering_id, number)] = name
    return names


def _participant_label(lesson, names) -> str:
    from apps.registrar import lab_groups, seminar_groups

    group = getattr(lesson.offering, "group", None) if lesson.offering.group_id else None
    group_name = (getattr(group, "name", "") or "").strip()
    sub = _sub_of(lesson)
    if sub is None:
        return group_name or "—"
    named = names.get((sub[0], lesson.offering_id, sub[1]))
    if named:
        return named
    default = lab_groups.default_label(sub[1]) if sub[0] == "lab" else seminar_groups.default_label(sub[1])
    return f"{group_name} · {default}" if group_name else default


def _event_sector(event) -> str:
    from apps.registrar.syllabus_carry import group_language

    sectors = {
        group_language(lesson.offering.group) if lesson.offering.group_id else "" for lesson in event["lessons"]
    } - {""}
    if not sectors:
        return ""
    if len(sectors) == 1:
        return next(iter(sectors))
    # Sahib 2026-11-11: az + ing qrupların birgə patoku İNGİLİS bölməsinə sayılır («ing sayılsın»).
    if "ing" in sectors:
        return "ing"
    return SECTOR_MIXED


def sector_label(code: str) -> str:
    labels = {
        "az": pgettext(_CTX, "Azərbaycan bölməsi"),
        "ing": pgettext(_CTX, "İngilis bölməsi"),
        "rus": pgettext(_CTX, "Rus bölməsi"),
        SECTOR_MIXED: pgettext(_CTX, "Qarışıq bölmə (birgə dərs)"),
        "": pgettext(_CTX, "Bölməsi göstərilməyib"),
    }
    return labels.get(code) or code.upper()


def kind_label(kind) -> str:
    try:
        return str(LessonKind(kind).label)
    except ValueError:
        return str(kind)


def hours_text(hours, lessons) -> str:
    """«16 saat (8 dərs)» — sahibin istədiyi yazılış."""
    return pgettext(_CTX, "%(hours)s saat (%(lessons)s dərs)") % {"hours": hours, "lessons": lessons}


def _bump(bucket: dict, key, hours) -> None:
    entry = bucket.setdefault(key, {"lessons": 0, "hours": 0})
    entry["lessons"] += 1
    entry["hours"] += hours


def _totals(pairs, label_of, order) -> list:
    def rank(code):
        return (order.index(code) if code in order else len(order), code == SECTOR_MIXED, str(code))

    return [
        {
            "key": str(code),
            "label": label_of(code),
            "lessons": entry["lessons"],
            "hours": entry["hours"],
            "text": hours_text(entry["hours"], entry["lessons"]),
        }
        for code, entry in sorted(pairs.items(), key=lambda item: rank(item[0]))
    ]


def load_events(base_qs, *, matched_qs=None) -> list:
    """Müəllimin (əhatə + dövr) dərslərindən birgə dərslər; ``matched_qs`` verilibsə yalnız ona toxunanlar."""
    lessons = list(
        base_qs.select_related(
            "offering", "offering__subject", "offering__subject__chair_unit", "offering__group", "room"
        ).order_by("date", "start_time", "created_at")[:LESSON_CAP]
    )
    from apps.registrar import design_practical_scope

    # «Praktiki məşğələ» etiketi sətir-sətir sorğu etməsin (bax `lessons_log.build_rows`).
    design_practical_scope.prime(lesson.offering for lesson in lessons if lesson.kind == LessonKind.SEMINAR)
    events = build_events(lessons)
    if matched_qs is not None:
        matched = set(matched_qs.order_by().values_list("id", flat=True)[:LESSON_CAP])
        events = [event for event in events if any(pk in matched for pk in event["ids"])]
    return events


def summarise(events) -> dict:
    """Hadisələrdən cədvəl: ``{"rows": […], "totals": {…}}`` (hadisələr hər sətrin ``events``-indədir)."""
    names = _sub_names(events)
    rows: dict = {}
    by_kind: dict = {}
    by_sector: dict = {}
    total = {"lessons": 0, "hours": 0}
    for event in events:
        key = _row_key(event)
        row = rows.get(key)
        if row is None:
            first = event["lessons"][0]
            labels = sorted(
                {_participant_label(lesson, names) for lesson in event["lessons"]}, key=lambda text: text.casefold()
            )
            sector = _event_sector(event)
            row = {
                "key": key,
                "groups": ", ".join(labels),
                "group_names": labels,
                "is_joint": len(event["lessons"]) > 1,
                "subject": getattr(event["subject"], "name", "") or "",
                "subject_code": getattr(event["subject"], "code", "") or "",
                "kind": str(event["kind"]),
                "kind_label": str(first.get_kind_display()),
                "sector": sector,
                "sector_label": sector_label(sector),
                "lessons": 0,
                "hours": 0,
                "events": [],
            }
            rows[key] = row
        row["lessons"] += 1
        row["hours"] += event["hours"]
        row["events"].append(event)
        total["lessons"] += 1
        total["hours"] += event["hours"]
        _bump(by_kind, str(event["kind"]), event["hours"])
        _bump(by_sector, row["sector"], event["hours"])
    kind_rank = {str(kind): index for index, kind in enumerate(KIND_ORDER)}
    ordered = sorted(
        rows.values(),
        key=lambda row: (row["subject"].casefold(), kind_rank.get(row["kind"], 9), row["groups"].casefold()),
    )
    for row in ordered:
        row["text"] = hours_text(row["hours"], row["lessons"])
    return {
        "rows": ordered,
        "totals": {
            "lessons": total["lessons"],
            "hours": total["hours"],
            "text": hours_text(total["hours"], total["lessons"]),
            "by_kind": _totals(by_kind, kind_label, [str(kind) for kind in KIND_ORDER]),
            "by_sector": _totals(by_sector, sector_label, list(SECTOR_ORDER)),
        },
    }


def _room_label(room) -> str:
    if room is None:
        return ""
    name = (getattr(room, "name", "") or "").strip()
    building = (getattr(room, "building", "") or "").strip()
    return f"{name} ({building})" if name and building else name or building


def event_details(row_or_rows) -> list:
    """Sətrin (və ya bütün sətirlərin) dərsləri təfərrüatı ilə: tarix, gün, saat, mövzu, otaq, iştirak.

    Mövzu: yazılmış ``topic``, yoxdursa bağlı sillabus sətri (``journal_topics.attach_syllabus_topics`` — toplu).
    İştirak birgə dərsdə bütün qrupların cəmidir («iştirak / qeyd olunan»)."""
    from apps.registrar.journal_topics import attach_syllabus_topics
    from apps.registrar.lessons_log import marks_by_lesson

    rows = row_or_rows if isinstance(row_or_rows, list) else [row_or_rows]
    lessons = [lesson for row in rows for event in row["events"] for lesson in event["lessons"]]
    attach_syllabus_topics(lessons)
    stats = marks_by_lesson([lesson.pk for lesson in lessons])
    out = []
    for row in rows:
        for event in row["events"]:
            members = event["lessons"]
            present = sum(int(stats.get(lesson.pk, {}).get("present") or 0) for lesson in members)
            marked = sum(int(stats.get(lesson.pk, {}).get("total") or 0) for lesson in members)
            topics = []
            for lesson in members:
                topic = (lesson.display_topic or "").strip()
                if topic and topic not in topics:
                    topics.append(topic)
            rooms = []
            for lesson in members:
                room = _room_label(lesson.room) if lesson.room_id else ""
                if room and room not in rooms:
                    rooms.append(room)
            start, end = event["start_time"], event["end_time"]
            time_text = start.strftime("%H:%M") if start else ""
            if start and end:
                time_text = f"{time_text} – {end.strftime('%H:%M')}"
            out.append(
                {
                    "row": row["key"],
                    "date": event["date"].isoformat(),
                    "date_text": event["date"].strftime("%d.%m.%Y"),
                    "weekday": str(WEEKDAYS[event["date"].weekday()]),
                    "time": time_text,
                    "hours": event["hours"],
                    "kind": row["kind"],
                    "kind_label": row["kind_label"],
                    "groups": row["groups"],
                    "subject": row["subject"],
                    "topic": " / ".join(topics),
                    "room": ", ".join(rooms),
                    "present": present,
                    "marked": marked,
                    "attendance": f"{present} / {marked}" if marked else "",
                    "off_schedule": next(
                        (lesson.off_schedule_reason for lesson in members if lesson.off_schedule_reason), ""
                    ),
                }
            )
    return out


def public_rows(table) -> list:
    """JSON üçün sətirlər (daxili ``events`` siyahısı olmadan)."""
    return [{key: value for key, value in row.items() if key != "events"} for row in table["rows"]]


def teacher_in_scope(lessons_all, teacher_id) -> bool:
    """Müəllimin baxanın ƏHATƏSİNDƏ ən azı bir dərsi varmı (hər hansı dövrdə) — əhatə qapısı."""
    from apps.registrar.lessons_log_request import teacher_q

    return lessons_all.filter(teacher_q(teacher_id)).exists()


__all__ = [
    "KIND_ORDER",
    "LESSON_CAP",
    "SECTOR_MIXED",
    "SECTOR_ORDER",
    "build_events",
    "event_details",
    "hours_text",
    "kind_label",
    "load_events",
    "public_rows",
    "sector_label",
    "summarise",
    "teacher_in_scope",
]
