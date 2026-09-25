"""Canlı kontekst — dərc olunmuş slotlar, otaqlar, müəllim əlçatanlığı (YALNIZ OXU).

Dərc olunmuş (``ScheduleSlot``, parklanmamış, silinməmiş) eyni semestr slotları
iki hissəyə bölünür:

* işləmədəki açılışlarınkı — «hint» (sabitlik rejimində ilkin yer + köçürmə cəriməsi)
  və dərcdə ƏVƏZ olunur;
* qalanları (başqa fakültə/ixtisas) — SABİT kənar məşğulluq: müəllimi, otağı
  və (əhatədəki qrupun işləməyə düşməyən dərsidirsə) qrupu tutur.

Müəllim = slotun EFFEKTİV müəllimi (2026-09-25, bölünmüş tədris): slotun öz müəllimi
(``ScheduleSlot.instructor`` — seminarı aparan assistent), yoxdursa jurnal sahibi
(``registrar.schedule.effective_instructor_id`` ilə eyni qayda) — override olunmuş slot
ASSİSTENTİN vaxtını tutur, jurnal sahibi həmin saatda boşdur.
"""

from __future__ import annotations

from django.apps import apps as django_apps

from ..engine import WEEK_FROM_CODE, WEEKS_OF


def cells_for(periods, weekdays, weekday, start, end) -> list:
    """Slotun vaxtı ilə kəsişən şəbəkə xanaları (``t`` indeksləri)."""
    if weekday not in weekdays:
        return []
    d = weekdays.index(weekday)
    pairs = len(periods)
    return [d * pairs + p for p, row in enumerate(periods) if row["start"] < end and start < row["end"]]


def live_slots(organization, period) -> list:
    Slot = django_apps.get_model("registrar", "ScheduleSlot")
    return list(
        Slot.objects.filter(organization=organization, offering__period=period, is_parked=False)
        .order_by("weekday", "start_time", "pk")
        .values(
            "pk",
            "offering_id",
            "offering__group_id",
            "offering__instructor_id",
            "instructor_id",
            "weekday",
            "start_time",
            "end_time",
            "week_type",
            "kind",
            "room",
        )
    )


def _norm(text) -> str:
    return " ".join(str(text or "").casefold().split())


def load_rooms(organization) -> list:
    """Təşkilatın aktiv otaqları (``exams.ExamRoom`` — reverse accessor ilə, import yox)."""
    rows = organization.exam_rooms.filter(is_active=True).order_by("building", "name", "code", "pk")
    out = []
    for room in rows.values("pk", "name", "code", "building", "capacity"):
        label = (room["name"] or "").strip() or (room["code"] or "").strip() or str(room["pk"])
        out.append(
            {
                "id": str(room["pk"]),
                "label": label[:64],
                "building": (room["building"] or "").strip(),
                "capacity": int(room["capacity"] or 0),
                "keys": {key for key in (_norm(room["name"]), _norm(room["code"])) if key},
            }
        )
    return out


def split_slots(slots, run_offering_ids, scope_group_ids, *, periods, weekdays) -> dict:
    """Canlı slotları hint / kənar-müəllim / kənar-qrup / otaq məşğulluğuna ayır."""
    hints: dict = {}
    teacher_busy: dict = {}
    group_blocked: dict = {}
    room_busy: list = []
    for slot in slots:
        cells = cells_for(periods, weekdays, slot["weekday"], slot["start_time"], slot["end_time"])
        week = WEEK_FROM_CODE.get(slot["week_type"], 0)
        offering = str(slot["offering_id"])
        if offering in run_offering_ids:
            if len(cells) == 1:
                hints.setdefault(offering, []).append((slot["kind"], cells[0], week))
            continue
        # Effektiv müəllim: slotun öz müəllimi (assistent), yoxdursa jurnal sahibi.
        teacher = slot.get("instructor_id") or slot["offering__instructor_id"]
        group = str(slot["offering__group_id"] or "")
        for t in cells:
            for wk in WEEKS_OF[week]:
                if teacher:
                    teacher_busy.setdefault(teacher, set()).add((wk, t))
                if group in scope_group_ids:
                    group_blocked.setdefault(group, set()).add(t)
                if slot["room"]:
                    room_busy.append((_norm(slot["room"]), wk, t))
    return {"hints": hints, "teacher_busy": teacher_busy, "group_blocked": group_blocked, "room_busy": room_busy}


def load_availability(organization, period, teacher_ids) -> dict:
    Availability = django_apps.get_model("timetable", "TeacherAvailability")
    return {
        row.teacher_id: row
        for row in Availability.objects.filter(organization=organization, period=period, teacher_id__in=teacher_ids)
    }


def levels_string(availability, *, weekdays, pairs) -> str:
    """Əlçatanlıq şəbəkəsi → mühərrikin ``levels`` sətri (gün × cüt; olmayan = neytral)."""
    grid = getattr(availability, "grid", None) or {}
    out = []
    for weekday in weekdays:
        row = str(grid.get(str(weekday)) or "")
        for p in range(pairs):
            level = row[p] if p < len(row) else "n"
            out.append(level if level in ("n", "p", "d", "u") else "n")
    return "".join(out)


__all__ = ["cells_for", "levels_string", "live_slots", "load_availability", "load_rooms", "split_slots"]
