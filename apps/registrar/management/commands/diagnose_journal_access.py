"""``diagnose_journal_access`` — jurnalda «Yeni dərs» / yazma niyə yoxdur (yalnız OXU, sahib 2026-10-26).

Sahib: «müəllimdə yeni dərs əlavə et yeri görünmür — səbəbinə bax». Jurnal səhifəsi yalnız universitet
şəbəkəsindən açılır; bu əmr ``journal_detail``-in ``can_edit`` şərtlərini AYRI-AYRI hesablayır:

* açılış aktivdir (``offering_accepts_writes``), müəllim təyin olunub;
* jurnalın sahibi (``instructor``) aktivdir, ``grade.input`` səlahiyyəti var (``is_authorized_instructor``);
* jurnal bağlı deyil (``journal_is_locked``), sillabus qapısı (``journal_policy.syllabus_gate``);
* ``--user`` verilərsə həmin istifadəçi üçün ``is_direct_editor`` / bölünmüş jurnal əhatəsi.

Heç nə yazmır (tranzaksiya geri qaytarılır — ``ensure_assessment_scheme`` sxem yarada bilər). Stdout-a YALNIZ
``journal_access: açar=dəyər`` sətirləri (ad / istifadəçi adı çap olunmur).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...models import CourseOffering

PREFIX = "journal_access:"


def _flag(value) -> str:
    return "yes" if value else "no"


class Command(BaseCommand):
    help = "Jurnalın yazma/«Yeni dərs» şərtlərini ayrı-ayrı göstərir (yalnız oxu)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--offering", required=True, help="Açılışın (jurnalın) UUID-i")
        parser.add_argument("--user", default="", help="Yoxlanan istifadəçinin adı (boş — jurnalın sahibi)")

    def handle(self, *args, **options):
        from ... import gradebook, journal_policy
        from ...integrity import is_authorized_instructor
        from ...journal_access import is_direct_editor, offering_accepts_writes
        from ...journal_shares import journal_scope

        values = {}
        with rls_worker_atomic(), bypass_rls(), transaction.atomic():
            offering = (
                CourseOffering.objects.select_related("organization", "instructor", "period")
                .filter(pk=str(options["offering"]).strip(), organization__slug=str(options["org"]).strip())
                .first()
            )
            if offering is None:
                raise CommandError("journal_access_offering_unknown")
            user = offering.instructor
            if options["user"]:
                user = get_user_model().objects.filter(username=options["user"]).first()
                if user is None:
                    raise CommandError("journal_access_user_unknown")
            gate = journal_policy.syllabus_gate(offering)
            values.update(
                offering_active=_flag(offering.is_active),
                period_locked=_flag(getattr(offering.period, "locked_at", None)),
                has_instructor=_flag(offering.instructor_id),
                user_is_instructor=_flag(user is not None and user.pk == offering.instructor_id),
                user_active=_flag(user is not None and user.is_active),
                user_grade_input=_flag(
                    user is not None and is_authorized_instructor(organization=offering.organization, instructor=user)
                ),
                accepts_writes=_flag(offering_accepts_writes(offering)),
                journal_locked=_flag(gradebook.journal_is_locked(offering)),
                syllabus_enforced=_flag(gate["enforced"]),
                syllabus_locked=_flag(gate["locked"]),
            )
            if user is not None:
                scope = journal_scope(user, offering)
                direct = is_direct_editor(user, offering)
                values.update(
                    direct_editor=_flag(direct),
                    share_full=_flag(scope.full),
                    can_edit=_flag(direct and values["journal_locked"] == "no" and not gate["locked"]),
                )
            transaction.set_rollback(True)
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in values.items()))
