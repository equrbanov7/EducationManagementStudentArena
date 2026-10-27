"""``restore_archived_students`` — səhvən «məzun» (arxiv) sayılmış konkret tələbələrin girişini bərpa edir (2026-10-27).

Sahib: «131 T qrupundan … parol bərpa edirəm, məzun göstərir; qrupa girirəm, aktiv göstərir — onu fixlə». Köçürmə
qəbul ili həll olunmayan (``1950`` yer-tutucusu) bəzi CARİ tələbələri arxivləyib; akademik qeyd ``enrolled`` və
qrupda aktiv qalıb, giriş və parol bərpası isə ``access_state='archived'`` ilə bağlıdır.

Yalnız ADI ilə verilən hesablar (``--usernames``) və yalnız bu şərtlərlə: profil ``archived``, hesab aktiv, aktiv
``enrolled`` akademik qeydi var və qrupu «Xaric …» psevdo-qrupu DEYİL. Qayda və keçid accounts tərəfindədir
(``apps.accounts.public.restore_wrongly_archived_student`` — RİM-in «Arxivdən çıxar» düyməsi ilə EYNİ; auditli
``restore_archived_account``, 0018 funksiyası + bərpa sübutu; sübut = təşkilat + istifadəçi + sahib qərarı sha256).
``--admission-year`` verilsə yer-tutucu qəbul ili (1950) də düzəlir. DEFOLT DRY-RUN; stdout-a yalnız saylar.
"""

from __future__ import annotations

import hashlib
from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "restore_archived:"
_EVIDENCE_PREFIX = b"owner-restore-archived-student-v1\x00"
_AUDIT_REASON = "restore_archived_students (sahib 2026-10-27)"
#: Ortaq qaydanın rədd kodu → bu əmrin (prod-data-ops logunda görünən) sayğac açarı.
_SKIP_KEYS = {
    "not_archived": "skip_not_archived",
    "account_inactive": "skip_no_active_record",
    "no_active_record": "skip_no_active_record",
    "expelled_group": "skip_expelled_group",
    "membership_mismatch": "skip_membership_mismatch",
}


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
        from apps.accounts.public import ArchiveRestoreError, restore_wrongly_archived_student

        usernames = [name.strip() for name in str(options["usernames"]).split(",") if name.strip()]
        if not usernames or len(usernames) > 50:
            raise CommandError("restore_archived_usernames_required")
        year = int(options["admission_year"] or 0)
        if year and not 2000 <= year <= 2100:
            raise CommandError("restore_archived_admission_year_out_of_range")
        counts = Counter()
        User = get_user_model()
        Organization = django_apps.get_model("organizations", "Organization")
        try:
            with rls_worker_atomic(), bypass_rls(), transaction.atomic():
                organization = Organization.objects.get(slug=options["org"])
                actor = User.objects.get(username=options["actor"], is_active=True)
                for username in usernames:
                    user = User.objects.filter(username=username).select_related("profile").first()
                    if user is None or getattr(user, "profile", None) is None:
                        counts["skip_unknown"] += 1
                        continue
                    try:
                        outcome = restore_wrongly_archived_student(
                            user=user,
                            organization=organization,
                            actor=actor,
                            reason=_AUDIT_REASON,
                            admission_year=year or None,
                            digest=_digest(organization.pk, user.pk),
                        )
                    except ArchiveRestoreError as exc:
                        if exc.code not in _SKIP_KEYS:
                            raise CommandError(f"restore_archived_{exc.code}") from exc
                        counts[_SKIP_KEYS[exc.code]] += 1
                        continue
                    counts["restored" if outcome.restored else "already_active"] += 1
                    if outcome.admission_year_fixed:
                        counts["admission_year_fixed"] += 1
                if not options["apply"]:
                    raise _DryRun
        except _DryRun:
            counts["dry_run"] = 1
        for key in sorted(counts):
            self.stdout.write(f"{PREFIX} {key}={counts[key]}")
