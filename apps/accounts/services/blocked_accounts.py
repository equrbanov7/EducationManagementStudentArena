"""Bloklanmış / deaktiv hesabların hesabatı (sahib 2026-10-17: «Bloklanmış hesablara da bax»).

Kim sayılır (təşkilatın üzvü — istənilən vəziyyətdə üzvlük və ya ``profile.organization``):

* ``deleted`` — ``profile.is_deleted`` (soft-delete);
* ``blocked`` — ``user.is_active=False`` («Hesabı dayandır», o cümlədən «Forma 7» tutuşdurmasının bloku);
* ``archived`` / ``staged`` — ``profile.access_state`` girişi bağlayır (məzun/xaric, idxal keçidi);
* ``membership_inactive`` — hesab aktivdir, amma bu təşkilatda AKTİV üzvlüyü yoxdur.

ŞÜBHƏLİ hallar:

* ``teacher_with_load`` — müəllim (müəllim rolu və ya cari yük) CARİ semestrdə yük daşıyır: tapşırıq bölgüsü
  (``TeacherAssignment``), jurnal sahibi (``CourseOffering.instructor``) və ya dərs cədvəli slotu;
* ``student_enrolled`` — tələbənin aktiv ``StudentAcademicRecord``-u (status enrolled) və ya cari semestrdə
  aktiv qeydiyyatı var (arxiv hesablarda bu, köhnə idxalın sistemli izidir — ``archived_record_enrolled``,
  ayrıca sayılır, şübhəli sayılmır).

QA hesabları (``qa.*``) qəsdən təqaüdə çıxarılıb — hesabata DÜŞMÜR. ``unblock_teachers_with_load`` YALNIZ
«Forma 7» idxalının blokladığı ``blocked`` + ``teacher_with_load`` (tələbə olmayan) hesabları rəsmi servislə
(``account_deletion.unblock_account`` — audit sətri yazır) açır; tələbələr heç vaxt avtomatik açılmır.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from .account_deletion import AccountDeletionError, unblock_account
from .teacher_roster.apply import BLOCK_REASON_CODE as ROSTER_BLOCK_REASON_CODE
from .teacher_roster.protection import STUDENT_ROLE_NAMES, TEACHING_ROLE_NAMES

QA_USERNAME = re.compile(r"^qa\.")
STUDENT_PROFILE_ROLES = frozenset({"student", "lead_student"})

STATUS_DELETED = "deleted"
STATUS_BLOCKED = "blocked"
STATUS_ARCHIVED = "archived"
STATUS_STAGED = "staged"
STATUS_MEMBERSHIP_INACTIVE = "membership_inactive"
STATUSES = (STATUS_DELETED, STATUS_BLOCKED, STATUS_ARCHIVED, STATUS_STAGED, STATUS_MEMBERSHIP_INACTIVE)

FLAG_TEACHER_LOAD = "teacher_with_load"
FLAG_STUDENT_ENROLLED = "student_enrolled"
FLAG_ARCHIVED_RECORD = "archived_record_enrolled"

UNBLOCK_REASON = "Cari semestrdə dərs yükü olan müəllimin bloku açıldı (blocked_accounts_report) — sahib 2026-10-17"

REPORT_HEADER = (
    "username",
    "status",
    "kind",
    "roles",
    "block_reason_code",
    "block_source",
    "blocked_at",
    "active_memberships",
    "assignments",
    "offerings",
    "slots",
    "sar_enrolled",
    "enrollments",
    "flag",
    "action",
)


@dataclass
class Row:
    user_id: object
    username: str
    status: str
    roles: set = field(default_factory=set)
    profile_role: str = ""
    block_reason_code: str = ""
    block_source: str = ""
    blocked_at: str = ""
    active_memberships: int = 0
    assignments: int = 0
    offerings: int = 0
    slots: int = 0
    sar_enrolled: int = 0
    enrollments: int = 0
    action: str = ""

    @property
    def load(self) -> int:
        return self.assignments + self.offerings + self.slots

    @property
    def is_student(self) -> bool:
        if self.roles & TEACHING_ROLE_NAMES:
            return False
        return bool(self.roles & STUDENT_ROLE_NAMES) or self.profile_role in STUDENT_PROFILE_ROLES

    @property
    def kind(self) -> str:
        if self.is_student:
            return "student"
        if self.roles & TEACHING_ROLE_NAMES or self.load:
            return "teacher"
        return "other"

    @property
    def flag(self) -> str:
        if self.kind == "teacher" and self.load:
            return FLAG_TEACHER_LOAD
        if self.kind == "student" and (self.sar_enrolled or self.enrollments):
            # Arxiv (məzun/xaric) hesabların köhnə idxal qeydi «enrolled» qalır — sistemli haldır, ayrıca sayılır.
            return FLAG_ARCHIVED_RECORD if self.status == STATUS_ARCHIVED else FLAG_STUDENT_ENROLLED
        return ""

    def csv_row(self):
        return (
            self.username,
            self.status,
            self.kind,
            ",".join(sorted(self.roles)),
            self.block_reason_code,
            self.block_source,
            self.blocked_at,
            self.active_memberships,
            self.assignments,
            self.offerings,
            self.slots,
            self.sar_enrolled,
            self.enrollments,
            self.flag,
            self.action,
        )


def _status(*, is_active, is_deleted, access_state, active_memberships) -> str:
    if is_deleted:
        return STATUS_DELETED
    if not is_active:
        return STATUS_BLOCKED
    if access_state in (STATUS_ARCHIVED, STATUS_STAGED):
        return access_state
    if not active_memberships:
        return STATUS_MEMBERSHIP_INACTIVE
    return ""


def _block_source(reason: str, code: str) -> str:
    if "[roster-" in (reason or ""):
        return "teacher_roster"
    return "manual" if (reason or code) else ""


def _count_by(queryset, field_name: str) -> dict:
    return dict(queryset.values(field_name).annotate(n=Count("pk", distinct=True)).values_list(field_name, "n"))


class BlockedAccountsReport:
    """Hesabatı qurur (yalnız oxuyur); :meth:`unblock_teachers_with_load` yazır."""

    def __init__(self, organization):
        self.organization = organization
        self.period = organization.academic_periods.filter(is_current=True, is_active=True).first()
        self.qa_skipped = 0
        self.rows: list[Row] = self._build()

    def _users(self):
        Membership = django_apps.get_model("organizations", "Membership")
        memberships = Membership.objects.filter(organization=self.organization).values_list(
            "user_id", "role__name", "is_active", "role__is_active"
        )
        roles: dict = defaultdict(set)
        active: Counter = Counter()
        for user_id, role_name, is_active, role_active in memberships:
            roles[user_id].add(role_name)
            if is_active and role_active:
                active[user_id] += 1
        ids = set(roles) | set(
            get_user_model().objects.filter(profile__organization=self.organization).values_list("pk", flat=True)
        )
        return ids, roles, active

    def _build(self) -> list[Row]:
        ids, roles, active = self._users()
        fields = (
            "pk",
            "username",
            "is_active",
            "profile__is_deleted",
            "profile__access_state",
            "profile__role",
            "profile__block_reason",
            "profile__block_reason_code",
            "profile__blocked_at",
        )
        rows = []
        for pk, username, is_active, deleted, access, role, reason, code, blocked_at in (
            get_user_model().objects.filter(pk__in=ids).values_list(*fields).order_by("username")
        ):
            if QA_USERNAME.match(username or ""):
                self.qa_skipped += 1
                continue
            status = _status(
                is_active=is_active,
                is_deleted=bool(deleted),
                access_state=access or "",
                active_memberships=active.get(pk, 0),
            )
            if not status:
                continue
            rows.append(
                Row(
                    user_id=pk,
                    username=username,
                    status=status,
                    roles=roles.get(pk, set()),
                    profile_role=role or "",
                    block_reason_code=code or "",
                    block_source=_block_source(reason, code) if status == STATUS_BLOCKED else "",
                    blocked_at=blocked_at.date().isoformat() if blocked_at else "",
                    active_memberships=active.get(pk, 0),
                )
            )
        self._attach_load(rows)
        return rows

    def _attach_load(self, rows: list[Row]) -> None:
        user_ids = [row.user_id for row in rows]
        if not user_ids:
            return
        org = self.organization
        SAR = django_apps.get_model("registrar", "StudentAcademicRecord")
        sar = _count_by(
            SAR.objects.filter(organization=org, student_id__in=user_ids, is_active=True, status="enrolled"),
            "student_id",
        )
        assignments = offerings = slots = enrollments = {}
        if self.period is not None:
            period = self.period
            TeacherAssignment = django_apps.get_model("workload", "TeacherAssignment")
            assignments = _count_by(
                TeacherAssignment.objects.filter(organization=org, teacher_id__in=user_ids)
                .filter(
                    Q(row__period=period) | Q(row__period__isnull=True, row__task__academic_year=period.academic_year)
                )
                .exclude(row__task__status="cancelled"),
                "teacher_id",
            )
            CourseOffering = django_apps.get_model("registrar", "CourseOffering")
            offerings = _count_by(
                CourseOffering.objects.filter(
                    organization=org, period=period, is_active=True, instructor_id__in=user_ids
                ),
                "instructor_id",
            )
            ScheduleSlot = django_apps.get_model("registrar", "ScheduleSlot")
            live = ScheduleSlot.objects.filter(
                organization=org, offering__period=period, offering__is_active=True, is_parked=False
            )
            slots = Counter(_count_by(live.filter(instructor_id__in=user_ids), "instructor_id"))
            slots.update(
                _count_by(
                    live.filter(instructor__isnull=True, offering__instructor_id__in=user_ids),
                    "offering__instructor_id",
                )
            )
            Enrollment = django_apps.get_model("registrar", "Enrollment")
            enrollments = _count_by(
                Enrollment.objects.filter(
                    organization=org, student_id__in=user_ids, status="enrolled", offering__period=period
                ),
                "student_id",
            )
        for row in rows:
            row.sar_enrolled = sar.get(row.user_id, 0)
            row.assignments = assignments.get(row.user_id, 0)
            row.offerings = offerings.get(row.user_id, 0)
            row.slots = slots.get(row.user_id, 0)
            row.enrollments = enrollments.get(row.user_id, 0)

    def unblock_teachers_with_load(self, *, actor=None) -> int:
        """Yalnız «Forma 7» idxalının blokladığı ``blocked`` + ``teacher_with_load`` (tələbə deyil) — rəsmi
        ``unblock_account`` ilə. Əl ilə (təhlükəsizlik, işdən çıxma, intizam …) bloklananlar AÇILMIR — hesabatda
        ``manual_review`` kimi qalır (SEC-1 F3, 2026-10-17)."""
        users = get_user_model().objects.in_bulk([row.user_id for row in self.rows if self._can_unblock(row)])
        done = 0
        for row in self.rows:
            user = users.get(row.user_id)
            if user is None:
                continue
            try:
                unblock_account(user, actor=actor, reason=UNBLOCK_REASON)
            except AccountDeletionError as exc:
                row.action = f"unblock_refused:{exc}"
                continue
            row.action = "unblocked"
            done += 1
        return done

    @staticmethod
    def _can_unblock(row: Row) -> bool:
        return (
            row.status == STATUS_BLOCKED
            and row.flag == FLAG_TEACHER_LOAD
            and not row.is_student
            and row.block_source == "teacher_roster"
            and row.block_reason_code == ROSTER_BLOCK_REASON_CODE
        )

    @staticmethod
    def _needs_review(row: Row) -> bool:
        return (
            row.status == STATUS_BLOCKED
            and row.flag == FLAG_TEACHER_LOAD
            and not BlockedAccountsReport._can_unblock(row)
        )

    def counters(self) -> dict:
        out = Counter({status: 0 for status in STATUSES})
        out.update(row.status for row in self.rows)
        out["total"] = len(self.rows)
        out[FLAG_TEACHER_LOAD] = sum(1 for row in self.rows if row.flag == FLAG_TEACHER_LOAD)
        out[f"{FLAG_TEACHER_LOAD}_blocked"] = sum(1 for row in self.rows if self._can_unblock(row))
        out[f"{FLAG_TEACHER_LOAD}_manual_review"] = sum(1 for row in self.rows if self._needs_review(row))
        out[FLAG_STUDENT_ENROLLED] = sum(1 for row in self.rows if row.flag == FLAG_STUDENT_ENROLLED)
        out[FLAG_ARCHIVED_RECORD] = sum(1 for row in self.rows if row.flag == FLAG_ARCHIVED_RECORD)
        out["unblocked"] = sum(1 for row in self.rows if row.action == "unblocked")
        out["qa_skipped"] = self.qa_skipped
        out["no_current_period"] = int(self.period is None)
        return dict(out)


__all__ = [
    "FLAG_ARCHIVED_RECORD",
    "FLAG_STUDENT_ENROLLED",
    "FLAG_TEACHER_LOAD",
    "REPORT_HEADER",
    "BlockedAccountsReport",
]
