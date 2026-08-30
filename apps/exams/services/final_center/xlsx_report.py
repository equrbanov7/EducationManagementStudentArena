"""Final imtahan günü üçün çoxvərəqli Excel (.xlsx) hesabatı.

Niyə CSV yox: universitet hesabatında hər zal ayrıca vərəq olmalıdır (bir gündə
onlarla zal ola bilər) və pozuntu jurnalı ayrıca cədvəldir — bunlar tək-cədvəlli
CSV-yə sığmır. Fayl idarə/dekanlıq üçün "həmin gün nə baş verdi" sualının tam
cavabıdır: kim, harada, hansı stolda, hansı kompüterdə, nə vaxt, hansı nəticə
və hansı pozuntularla imtahan verib.

Vərəqlər:
  1. "Xülasə"       — filtr parametrləri + ümumi say göstəriciləri
  2. hər zal üçün    — zaldakı bütün tələbə sətirləri (tam detal)
  3. "Pozuntular"    — nəzarət hadisələri jurnalı (tələbə/zal/vaxt/ağırlıq)

Sorğular toplu (bulk) qurulub: tələbə akademik konteksti, kompüterlər və
pozuntular hər sətir üçün ayrıca DB sorğusu ilə YOX, bir dəfə yığılıb map-lə
paylanır — 500+ tələbəli gündə də sorğu sayı sabit qalır.
"""

from __future__ import annotations

import re
from collections import defaultdict

from django.utils import timezone
from django.utils.translation import pgettext

from apps.exams.models import ExamRoomComputer, SupervisionIncident
from apps.organizations.models import OrgUnit
from apps.registrar.models import StudentAcademicRecord

# Excel vərəq adında qadağan olunan simvollar (Excel özü faylı açmır).
_SHEET_FORBIDDEN = re.compile(r"[\[\]:*?/\\]")
_SHEET_MAX = 31

# Bu hadisələr pozuntu deyil — vəziyyət bərpası/təsdiqidir; ayrıca sayılmır,
# amma jurnalda görünür ki, tam xronologiya itməsin.
BENIGN_EVENTS = frozenset(
    {
        "fullscreen_restored",
        "window_focused",
        "student_acknowledged",
        "exam_started_supervised",
        "teacher_resumed",
        "teacher_granted_chance",
    }
)


# Modeldəki choice etiketləri texniki açarlardır ("absent", "removed") — rəsmi
# hesabatda oxunaqlı olmalıdır. UI-dakı sözlərlə eyni saxlanılır.
def _status_labels():
    return {
        "assigned": pgettext("exams.final_center.report", "Təyin olunub"),
        "waiting": pgettext("exams.final_center.report", "Gözləyir"),
        "ready": pgettext("exams.final_center.report", "Hazır"),
        "active": pgettext("exams.final_center.report", "İmtahanda"),
        "completed": pgettext("exams.final_center.report", "Bitirib"),
        "removed": pgettext("exams.final_center.report", "Çıxarılıb"),
        "absent": pgettext("exams.final_center.report", "Gəlməyib"),
    }


def _removal_labels():
    return {
        "removed": pgettext("exams.final_center.report", "İmtahandan çıxarılıb"),
        "suspended": pgettext("exams.final_center.report", "Dayandırılıb"),
        "technical": pgettext("exams.final_center.report", "Texniki səbəb"),
    }


def _sheet_title(raw: str, used: set[str]) -> str:
    """Excel-in vərəq adı qaydalarına uyğun, təkrarlanmayan ad."""
    title = _SHEET_FORBIDDEN.sub("-", (raw or "").strip()) or "Zal"
    title = title[:_SHEET_MAX]
    if title not in used:
        used.add(title)
        return title
    for suffix in range(2, 100):
        candidate = f"{title[: _SHEET_MAX - len(str(suffix)) - 1]} {suffix}"
        if candidate not in used:
            used.add(candidate)
            return candidate
    used.add(title)
    return title


def _local(value):
    return timezone.localtime(value) if value else None


def _fmt_dt(value):
    local = _local(value)
    return local.strftime("%d.%m.%Y %H:%M:%S") if local else ""


def _fmt_date(value):
    local = _local(value)
    return local.strftime("%d.%m.%Y") if local else ""


def _person(user) -> str:
    if not user:
        return ""
    return (user.get_full_name() or "").strip() or user.username


def _duration_minutes(started, finished) -> str:
    if not started or not finished:
        return ""
    seconds = (finished - started).total_seconds()
    return str(int(seconds // 60)) if seconds > 0 else "0"


# ── Akademik kontekst (fakültə / kafedra / ixtisas / qrup) ──────────────────


class _AcademicIndex:
    """Tələbə → (qrup, ixtisas, kafedra, fakültə, proqram, qəbul ili).

    OrgUnit iyerarxiyası təşkilata görə dəyişir (bax `project_group_sector_variability`):
    qrupun valideyni bəzi qurumlarda ixtisas, bəzilərində birbaşa kafedradır.
    Ona görə sabit dərinlik fərz edilmir — yuxarı qalxıb hər səviyyə `unit_type`
    ilə təsnif edilir.
    """

    def __init__(self, organization, student_ids):
        self._units = {
            unit.pk: unit
            for unit in OrgUnit.objects.filter(organization=organization).only("id", "name", "unit_type", "parent_id")
        }
        self._by_student = {}
        records = (
            StudentAcademicRecord.objects.filter(organization=organization, student_id__in=student_ids)
            .select_related("program", "curriculum")
            .order_by("student_id", "-is_active", "-created_at")
        )
        for record in records:
            # Bir tələbənin bir neçə qeydi ola bilər (proqram dəyişikliyi) —
            # aktiv/ən yenisi götürülür (order_by ilə birinci gələn).
            self._by_student.setdefault(record.student_id, record)

    def _ancestors(self, unit_id):
        seen = set()
        while unit_id and unit_id not in seen:
            seen.add(unit_id)
            unit = self._units.get(unit_id)
            if unit is None:
                return
            yield unit
            unit_id = unit.parent_id

    def get(self, student_id) -> dict:
        record = self._by_student.get(student_id)
        if record is None:
            return {}

        info = {
            "program": record.program.display_label if record.program_id else "",
            "admission_year": record.admission_year or "",
            "academic_status": record.get_status_display(),
        }
        by_type = {}
        for unit in self._ancestors(record.group_id):
            by_type.setdefault(unit.unit_type, unit.name)
        info["group"] = by_type.get("group") or by_type.get("class") or ""
        info["specialty"] = by_type.get("specialty") or ""
        info["chair"] = by_type.get("chair") or by_type.get("department") or ""
        info["faculty"] = by_type.get("faculty") or ""
        return info


# ── Sətir yığımı ────────────────────────────────────────────────────────────


ROOM_COLUMNS = [
    ("№", 5),
    ("Tarix", 12),
    ("İmtahan", 34),
    ("Fənn", 26),
    ("Fənn kodu", 12),
    ("Soyad, Ad", 28),
    ("İstifadəçi adı", 18),
    ("Qrup", 14),
    ("İxtisas", 26),
    ("Proqram", 26),
    ("Kafedra", 24),
    ("Fakültə", 24),
    ("Qəbul ili", 10),
    ("Akademik status", 16),
    ("Dil", 8),
    ("Zal", 24),
    ("Zal kodu", 12),
    ("Stol №", 8),
    ("Kompüter", 14),
    ("Kompüter IP", 16),
    ("Kompüter MAC", 20),
    ("Giriş vaxtı", 20),
    ("Başlama", 20),
    ("Bitmə", 20),
    ("Müddət (dəq)", 12),
    ("Status", 14),
    ("Bal", 8),
    ("Düz", 7),
    ("Səhv", 7),
    ("Pozuntu sayı", 13),
    ("Çıxarılma növü", 16),
    ("Çıxarılma səbəbi", 34),
    ("Çıxaran", 22),
    ("Çıxarılma vaxtı", 20),
    ("Yenidən qoşulma", 15),
    ("Zal nəzarətçiləri", 32),
]

INCIDENT_COLUMNS = [
    ("№", 5),
    ("Tarix və saat", 20),
    ("Tələbə", 28),
    ("İstifadəçi adı", 18),
    ("Qrup", 14),
    ("İmtahan", 30),
    ("Zal", 22),
    ("Stol №", 8),
    ("Hadisə", 24),
    ("Ağırlıq", 12),
    ("Pozuntu sayı (o anda)", 20),
    ("Qeyd", 40),
]


def _collect(organization, tickets):
    """Biletləri hesabat sətirlərinə çevir (bütün köməkçi data toplu yığılır)."""
    tickets = list(tickets)
    student_ids = {t.student_id for t in tickets}
    attempt_ids = {t.attempt_id for t in tickets if t.attempt_id}
    room_ids = {t.session.room_id for t in tickets if t.session_id}

    academic = _AcademicIndex(organization, student_ids)
    status_labels = _status_labels()
    removal_labels = _removal_labels()

    # Stol nömrəsi → kompüter (zal üzrə), yalnız lazım olan zallar üçün.
    computers = defaultdict(dict)
    by_pk = {}
    for computer in ExamRoomComputer.objects.filter(organization=organization, room_id__in=room_ids):
        by_pk[computer.pk] = computer
        if computer.seat_number is not None:
            computers[computer.room_id][computer.seat_number] = computer

    incidents = defaultdict(list)
    for incident in (
        SupervisionIncident.objects.filter(organization=organization, attempt_id__in=attempt_ids)
        .select_related("student")
        .order_by("timestamp")
    ):
        incidents[incident.attempt_id].append(incident)

    # Zal nəzarətçiləri (M2M) — zal başına bir dəfə.
    invigilators = {}
    rows = []
    for ticket in tickets:
        session = ticket.session
        room = session.room if session else None
        attempt = ticket.attempt
        info = academic.get(ticket.student_id)

        if room is not None and room.pk not in invigilators:
            names = [_person(u) for u in room.invigilators.all()]
            if session is not None and session.invigilator_id:
                own = _person(session.invigilator)
                if own and own not in names:
                    names.insert(0, own)
            invigilators[room.pk] = ", ".join(n for n in names if n)

        computer = None
        if attempt is not None and getattr(attempt, "room_computer_id", None):
            computer = by_pk.get(attempt.room_computer_id)
        if computer is None and room is not None and ticket.seat_number is not None:
            computer = computers.get(room.pk, {}).get(ticket.seat_number)

        attempt_incidents = incidents.get(ticket.attempt_id, []) if ticket.attempt_id else []
        violation_count = (
            attempt.supervision_violation_count
            if attempt is not None and attempt.supervision_violation_count
            else sum(1 for i in attempt_incidents if i.event_type not in BENIGN_EVENTS)
        )

        rows.append(
            {
                "room": room,
                "ticket": ticket,
                "incidents": attempt_incidents,
                "values": [
                    None,  # № — vərəqə yazılanda doldurulur
                    _fmt_date(ticket.entry_validated_at or (session.scheduled_start if session else None)),
                    ticket.exam.title if ticket.exam_id else "",
                    ticket.exam.subject.name if ticket.exam_id and ticket.exam.subject_id else "",
                    ticket.exam.subject.code if ticket.exam_id and ticket.exam.subject_id else "",
                    _person(ticket.student),
                    ticket.student.username,
                    info.get("group", ""),
                    info.get("specialty", ""),
                    info.get("program", ""),
                    info.get("chair", ""),
                    info.get("faculty", ""),
                    info.get("admission_year", ""),
                    info.get("academic_status", ""),
                    ticket.language or "",
                    room.name if room else "",
                    room.code if room else "",
                    ticket.seat_number if ticket.seat_number is not None else "",
                    computer.label if computer else "",
                    (computer.ip_address or "") if computer else "",
                    (computer.mac_address or "") if computer else "",
                    _fmt_dt(ticket.entry_validated_at),
                    _fmt_dt(ticket.started_at),
                    _fmt_dt(ticket.completed_at),
                    _duration_minutes(ticket.started_at, ticket.completed_at),
                    status_labels.get(ticket.status, ticket.get_status_display()),
                    attempt.teacher_score if attempt is not None and attempt.teacher_score is not None else "",
                    attempt.correct_count if attempt is not None else "",
                    attempt.wrong_count if attempt is not None else "",
                    violation_count,
                    removal_labels.get(ticket.removal_action, "") if ticket.removal_action else "",
                    ticket.removal_reason or "",
                    _person(ticket.removed_by),
                    _fmt_dt(ticket.removed_at),
                    ticket.reconnect_count,
                    invigilators.get(room.pk, "") if room else "",
                ],
                "academic": info,
            }
        )
    return rows


__all__ = [
    "BENIGN_EVENTS",
    "INCIDENT_COLUMNS",
    "ROOM_COLUMNS",
    "_AcademicIndex",
    "_collect",
    "_fmt_date",
    "_fmt_dt",
    "_person",
    "_sheet_title",
]
