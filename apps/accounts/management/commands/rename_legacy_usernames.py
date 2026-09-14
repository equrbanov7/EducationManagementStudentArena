"""``rename_legacy_usernames`` — `myedu.<növ>.<id>` → real `ad.soyad` istifadəçi adları.

Dry-run DEFAULT-dur; qayda `apps.accounts.services.username_repair` sənədindədir.

    manage.py rename_legacy_usernames --report /tmp/usernames.csv
    manage.py rename_legacy_usernames --report /tmp/usernames.csv --apply

Hesabat CSV: `user_id,old,new,source` (sirr yoxdur — yalnız istifadəçi adları).
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.services import username_repair
from core.export_safety import safe_csv_writer
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Legacy `myedu.*` istifadəçi adlarını `ad.soyad` (və ya universitetin verdiyi hesab) ilə əvəz edir."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Yaz (defolt: yalnız plan)")
        parser.add_argument("--report", type=str, default="", help="Plan CSV faylı (user_id,old,new,source)")
        parser.add_argument("--show", type=int, default=25, help="Ekranda göstəriləcək nümunə sətir sayı")

    def handle(self, *args, **options):
        User = get_user_model()
        with rls_worker_atomic(), bypass_rls():
            candidates, reserved = username_repair.load_candidates_and_reserved(User)
            rows = username_repair.plan_renames(candidates, reserved)
            counters = Counter(row.source for row in rows)
            changed = [row for row in rows if row.new != row.old]
            suffixed = sum(
                1 for row in changed if row.new[-1:].isdigit() and row.source != username_repair.SOURCE_FALLBACK
            )

            self.stdout.write(
                f"Legacy hesab: {len(candidates)} · dəyişəcək: {len(changed)} · "
                f"universitet hesabı: {counters[username_repair.SOURCE_INSTITUTIONAL]} · "
                f"ad.soyad: {counters[username_repair.SOURCE_NAME]} · "
                f"nömrəli təkrar: {suffixed} · adsız (hesab<id>): {counters[username_repair.SOURCE_FALLBACK]} · "
                f"artıq düzgün: {counters[username_repair.SOURCE_KEEP]}"
            )
            for row in changed[: options["show"]]:
                self.stdout.write(f"  {row.old:>24} → {row.new:<32} [{row.source}]")

            if options["report"]:
                path = Path(options["report"])
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = safe_csv_writer(handle)
                    writer.writerow(["user_id", "old", "new", "source"])
                    writer.writerows(username_repair.iter_report_rows(rows))
                self.stdout.write(f"Hesabat: {path}")

            if not options["apply"]:
                self.stdout.write(self.style.WARNING("DRY-RUN — heç nə yazılmadı (--apply ilə yazılır)."))
                return

            written = username_repair.apply_plan(User, rows)
            # Yazıdan sonra unikallıq sübutu — toqquşma olsa DB indeksi onsuz da atardı.
            distinct = User.objects.values("username").distinct().count()
            total = User.objects.count()
            if distinct != total:
                raise CommandError(f"username_uniqueness_violated: {distinct} != {total}")
            self.stdout.write(self.style.SUCCESS(f"Yazıldı: {written} istifadəçi adı dəyişdirildi."))
