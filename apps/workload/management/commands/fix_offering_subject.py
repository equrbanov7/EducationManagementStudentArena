"""``fix_offering_subject`` — səhv fənnə bağlanmış jurnalın fənnini YERİNDƏ düzəldir (2026-11-03).

Bax :mod:`apps.workload.services.offering_subject_fix`. Jurnal (dərslər, xanalar, tələbələr) toxunulmur; köhnə
sillabus bağı ayrılır, düzgün sillabus paylaşma ilə bağlanır, yük sətrinin fənni düzəliş axını ilə dəyişir və
sinxron YENİ jurnal yaratmır. Toqquşmada heç nə yazılmır. DEFOLT DRY-RUN (yazılar icra olunub geri qaytarılır);
idempotent. Stdout-a YALNIZ saylar (``offering_subject_fix: açar=say …``).
"""

from __future__ import annotations

import re

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...services.offering_subject_fix import OfferingSubjectFixError, fix_offering_subject

PREFIX = "offering_subject_fix:"
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _uuid(value, code, *, required=False) -> str:
    text = str(value or "").strip().lower()
    if (required or text) and not _UUID.match(text):
        raise CommandError(code)
    return text


class Command(BaseCommand):
    help = "Jurnalın (açılışın) səhv fənn bağını yerində düzəldir: fənn, sillabus bağı, yük sətri (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--offering", required=True, help="Jurnalın (açılışın) UUID-i")
        parser.add_argument("--subject", required=True, help="Düzgün (hədəf) fənnin UUID-i")
        parser.add_argument("--detach-syllabus", default="", help="Ayrılacaq səhv sillabusun UUID-i (istəyə bağlı)")
        parser.add_argument("--attach-syllabus", default="", help="Paylaşma ilə bağlanacaq sillabusun UUID-i")
        parser.add_argument("--row", default="", help="Fənni dəyişəcək yük sətrinin UUID-i (istəyə bağlı)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        values = {
            "offering_id": _uuid(options["offering"], "offering_invalid", required=True),
            "subject_id": _uuid(options["subject"], "subject_invalid", required=True),
            "detach_syllabus_id": _uuid(options["detach_syllabus"], "detach_syllabus_invalid"),
            "attach_syllabus_id": _uuid(options["attach_syllabus"], "attach_syllabus_invalid"),
            "row_id": _uuid(options["row"], "row_invalid"),
        }
        Organization = django_apps.get_model("organizations", "Organization")
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("organization_unknown")
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            try:
                result = fix_offering_subject(organization=organization, user=actor, apply=options["apply"], **values)
            except OfferingSubjectFixError as exc:
                raise CommandError(str(exc)) from None
            except DatabaseError:
                raise CommandError("offering_subject_fix_database_conflict") from None
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(result.items())))
