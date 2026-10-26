"""``unblock_legacy_journal_teachers`` — köhnə sistemdə bu semestr jurnal aparan müəllimin «Forma 7» blokunu açır.

Sahib 2026-10-26: «kimdəsə köhnə sistemdə jurnal varsa, adına nə isə aparıbsa onu bloklama — o profilləri də aktiv
et, jurnallarında görsünlər və daxil olsunlar». «Forma 7» idxalı (``reconcile_teacher_roster`` / staff placement)
yeni sistemdə dərs yükü / jurnal sahibliyi olmayan müəllimi «işdən ayrılıb» kimi bloklamışdı — halbuki köhnə
sistemin jurnalları başqa müəllimin açılışına birləşdiyi üçün onun adına açılış yox idi.

Sübut faylı (lokal qurulur, ad/FİN YOXDUR, açarlar prod-un id-ləridir)::

    {"format": "legacy-teachers/1", "teachers": [{"user": 123, "journals": 2, "points": 405, "dates": 29}, ...]}

Yalnız: hesab bloklu + blok «Forma 7» idxalınındır (``[roster-`` izi və ``employment_ended`` kodu) + köhnə jurnalda
İŞ var (xana və ya dərs tarixi > 0; ``--include-empty`` ilə boş jurnal da). Əl ilə (təhlükəsizlik, intizam, ikinci
hesab …) qoyulan bloklar AÇILMIR — sayılır. Yazı rəsmi ``unblock_account`` ilə (audit). DEFOLT DRY-RUN.
Stdout-a YALNIZ saylar.
"""

from __future__ import annotations

import json
from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.services.account_deletion import AccountDeletionError, unblock_account
from apps.accounts.services.teacher_roster.apply import BLOCK_REASON_CODE
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "legacy_teachers_unblock:"
FORMAT = "legacy-teachers/1"
REASON = (
    "Köhnə sistemdə cari semestr jurnalı var (jurnal datası) — «Forma 7» bloku açıldı, sahibin 2026-10-26 tapşırığı"
)


def _roster_block(profile) -> bool:
    if profile is None:
        return False
    return "[roster-" in (profile.block_reason or "") and (profile.block_reason_code or "") == BLOCK_REASON_CODE


class Command(BaseCommand):
    help = "Köhnə sistemdə bu semestr jurnal aparan müəllimlərin «Forma 7» blokunu açır (sübut faylı ilə)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--file", required=True, help="legacy-teachers/1 JSON faylı")
        parser.add_argument("--include-empty", action="store_true", help="İşsiz (boş) köhnə jurnalı olanı da aç")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        try:
            with open(options["file"], encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            raise CommandError("legacy_teachers_file_unreadable") from None
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise CommandError("legacy_teachers_format_unknown")
        Organization = django_apps.get_model("organizations", "Organization")
        User = get_user_model()
        counts = Counter()
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("legacy_teachers_organization_unknown")
            actor = User.objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
            if actor is None:
                raise CommandError("actor_must_be_active_superuser")
            rows = [row for row in data.get("teachers") or [] if isinstance(row, dict)]
            users = User.objects.select_related("profile").in_bulk(
                [int(row["user"]) for row in rows if str(row.get("user", "")).isdigit()]
            )
            member_ids = set(
                django_apps.get_model("organizations", "Membership")
                .objects.filter(organization=organization, user_id__in=list(users))
                .values_list("user_id", flat=True)
            )
            with transaction.atomic():
                for row in rows:
                    counts["in_file"] += 1
                    user = users.get(int(row.get("user") or 0))
                    if user is None or user.pk not in member_ids:
                        counts["user_missing"] += 1
                        continue
                    if user.is_active:
                        counts["already_active"] += 1
                        continue
                    if not _roster_block(getattr(user, "profile", None)):
                        counts["manual_block_kept"] += 1
                        continue
                    worked = int(row.get("points") or 0) + int(row.get("dates") or 0) > 0
                    if not worked and not options["include_empty"]:
                        counts["empty_journal_kept"] += 1
                        continue
                    try:
                        unblock_account(user, actor=actor, reason=REASON)
                    except AccountDeletionError:
                        counts["unblock_refused"] += 1
                        continue
                    counts["unblocked"] += 1
                if not options["apply"]:
                    transaction.set_rollback(True)
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))
