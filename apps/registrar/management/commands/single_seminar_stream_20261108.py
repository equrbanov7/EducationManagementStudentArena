"""``single_seminar_stream_20261108`` — jurnalın seminarı BİR axındır: köhnə alt qrup bölgüsü və pay məhdudiyyəti açılır.

Sahib 2026-11-08 (audit 3, 536 MU · Xətti cəbr): MU1 + MU2 ana jurnala birləşdi (yükdə seminar bir axındır,
``1804fd03``), amma ana jurnalda əvvəlki bölgü qalmışdı — «536 MU1» / «536 MU2» seminar alt qrupları və seminarçının
(Orucova) payı yalnız köhnə 27 tələbəyə bağlı idi; o, 47 tələbədən 20-ni görmürdü. Bu əmr :data:`PLAN`-dakı hər
jurnal üçün:

* seminarı əhatə edən aktiv payın tələbə siyahısını boşaldır (boş = jurnalın bütün tələbələri);
* tələbələrin ``seminar_group`` nömrəsini sıfırlayır və ``SeminarGroup`` sətirlərini silir.

Qoruyucu: alt qrupa bağlı (``seminar_group`` dolu) dərs varsa jurnal toxunulmur (``blocked_tagged_lessons``) — əvvəl
həmin dərslər həll olunmalıdır. Hər dəyişiklik audit sətrindədir — ``--undo`` qaytarır. Defolt dry-run; stdout-a
YALNIZ saylar.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .relocate_twin_enrollment import run_plan

PREFIX = "seminar_stream:"
RESOURCE = "registrar.single_seminar_stream"
REASON = "Sahib 2026-11-08: jurnalın seminarı bir axındır — alt qrup bölgüsü və pay məhdudiyyəti açıldı"
#: Seminarı bir axın olan jurnallar (yalnız id).
PLAN = ("0f7f3cc3-e22c-4da5-a4d2-07f11bacd711",)  # 536 MU · Xətti cəbr və riyazi analiz


def _model(name):
    return django_apps.get_model("registrar", name)


def _covers_seminar(share) -> bool:
    return not share.kinds or "seminar" in share.kinds


def apply(organization, actor, counts) -> None:
    Lesson, Enrollment, SeminarGroup = _model("Lesson"), _model("Enrollment"), _model("SeminarGroup")
    for offering_id in PLAN:
        offering = (
            _model("CourseOffering").objects.filter(organization=organization, pk=offering_id, is_active=True).first()
        )
        if offering is None:
            counts["offering_missing"] += 1
            continue
        if Lesson.objects.filter(offering=offering, seminar_group__isnull=False).exists():
            counts["blocked_tagged_lessons"] += 1
            continue
        shares = {}
        for share in _model("JournalShare").objects.filter(offering=offering, is_active=True):
            ids = [str(pk) for pk in share.enrollments.values_list("pk", flat=True)]
            if ids and _covers_seminar(share):
                shares[str(share.pk)] = ids
                share.enrollments.clear()
                counts["shares_unrestricted"] += 1
                counts["share_students_released"] += len(ids)
        rows = Enrollment.objects.filter(offering=offering, seminar_group__isnull=False)
        numbers = {str(pk): number for pk, number in rows.values_list("pk", "seminar_group")}
        rows.update(seminar_group=None, updated_at=timezone.now())
        counts["enrollment_seminar_groups_cleared"] += len(numbers)
        groups = [
            {"number": row.number, "name": row.name, "unit": str(row.unit_id) if row.unit_id else None}
            for row in SeminarGroup.objects.filter(offering=offering)
        ]
        SeminarGroup.objects.filter(offering=offering).delete()
        counts["seminar_groups_deleted"] += len(groups)
        if not (shares or numbers or groups):
            counts["already_single"] += 1
            continue
        counts["offerings_changed"] += 1
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=offering,
            changes={"shares": shares, "seminar_groups": numbers, "groups": groups},
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=str(offering.pk),
        )


def undo(organization, actor, counts) -> None:
    Enrollment, SeminarGroup, JournalShare = _model("Enrollment"), _model("SeminarGroup"), _model("JournalShare")
    AuditLog = django_apps.get_model("audit", "AuditLog")
    for row in AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, reason=REASON).order_by(
        "-created_at"
    ):
        changes = row.changes or {}
        offering_id = row.resource_id
        for group in changes.get("groups") or []:
            _, made = SeminarGroup.objects.get_or_create(
                organization=organization,
                offering_id=offering_id,
                number=group["number"],
                defaults={"name": group.get("name") or "", "unit_id": group.get("unit")},
            )
            counts["undo_groups_restored" if made else "undo_groups_present"] += 1
        for pk, number in (changes.get("seminar_groups") or {}).items():
            done = Enrollment.objects.filter(pk=pk, offering_id=offering_id, seminar_group__isnull=True).update(
                seminar_group=number, updated_at=timezone.now()
            )
            counts["undo_enrollments_restored" if done else "undo_enrollments_skipped"] += 1
        for pk, ids in (changes.get("shares") or {}).items():
            share = JournalShare.objects.filter(pk=pk, offering_id=offering_id).first()
            if share is None or share.enrollments.exists():
                counts["undo_shares_skipped"] += 1
                continue
            share.enrollments.add(*Enrollment.objects.filter(pk__in=ids, offering_id=offering_id))
            counts["undo_shares_restricted"] += 1


class Command(BaseCommand):
    help = (
        "Sahib 2026-11-08: jurnalın seminarı bir axın — alt qrup bölgüsü və pay məhdudiyyəti açılır (defolt dry-run)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--undo", action="store_true", help="Dəyişiklikləri geri qaytar")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        def runner(organization, actor, counts):
            (undo if options["undo"] else apply)(organization, actor, counts)

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
