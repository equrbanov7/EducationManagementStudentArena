"""``restore_archived_students`` — səhvən «məzun» (arxiv) sayılmış konkret tələbələrin girişini bərpa edir (2026-10-27).

Sahib: «131 T qrupundan … parol bərpa edirəm, məzun göstərir; qrupa girirəm, aktiv göstərir — onu fixlə». Köçürmə
qəbul ili həll olunmayan (``1950`` yer-tutucusu) bəzi CARİ tələbələri arxivləyib; akademik qeyd ``enrolled`` və
qrupda aktiv qalıb, giriş və parol bərpası isə ``access_state='archived'`` ilə bağlıdır.

Yalnız ADI ilə verilən hesablar (``--usernames``) və yalnız bu şərtlərlə: profil ``archived``, hesab aktiv, aktiv
``enrolled`` akademik qeydi var və qrupu «Xaric …» psevdo-qrupu DEYİL. Keçid mövcud, auditli
``restore_archived_account`` ilə (0018 funksiyası + bərpa sübutu; sübut = təşkilat + istifadəçi + sahib qərarı
sha256). ``--admission-year`` verilsə yer-tutucu qəbul ili (1950) də düzəlir. DEFOLT DRY-RUN; stdout-a yalnız saylar.
"""

from __future__ import annotations

import hashlib
from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.legacy_import.services.repair_archive import student_role
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "restore_archived:"
SENTINEL_YEAR = 1950
EVIDENCE_REASON = "manual_registry_verification"
_EVIDENCE_PREFIX = b"owner-restore-archived-student-v1\x00"


class _DryRun(Exception):
    pass


def _digest(organization_pk, user_pk) -> str:
    return hashlib.sha256(_EVIDENCE_PREFIX + f"{organization_pk}:{user_pk}".encode()).hexdigest()


class Command(BaseCommand):
    help = "Səhvən arxivlənmiş (məzun sayılmış) konkret tələbələrin girişini bərpa edir (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True, help="Əməliyyatı aparan superadmin istifadəçi adı")
        parser.add_argument("--usernames", required=True, help="Vergüllə ayrılmış istifadəçi adları (≤ 50)")
        parser.add_argument("--admission-year", type=int, default=0, help="Yer-tutucu (1950) qəbul ilini düzəlt")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        from apps.accounts.public import restore_archived_account

        usernames = [name.strip() for name in str(options["usernames"]).split(",") if name.strip()]
        if not usernames or len(usernames) > 50:
            raise CommandError("restore_archived_usernames_required")
        year = int(options["admission_year"] or 0)
        if year and not 2000 <= year <= 2100:
            raise CommandError("restore_archived_admission_year_out_of_range")
        counts = Counter()
        User = get_user_model()
        Organization = django_apps.get_model("organizations", "Organization")
        Record = django_apps.get_model("registrar", "StudentAcademicRecord")
        try:
            with rls_worker_atomic(), bypass_rls(), transaction.atomic():
                organization = Organization.objects.get(slug=options["org"])
                actor = User.objects.get(username=options["actor"], is_active=True)
                role = student_role(organization)
                for username in usernames:
                    user = User.objects.filter(username=username).select_related("profile").first()
                    profile = getattr(user, "profile", None)
                    if user is None or profile is None:
                        counts["skip_unknown"] += 1
                        continue
                    if profile.access_state != "archived":
                        counts["skip_not_archived"] += 1
                        continue
                    record = (
                        Record.objects.filter(
                            organization=organization, student=user, is_active=True, status="enrolled"
                        )
                        .select_related("group")
                        .first()
                    )
                    if record is None or not user.is_active:
                        counts["skip_no_active_record"] += 1
                        continue
                    if record.group is not None and record.group.name.strip().lower().startswith("xaric"):
                        counts["skip_expelled_group"] += 1
                        continue
                    result = restore_archived_account(
                        user=user,
                        organization=organization,
                        expected_role=role,
                        actor=actor,
                        email_authority_evidence_digest=_digest(organization.pk, user.pk),
                        email_authority_reason_code=EVIDENCE_REASON,
                    )
                    counts["restored" if getattr(result, "restored", False) else "already_active"] += 1
                    if year and record.admission_year == SENTINEL_YEAR:
                        Record.objects.filter(pk=record.pk).update(admission_year=year)
                        counts["admission_year_fixed"] += 1
                if not options["apply"]:
                    raise _DryRun
        except _DryRun:
            counts["dry_run"] = 1
        for key in sorted(counts):
            self.stdout.write(f"{PREFIX} {key}={counts[key]}")
