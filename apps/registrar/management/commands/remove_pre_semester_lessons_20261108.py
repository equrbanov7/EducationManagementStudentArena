"""``remove_pre_semester_lessons_20261108`` — cari semestrin başlanğıcından ƏVVƏL tarixli dərslər (sahib 2026-11-08).

Sahib: «ayın 15-dən tez jurnala nə isə yazıla bilməz … bütün sistemə tətbiq et, 15-dən tez nə yazılıbsa o xanalar
silinsin». Cari semestrin (``is_current``) bütün jurnallarında ``date < period.start_date`` olan dərslər xanaları ilə
silinir; rəsmi düzəlişi (``LessonCorrection`` / ``JournalCorrection``) olan dərs toxunulmur və sayılır. Audit seçilmiş
dərs/xana sahələrini və ``created_at``-ı saxlayır. Undo yalnız bu sahələri və ilkin dərs ID-sini bərpa edir;
köhnə xana ID-ləri və ``updated_at`` auditdə yoxdur, onların eyniliyi təmin edilmir. Əvəzləyici dərs, dəyişmiş xana
və ya itmiş qeydiyyat varsa bütün bərpa dayanır. Tam eyni vəziyyətə təkrar undo yazısızdır. Bu geniş undo tarixi
düzəltmir və 33 mənbə balının ayrıca bərpa planını əvəz etmir. Qayıb saatı yenidən hesablanır. Defolt dry-run;
stdout-a YALNIZ saylar. Gövdə: :mod:`apps.registrar.pre_semester_lessons` (11-14 qaçışı ilə ortaq).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from core.audit import log_action
from core.constants import AuditAction

from ... import pre_semester_lessons as service
from ...pre_semester_lessons import RESOURCE
from .relocate_twin_enrollment import run_plan

PREFIX = "pre_semester:"
REASON = "Sahib 2026-11-08: semestrin başlanğıcından əvvəl tarixli dərslər silindi"


def remove(organization, actor, counts) -> None:
    service.remove(organization, actor, counts, reason=REASON)


def undo(organization, actor, counts) -> None:
    service.undo(organization, actor, counts, reason=REASON)


class Command(BaseCommand):
    help = "Sahib 2026-11-08: semestrin başlanğıcından əvvəl tarixli dərslər (xanaları ilə) silinir (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--undo", action="store_true", help="Silinən dərsləri geri qaytar")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        def runner(organization, actor, counts):
            (undo if options["undo"] else remove)(organization, actor, counts)

        run_plan(self, options=options, prefix=PREFIX, runner=runner)


# Testlər və köhnə çağırışlar üçün (audit qəbzi modelləşdirmə: ``log_action`` / ``AuditAction``).
__all__ = ["PREFIX", "REASON", "RESOURCE", "AuditAction", "Command", "log_action", "remove", "undo"]
