"""Cədvəl redaktoru — «Uyğun vaxtlar» şəbəkəsi + otaq tövsiyəsi (YALNIZ OXU, SERVER AVTORİTETDİR).

──────────────────────────────────────────────────────────────────────────────
SAHİBİN TƏLƏBİ (2026-10-17)
──────────────────────────────────────────────────────────────────────────────
«Cədvəl yaradarkən otaq tövsiyəsi də et. Burda həm müəllimin, həm də qrupun ortaq vaxtı
görünsün, ya da seçim olsun ki müəllim üçün uyğun / qrup üçün uyğun vaxt — sistem təkliflər
verə bilsin. Bir də qrupdakı uşaq sayı limitinə görə də otaq təklifi dəyişsin. Bir də korpus
məsələsi var.»

NƏ QAYTARIR (:func:`plan`)
--------------------------
* ``cells`` — gün × nömrələnmiş dərs saatı şəbəkəsi; hər xananın statusu:
  ``free`` (ortaq boş), ``room`` (müəllim + qrup boş, amma otaq problemi), ``teacher``
  (müəllim məşğul), ``group`` (qrup məşğul), ``both`` (hər ikisi məşğul) + səbəb mətnləri;
* ``mode`` — «Hər ikisi üçün» (defolt) / «Müəllim üçün» / «Qrup üçün»: hansı xanaların
  TƏKLİF olunduğunu dəyişir (``suggested``);
* ``top`` — sıralanmış qısa siyahı (yığcam gün, boşluqsuz, qrupun növbəsi — bax :func:`_rank_key`);
* ``rooms`` — seçilmiş gün + saat üçün BOŞ otaqlar: tutum ≥ qrup sayı (ən kiçik uyğun əvvəl),
  qrupun korpusu əvvəl, laboratoriya dərsinə laboratoriya; kiçik otaq xəbərdarlıqla sonda.

TOQQUŞMA QAYDALARI TƏKRARLANMIR
-------------------------------
Müəllim/qrup məşğulluğu :func:`apps.registrar.schedule_conflicts.detect` ilə hesablanır — eyni
semestr süzgəci, üst/alt həftə pariteti, axın (birləşmiş mühazirə) və paralel alt qrup qaydası.
Ona görə «boş» göstərilən xana saxlamada toqquşma VERMİR (otaq sütunu ayrıca yoxlanır).
Əhatədən kənar dərsin səbəbi minimal açıqlama ilə gəlir (``visible``).

SƏMƏRƏLİLİK
-----------
Qrupun/müəllimin canlı slotları BİR sorğu ilə (tam obyekt), semestrin otaq məşğulluğu bir yüngül
``values_list`` sorğusu ilə (PERF-1 F-07), otaqlar bir, qrup sayları iki aqreqat sorğu ilə gəlir;
qalan hər şey Python-dadır (48 xana × yalnız müəllim/qrupa aid slotlar).

OTAQ = MƏTN
-----------
``ScheduleSlot.room`` sərbəst mətndir (``exams.ExamRoom`` reyestrinin adı və ya kodu yazılır);
otaq məşğulluğu ``detect`` ilə eyni normallaşdırma ilə (kiçik hərf, kənar boşluqsuz) müqayisə olunur.
"""

from __future__ import annotations

from collections import Counter

from django.db.models import Count
from django.utils.translation import pgettext, pgettext_lazy

from apps.registrar import campus, schedule_conflicts, schedule_grid
from apps.registrar.models import AcademicStatus, Enrollment, SlotKind, StudentAcademicRecord, WeekType
from apps.registrar.schedule import effective_instructor_id, is_joint_lecture, same_id

_CTX = "registrar.schedule_suggest"

MODE_BOTH = "both"
MODE_TEACHER = "teacher"
MODE_GROUP = "group"
MODES = (MODE_BOTH, MODE_TEACHER, MODE_GROUP)

STATUS_FREE = "free"
STATUS_ROOM = "room"
STATUS_TEACHER = "teacher"
STATUS_GROUP = "group"
STATUS_BOTH = "both"

#: Qısa siyahıda və otaq siyahısında göstərilən sətir sayı.
TOP_LIMIT = 6
ROOM_LIMIT = 12
#: Gündə bu qədər (və çox) dərs varsa həmin gün «yüklü» sayılır — ora əlavə təklif sonra gəlir.
DAY_OVERLOAD = 4

SHORT_DAYS = {
    1: pgettext_lazy(_CTX, "B.e."),
    2: pgettext_lazy(_CTX, "Ç.a."),
    3: pgettext_lazy(_CTX, "Ç."),
    4: pgettext_lazy(_CTX, "C.a."),
    5: pgettext_lazy(_CTX, "C."),
    6: pgettext_lazy(_CTX, "Ş."),
    7: pgettext_lazy(_CTX, "B."),
}


def _norm(text) -> str:
    """Otaq mətni — ``schedule_conflicts.detect`` ilə EYNİ normallaşdırma."""
    return (text or "").strip().lower()


def _overlaps(slot, weekday, start, end, week_type) -> bool:
    return (
        slot.weekday == weekday
        and schedule_conflicts.time_ranges_overlap(start, end, slot.start_time, slot.end_time)
        and schedule_conflicts.week_types_overlap(week_type, slot.week_type)
    )


# ── Qrup sayı ────────────────────────────────────────────────────────────────


def group_sizes(organization, group_ids, offering_ids=()) -> dict:
    """Qrup → aktiv tələbə sayı: akademik qeydlər (``enrolled``) və ya açılışın aktiv qeydiyyatları.

    İkisindən BÖYÜYÜ götürülür: alt qrupa bölünmüş qrupun tələbələri alt qrupda otura bilər və
    jurnala qonaq qeydiyyatla düşür (``subgroup_rollup``) — o halda qeyd sayı 0, qeydiyyat sayı
    real olur. İki aqreqat sorğu, nəticə ``{str(group_id): n}``."""
    ids = [gid for gid in group_ids if gid]
    sizes = {str(gid): 0 for gid in ids}
    if not ids:
        return sizes
    records = (
        StudentAcademicRecord.objects.filter(
            organization=organization, group_id__in=ids, status=AcademicStatus.ENROLLED
        )
        .values("group_id")
        .annotate(n=Count("id"))
    )
    for row in records:
        sizes[str(row["group_id"])] = max(sizes.get(str(row["group_id"]), 0), row["n"])
    offering_ids = [oid for oid in offering_ids if oid]
    if offering_ids:
        enrolled = (
            Enrollment.objects.filter(
                organization=organization, offering_id__in=offering_ids, status=Enrollment.Status.ENROLLED
            )
            .values("offering__group_id")
            .annotate(n=Count("id"))
        )
        for row in enrolled:
            key = str(row["offering__group_id"])
            sizes[key] = max(sizes.get(key, 0), row["n"])
    return sizes


# ── Otaqlar ──────────────────────────────────────────────────────────────────


def load_rooms(organization) -> list[dict]:
    """Təşkilatın aktiv otaqları (``exams.ExamRoom`` — REVERSE accessor, registrar → exams idxalı yox)."""
    rows = organization.exam_rooms.filter(is_active=True).order_by("building", "name", "code")
    out = []
    for room in rows.values("pk", "name", "code", "building", "capacity", "computer_count", "notes"):
        label = (room["name"] or "").strip() or (room["code"] or "").strip()
        if not label:
            continue
        kind_text = campus.normalize_unit_name(f"{room['notes'] or ''} {room['name'] or ''}")
        out.append(
            {
                "id": str(room["pk"]),
                "label": label[:64],
                "building": (room["building"] or "").strip(),
                "capacity": int(room["capacity"] or 0),
                "is_lab": bool(room["computer_count"]) or "laborator" in kind_text,
                "keys": {key for key in (_norm(room["name"]), _norm(room["code"])) if key},
            }
        )
    return out


def _busy_rooms(rows, weekday, start, end, week_type, *, partner_ids=()) -> set:
    """Bu vaxtda tutulan otaq mətnləri — axın yoldaşlarının otağı BİZİMDİR (məşğul sayılmır)."""
    skip = {str(pk) for pk in partner_ids}
    return {
        _norm(slot.room)
        for slot in rows
        if slot.room and str(slot.pk) not in skip and _overlaps(slot, weekday, start, end, week_type)
    }


def _room_fits(room, size):
    """``True`` — sığır, ``False`` — kiçikdir, ``None`` — tutum və ya qrup sayı məlum deyil."""
    if not room["capacity"] or not size:
        return None
    return room["capacity"] >= size


def rank_rooms(rooms, *, busy, size, building="", kind=SlotKind.LECTURE, current="", limit=ROOM_LIMIT) -> dict:
    """Boş otaqları sırala: kiçik otaq sonda → qrupun korpusu → dərs növü (lab) → tutum məlum → ən kiçik uyğun.

    Sıralama açarı (kiçik = yaxşı): ``(kiçikdir, başqa korpus, növ uyğunsuz, tutum naməlum, tutum, ad)``.
    Laboratoriya dərsinə laboratoriya əvvəl; mühazirə/məşğələyə isə adi otaq əvvəl (laboratoriyalar
    laboratoriya dərsləri üçün qalsın)."""
    home = campus.normalize_unit_name(building)
    want_lab = kind == SlotKind.LAB
    capacity_known = any(room["capacity"] for room in rooms)
    candidates = []
    for room in rooms:
        if room["keys"] & busy:
            continue
        fits = _room_fits(room, size)
        same = bool(home) and campus.normalize_unit_name(room["building"]) == home
        key = (
            fits is False,
            bool(home) and not same,
            room["is_lab"] != want_lab,
            fits is None,
            room["capacity"] if fits else -room["capacity"],
            room["label"].lower(),
        )
        candidates.append((key, room, fits, same))
    candidates.sort(key=lambda item: item[0])
    small = sum(1 for _key, _room, fits, _same in candidates if fits is False)
    current_norm = _norm(current)
    rows = [
        {
            "id": room["id"],
            "label": room["label"],
            "building": room["building"],
            "capacity": room["capacity"],
            "fits": fits,
            "same_campus": same,
            "is_lab": room["is_lab"],
            "is_current": bool(current_norm) and current_norm in room["keys"],
        }
        for _key, room, fits, same in candidates[: max(1, int(limit or ROOM_LIMIT))]
    ]
    return {
        "rows": rows,
        "free_total": len(candidates),
        "fitting": sum(1 for _key, _room, fits, _same in candidates if fits is not False),
        "small": small,
        "capacity_known": capacity_known,
        "registry_empty": not rooms,
    }


# ── Şəbəkə ───────────────────────────────────────────────────────────────────


class _Plan:
    """Bir sorğunun girişləri + bir dəfə yüklənmiş slot dəsti (xanalar arasında paylaşılır)."""

    def __init__(
        self, *, organization, group, teacher_id, period_id, subject_id, kind, week_type, offering_id, exclude
    ):
        self.organization = organization
        self.group = group
        self.group_id = getattr(group, "pk", None)
        self.teacher_id = teacher_id or None
        self.period_id = period_id
        self.subject_id = subject_id or None
        self.kind = kind if kind in dict(SlotKind.choices) else SlotKind.LECTURE
        self.week_type = week_type if week_type in dict(WeekType.choices) else WeekType.ALL
        self.offering_id = offering_id
        self.exclude = tuple(str(pk) for pk in exclude if pk)
        # PERF-1 F-07 (2026-10-17): tam obyekt YALNIZ qrupun/müəllimin slotları üçün; otaq
        # məşğulluğu bütün semestrdən yüngül ``values_list`` sətirləri ilə (iki sorğu).
        mine = schedule_conflicts.owner_slots(
            organization, period_id=period_id, group_id=self.group_id, instructor_id=self.teacher_id
        )
        self.mine = [slot for slot in mine if str(slot.pk) not in self.exclude]
        self.room_rows: dict = {}
        for slot in schedule_conflicts.room_rows(organization, period_id=period_id, exclude_ids=self.exclude):
            self.room_rows.setdefault(slot.weekday, []).append(slot)

    def busy_rooms(self, weekday, start, end, partners) -> set:
        return _busy_rooms(
            self.room_rows.get(weekday, ()), weekday, start, end, self.week_type, partner_ids=[s.pk for s in partners]
        )

    def is_group(self, slot) -> bool:
        return same_id(self.group_id, slot.offering.group_id)

    def is_teacher(self, slot) -> bool:
        return same_id(self.teacher_id, effective_instructor_id(slot))

    def clashes(self, weekday, period, visible):
        return schedule_conflicts.detect(
            organization=self.organization,
            weekday=weekday,
            start_time=period["start"],
            end_time=period["end"],
            week_type=self.week_type,
            group_id=self.group_id,
            instructor_id=self.teacher_id,
            exclude_ids=self.exclude,
            candidates=self.mine,
            period_id=self.period_id,
            subject_id=self.subject_id,
            kind=self.kind,
            offering_id=self.offering_id,
            visible=visible,
        )

    def partners(self, weekday, start, end):
        """Axın yoldaşları: eyni müəllim + fənn, hər ikisi mühazirə, BAŞQA qrup (``is_joint_lecture``)."""
        return [
            slot
            for slot in self.mine
            if not self.is_group(slot)
            and _overlaps(slot, weekday, start, end, self.week_type)
            and is_joint_lecture(
                kind=self.kind, subject_id=self.subject_id, teacher_id=self.teacher_id, room="", slot=slot
            )
        ]

    def day_lessons(self, owner) -> dict:
        """Gün → sahibin (qrup / müəllim) dərs saatlarının nömrələri (pariteti fərq etmədən)."""
        test = self.is_group if owner == MODE_GROUP else self.is_teacher
        periods = schedule_grid.lesson_periods(self.organization)
        out: dict = {}
        for slot in self.mine:
            if not test(slot):
                continue
            for row in periods:
                if schedule_conflicts.time_ranges_overlap(row["start"], row["end"], slot.start_time, slot.end_time):
                    out.setdefault(slot.weekday, set()).add(row["no"])
        return out

    def dominant_shift(self) -> str:
        shifts = Counter(schedule_grid.shift_of(slot.start_time) for slot in self.mine if self.is_group(slot))
        return shifts.most_common(1)[0][0] if shifts else ""


def _status(teacher_busy, group_busy, room_issue) -> str:
    if teacher_busy and group_busy:
        return STATUS_BOTH
    if teacher_busy:
        return STATUS_TEACHER
    if group_busy:
        return STATUS_GROUP
    return STATUS_ROOM if room_issue else STATUS_FREE


def _suggested(mode, status) -> bool:
    if mode == MODE_TEACHER:
        return status in (STATUS_FREE, STATUS_ROOM, STATUS_GROUP)
    if mode == MODE_GROUP:
        return status in (STATUS_FREE, STATUS_ROOM, STATUS_TEACHER)
    return status in (STATUS_FREE, STATUS_ROOM)


def _day_cost(numbers, no):
    """``(xərc, növ)`` — 0 bitişik/eyni saat, N saat boşluq = N, yeni gün = 2."""
    if not numbers:
        return 2, "new"
    distance = min(abs(no - other) for other in numbers)
    if distance == 0:
        return 0, "pair"
    if distance == 1:
        return 0, "adjacent"
    return distance - 1, "gap"


def _day_note(owner, kind, gap) -> str:
    if owner == MODE_TEACHER:
        notes = {
            "new": pgettext(_CTX, "Müəllimin bu gün dərsi yoxdur"),
            "adjacent": pgettext(_CTX, "Müəllimin dərsinə bitişik"),
            "pair": pgettext(_CTX, "Müəllimin digər həftədəki dərsi ilə eyni saat"),
            "gap": pgettext(_CTX, "Müəllimin dərsləri arasında %(gap)s saat boşluq"),
        }
    else:
        notes = {
            "new": pgettext(_CTX, "Qrupun bu gün dərsi yoxdur — yeni gün"),
            "adjacent": pgettext(_CTX, "Qrupun dərsinə bitişik — boşluq yoxdur"),
            "pair": pgettext(_CTX, "Qrupun digər həftədəki dərsi ilə eyni saat"),
            "gap": pgettext(_CTX, "Qrupun dərsləri arasında %(gap)s saat boşluq"),
        }
    return notes[kind] % {"gap": gap} if kind == "gap" else notes[kind]


def _rank_key(cell, *, days, other_days, shift):
    """Kiçik = yaxşı: otaq problemi yox → qrupun növbəsi → yüklü gün deyil → yığcam gün (boşluqsuz) → erkən saat."""
    primary = days.get(cell["weekday"], set())
    cost, _kind = _day_cost(primary, cell["lesson_no"])
    other_cost, _other = _day_cost(other_days.get(cell["weekday"], set()), cell["lesson_no"])
    return (
        {STATUS_FREE: 0, STATUS_ROOM: 1}.get(cell["status"], 2),
        bool(shift) and cell["shift"] != shift,
        len(primary) >= DAY_OVERLOAD,
        cost,
        other_cost,
        cell["lesson_no"],
        cell["weekday"],
    )


def _room_issue(context, rooms, sizes, *, weekday, period, room, building):
    """Müəllim + qrup boş olan xananın OTAQ problemi (mətn) və ``building`` daxilində uyğun boş otaq sayı."""
    partners = context.partners(weekday, period["start"], period["end"])
    busy = context.busy_rooms(weekday, period["start"], period["end"], partners)
    stream_room = next((slot.room for slot in partners if slot.room), "")
    if room and stream_room and _norm(room) != _norm(stream_room):
        return (
            pgettext(_CTX, "Axın mühazirəsi %(room)s otağındadır — eyni otaq seçilməlidir.") % {"room": stream_room},
            0,
        )
    if room and _norm(room) in busy:
        return pgettext(_CTX, "%(room)s otağı bu saatda tutulub.") % {"room": room}, 0
    size = _joint_size(context, sizes, partners)
    home = campus.normalize_unit_name(building)
    free = [
        r
        for r in rooms
        if not (r["keys"] & busy)
        and _room_fits(r, size) is not False
        and (not home or campus.normalize_unit_name(r["building"]) == home)
    ]
    if rooms and not room and not stream_room and not free:
        return pgettext(_CTX, "Bu saatda qrupa uyğun boş otaq yoxdur."), 0
    return "", len(free)


def _joint_size(context, sizes, partners) -> int:
    own = sizes.get(str(context.group_id), 0)
    seen = {str(context.group_id)}
    total = own
    for slot in partners:
        key = str(slot.offering.group_id)
        if key not in seen:
            seen.add(key)
            total += sizes.get(key, 0)
    return total


def scope_visible(actor, organization):
    """Toqquşan dərsin redaktorun əhatəsində olub-olmadığı — BİR sorğu (əhatə qruplarının id-ləri).

    ``schedule_editor.scope_filter``-in toplu forması: 48 xana × onlarla açılış üçün hər açılışa
    ayrıca icazə sorğusu getməsin. Fail-closed: əhatə qrupu deyilsə səbəb minimal açıqlama ilə gəlir."""
    if actor is None:
        return None
    from apps.registrar import schedule_manage

    ids = {str(pk) for pk in schedule_manage.scoped_groups(actor, organization).values_list("pk", flat=True)}
    return lambda slot: str(slot.offering.group_id) in ids


def plan(
    *,
    organization,
    group,
    period_id,
    teacher_id=None,
    subject_id=None,
    kind=SlotKind.LECTURE,
    week_type=WeekType.ALL,
    offering_id=None,
    exclude_ids=(),
    mode=MODE_BOTH,
    weekday=None,
    time_slot="",
    room="",
    building="",
    visible=None,
) -> dict:
    """«Uyğun vaxtlar» paneli + seçilmiş vaxt üçün otaq tövsiyəsi (bax modul başlığı).

    ``building`` — dialoqda SEÇİLMİŞ korpus (boşdursa qrupun korpusu): otaqlar ona görə sıralanır."""
    mode = mode if mode in MODES else MODE_BOTH
    context = _Plan(
        organization=organization,
        group=group,
        teacher_id=teacher_id,
        period_id=period_id,
        subject_id=subject_id,
        kind=kind,
        week_type=week_type,
        offering_id=offering_id,
        exclude=exclude_ids,
    )
    periods = schedule_grid.lesson_periods(organization)
    rooms = load_rooms(organization)
    buildings = sorted({row["building"] for row in rooms if row["building"]})
    home = campus.default_building_for_group(organization, group)
    home = campus.match_building(buildings, home) or home
    building = campus.match_building(buildings, building) or home
    partner_offerings = {slot.offering_id for slot in context.mine if not context.is_group(slot)}
    group_ids = {context.group_id} | {slot.offering.group_id for slot in context.mine if not context.is_group(slot)}
    sizes = group_sizes(organization, group_ids, {offering_id, *partner_offerings})

    cells = []
    for day, _label in schedule_grid.TEACHING_WEEKDAYS:
        for period in periods:
            found = context.clashes(day, period, visible)
            teacher_busy = any(row["kind"] == schedule_conflicts.KIND_TEACHER for row in found)
            group_busy = any(row["kind"] == schedule_conflicts.KIND_GROUP for row in found)
            issue, free_rooms = ("", 0)
            if not teacher_busy and not group_busy:
                issue, free_rooms = _room_issue(
                    context, rooms, sizes, weekday=day, period=period, room=room, building=building
                )
            status = _status(teacher_busy, group_busy, issue)
            cells.append(
                {
                    "weekday": day,
                    "lesson_no": period["no"],
                    "time_slot": period["key"],
                    "shift": period["shift"],
                    "status": status,
                    "suggested": _suggested(mode, status),
                    "reasons": [row["message"] for row in found] + ([issue] if issue else []),
                    "free_rooms": free_rooms,
                }
            )

    owner = MODE_TEACHER if mode == MODE_TEACHER else MODE_GROUP
    days = context.day_lessons(owner)
    other_days = context.day_lessons(MODE_GROUP if owner == MODE_TEACHER else MODE_TEACHER)
    shift = context.dominant_shift()
    ranked = sorted(
        (cell for cell in cells if cell["suggested"]),
        key=lambda cell: _rank_key(cell, days=days, other_days=other_days, shift=shift),
    )
    by_no = {row["no"]: row for row in periods}
    labels = dict(schedule_grid.TEACHING_WEEKDAYS)
    top = []
    for rank, cell in enumerate(ranked[:TOP_LIMIT], start=1):
        cell["rank"] = rank
        period = by_no[cell["lesson_no"]]
        cost, kind_ = _day_cost(days.get(cell["weekday"], set()), cell["lesson_no"])
        top.append(
            {
                "weekday": cell["weekday"],
                "weekday_label": str(labels.get(cell["weekday"], "")),
                "time_slot": cell["time_slot"],
                "start_time": period["start_text"],
                "end_time": period["end_text"],
                "status": cell["status"],
                "note": _day_note(owner, kind_, cost),
                "shift_label": str(schedule_grid.SHIFT_LABELS.get(cell["shift"], "")),
            }
        )

    return {
        "mode": mode,
        "week_type": context.week_type,
        "has_teacher": bool(context.teacher_id),
        "days": [
            {"weekday": num, "label": str(label), "short": str(SHORT_DAYS.get(num, label))}
            for num, label in schedule_grid.TEACHING_WEEKDAYS
        ],
        "periods": [
            {"no": row["no"], "key": row["key"], "start_time": row["start_text"], "end_time": row["end_text"]}
            for row in periods
        ],
        "cells": cells,
        "top": top,
        "campus": home,
        "campus_selected": building,
        "group_size": sizes.get(str(context.group_id), 0),
        "rooms": _rooms_for_time(context, rooms, sizes, periods, weekday, time_slot, room, building),
    }


def _rooms_for_time(context, rooms, sizes, periods, weekday, time_slot, room, building):
    """Seçilmiş gün + saat üçün otaq tövsiyəsi — vaxt seçilməyibsə ``None``."""
    period = next((row for row in periods if row["key"] == time_slot), None)
    try:
        weekday = int(weekday or 0)
    except (TypeError, ValueError):
        weekday = 0
    if period is None or not 1 <= weekday <= 7:
        return None
    partners = context.partners(weekday, period["start"], period["end"])
    busy = context.busy_rooms(weekday, period["start"], period["end"], partners)
    size = _joint_size(context, sizes, partners)
    ranked = rank_rooms(rooms, busy=busy, size=size, building=building, kind=context.kind, current=room)
    joint = sorted({slot.offering.group.name for slot in partners if slot.offering.group_id})
    ranked.update(
        {
            "weekday": weekday,
            "time_slot": period["key"],
            "size": size,
            "joint_groups": joint,
            "stream_room": next((slot.room for slot in partners if slot.room), ""),
            "current_busy": bool(room) and _norm(room) in busy,
        }
    )
    return ranked


__all__ = [
    "MODES",
    "MODE_BOTH",
    "MODE_GROUP",
    "MODE_TEACHER",
    "STATUS_BOTH",
    "STATUS_FREE",
    "STATUS_GROUP",
    "STATUS_ROOM",
    "STATUS_TEACHER",
    "group_sizes",
    "load_rooms",
    "plan",
    "rank_rooms",
    "scope_visible",
]
