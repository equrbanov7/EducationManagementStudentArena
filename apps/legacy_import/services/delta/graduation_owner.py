"""``graduation`` fazasının sahib qərarı ilə açılan (opt-in) əlavələri — sahib 2026-10-25.

İlk tətbiqdən (1 048 məzun, 201 xaric) sonra «yoxlanmalı» qalan kateqoriyalar üçün sahibin qərarı:

1. ``graduate_year_unknown`` — qəbul ili bilinməyən (köçürmə sentineli 1950 / ≤2000, köhnə «0000» qrupları,
   loginləri cutover-də arxivlənmiş) tələbələr rəsmi «Məzun etmə» əmri ilə məzun edilir
   (``MZN-SINX-2026``, 2026-07-01). Şərtlər fazanın özünküdür: qeyd ``enrolled``, cari/gələcək dövrdə qeydiyyat
   yoxdur, köhnə sistemin cari jurnalında yoxdur, azad edilməyib, əl ilə dəyişiklik izi yoxdur, «silinməli» qabı deyil;
   üstəlik köhnə sistemin cari jurnalında tutuşmayan sətrin FİN-i/adı ilə üst-üstə düşən (``legacy_unresolved_match``)
   yenə «yoxlanmalı» qalır.
2. ``leave_unfinished`` — proqramı bitməyən (``period_not_ended``), son kursdan əvvəl kəsilən
   (``left_before_final_year``) və jurnal tarixçəsi olmayan (``no_journal_history``) tələbələr rəsmi «Akademik
   məzuniyyət» əmri ilə (``AM-SINX-2026``) — status ``academic_leave`` (aktiv sayda deyil), «Bərpa» ilə geri qayıdır.
   Dekanlıq təsdiqləməlidir; hər kateqoriya hesabatda ayrıca sayılır.
3. ``deactivate_emptied_groups`` — (1)-də məzun edilənlərin QRUPLARI arxivlənir (``is_active=False``, qrup reyestrinin
   «arxivlə» əməli ilə eyni iz: audit sətri + ``settings.graduation_archived``; reyestrdə «arxivdən qaytar» ilə geri
   qaytarılır) — YALNIZ qrupda aktiv (``enrolled`` / ``academic_leave``) qeyd qalmayıbsa, qrupun cari/gələcək dövrdə
   açılışı və ya qeydiyyatı yoxdursa və aktiv alt vahidi yoxdursa.

Səbəblər ``SYNC_REASON`` prefiksi ilə yazılır — sinxronun öz izi növbəti qaçışlarda «əl ilə dəyişiklik» sayılmır.
İdempotent: məzun / məzuniyyətdəki qeyd artıq ``enrolled`` deyil (namizəd olmur), arxivlənmiş qrup toxunulmur.
"""

from __future__ import annotations

import datetime

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .registry_sync import SYNC_REASON

FLAG_GRADUATE_YEAR_UNKNOWN = "graduate_year_unknown"
FLAG_LEAVE_UNFINISHED = "leave_unfinished"
FLAG_DEACTIVATE_GROUPS = "deactivate_emptied_groups"
FLAGS = (FLAG_GRADUATE_YEAR_UNKNOWN, FLAG_LEAVE_UNFINISHED, FLAG_DEACTIVATE_GROUPS)

YEAR_UNKNOWN_REASON = f"{SYNC_REASON}: məzun — köhnə sistem: qəbul ili məlum deyil — sahibin 2026-10-25 qərarı"
LEAVE_ORDER_NUMBER = "AM-SINX-2026"
LEAVE_ORDER_DATE = datetime.date(2026, 10, 25)
#: Məzuniyyətin bitmə tarixi (rəsmi servis məcburi tələb edir) — 2026/2027 tədris ilinin sonu.
LEAVE_UNTIL = datetime.date(2027, 6, 30)
LEAVE_REASON = (
    f"{SYNC_REASON}: akademik məzuniyyət — köhnə sistemdə və cari semestr jurnallarında yoxdur — "
    "dekanlıq təsdiqləməlidir (sahibin 2026-10-25 qərarı)"
)
#: «Yoxlanmalı» kateqoriyası → akademik məzuniyyət (``leave_unfinished``).
LEAVE_KINDS = ("review.period_not_ended", "review.left_before_final_year", "review.no_journal_history")
YEAR_UNKNOWN_KIND = "review.year_unknown"
GROUP_SETTING = "graduation_archived"
GROUP_REASON = (
    f"{SYNC_REASON}: qrupun bütün tələbələri məzun edildi (qəbul ili məlum deyil) — sahibin 2026-10-25 qərarı"
)
_HOLDING_STATUSES = ("enrolled", "academic_leave")


def owner_flags(bundle: dict) -> dict:
    snapshot = bundle.get("snapshot") or {}
    return {flag: bool(snapshot.get(flag)) for flag in FLAGS}


class OwnerDecisions:
    """Fazanın «yoxlanmalı» qərarlarını sahib bayraqlarına görə rəsmi əmrə çevirir."""

    def __init__(self, sync):
        self.sync = sync
        self.run = sync.run
        self.org = sync.org
        self.flags = owner_flags(self.run.bundle)
        self.group_ids: set = set()
        for flag, enabled in self.flags.items():
            if enabled:
                self.run.count(f"graduation.info.flag.{flag}")

    def action_for(self, kind: str) -> str:
        if kind == YEAR_UNKNOWN_KIND and self.flags[FLAG_GRADUATE_YEAR_UNKNOWN]:
            return "graduate"
        if kind in LEAVE_KINDS and self.flags[FLAG_LEAVE_UNFINISHED]:
            return "leave"
        return ""

    def graduated(self, record) -> None:
        if record.group_id:
            self.group_ids.add(record.group_id)

    # ── akademik məzuniyyət ───────────────────────────────────────────────
    def leave(self, record, kind: str) -> None:
        from apps.registrar.public import movements

        category = kind.split(".", 1)[1]
        try:
            with transaction.atomic():
                movements.create_movement(
                    record=record,
                    kind=movements.MovementKind.ACADEMIC_LEAVE,
                    order_number=LEAVE_ORDER_NUMBER,
                    order_date=LEAVE_ORDER_DATE,
                    reason=LEAVE_REASON,
                    actor=self.run.actor,
                    effective_until=LEAVE_UNTIL,
                )
        except (movements.MovementError, ValidationError) as error:
            code = getattr(error, "code", "") or error.__class__.__name__
            self.run.count("graduation.leave_failed")
            self.run.names("graduation_leave_failed", self.sync.person(record), f"{self.sync.label(record)} · {code}")
            return
        self.run.count("graduation.leave")
        self.run.count(f"graduation.leave.{category}")
        self.run.count("written.student_movements")
        self.run.names(f"graduation_leave.{category}", self.sync.person(record), self.sync.label(record))

    # ── qrupların arxivlənməsi ────────────────────────────────────────────
    def finish(self) -> None:
        if not self.flags[FLAG_DEACTIVATE_GROUPS] or not self.group_ids:
            return
        OrgUnit = django_apps.get_model("organizations", "OrgUnit")
        for unit in OrgUnit.objects.filter(organization=self.org, pk__in=list(self.group_ids)).order_by("name"):
            verdict = self._group_verdict(unit)
            self.run.count(f"graduation.groups.{verdict}")
            if verdict == "deactivated":
                self._archive(unit)
                self.run.names("graduation_group_deactivated", unit.name, "")
            elif verdict != "already_inactive":
                self.run.names("graduation_group_kept", unit.name, verdict)

    def _group_verdict(self, unit) -> str:
        if not unit.is_active:
            return "already_inactive"
        Record = django_apps.get_model("registrar", "StudentAcademicRecord")
        if Record.objects.filter(organization=self.org, group=unit, status__in=_HOLDING_STATUSES).exists():
            return "kept.active_records"
        today = datetime.date.today()
        open_period = Q(period__is_active=True) & (Q(period__is_current=True) | Q(period__start_date__gt=today))
        CourseOffering = django_apps.get_model("registrar", "CourseOffering")
        if CourseOffering.objects.filter(open_period, organization=self.org, group=unit).exists():
            return "kept.open_period"
        Enrollment = django_apps.get_model("registrar", "Enrollment")
        enrollment_open = Q(offering__period__is_active=True) & (
            Q(offering__period__is_current=True) | Q(offering__period__start_date__gt=today)
        )
        members = Record.objects.filter(organization=self.org, group=unit).values("student_id")
        if Enrollment.objects.filter(
            enrollment_open, Q(source_group=unit) | Q(student_id__in=members), organization=self.org
        ).exists():
            return "kept.open_period"
        if type(unit).objects.filter(parent=unit, is_active=True).exists():
            return "kept.active_children"
        return "deactivated"

    def _archive(self, unit) -> None:
        from core.audit import log_action
        from core.constants import AuditAction

        settings_blob = dict(unit.settings) if isinstance(unit.settings, dict) else {}
        settings_blob[GROUP_SETTING] = {"at": timezone.now().isoformat(), "tag": self.run.tag, "reason": GROUP_REASON}
        unit.settings = settings_blob
        unit.is_active = False
        unit.save(update_fields=["is_active", "settings", "updated_at"])
        log_action(
            action=AuditAction.UPDATE,
            user=self.run.actor,
            organization=self.org,
            obj=unit,
            reason=f"groups: archived — {GROUP_REASON}",
            old_values={"is_active": True},
            new_values={"is_active": False, "reason": GROUP_REASON, "batch": self.run.tag},
        )
        self.run.count("written.groups_archived")


__all__ = [
    "FLAGS",
    "LEAVE_KINDS",
    "LEAVE_ORDER_DATE",
    "LEAVE_ORDER_NUMBER",
    "LEAVE_REASON",
    "LEAVE_UNTIL",
    "YEAR_UNKNOWN_REASON",
    "OwnerDecisions",
    "owner_flags",
]
