"""``recode_site_subjects`` — qalan ``SAYT-####`` fənn kartlarını ``QKU-N``-ə keçirir (sahib 2026-11-04). DEFOLT DRY-RUN.

Qaydalar: :mod:`apps.registrar.subject_recode`. İş sırası: əvvəlcə ``merge_subjects`` (plan rejimi — SAYT kartları
mənbə), sonra bu əmr. Stdout: ``köhnə → yeni`` kod siyahısı + ``site_recode: açar=say …`` xülasəsi.

İstifadə::

    python manage.py recode_site_subjects --org qku                       # dry-run
    python manage.py recode_site_subjects --org qku --exclude SAYT-0012   # gözləyən birləşmələri saxla
    python manage.py recode_site_subjects --org qku --apply
    python manage.py recode_site_subjects --org qku --undo sitecode-20261104-120000-ab12 --apply
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...subject_codes import SITE_CODE_RE
from ...subject_recode import RecodeError, apply_recode, new_batch_id, plan, undo_recode

PREFIX = "site_recode:"


class Command(BaseCommand):
    help = "Qalan SAYT-#### fənn kartlarını növbəti boş QKU-N koduna keçirir (kart id-si dəyişmir; defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--exclude", default="", help="toxunulmayacaq SAYT kodları, vergüllə")
        parser.add_argument("--undo", default="", help="geri qaytarılacaq paket (sitecode-…)")
        parser.add_argument("--apply", action="store_true", help="faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        exclude = [code.strip() for code in options["exclude"].split(",") if code.strip()]
        if any(not SITE_CODE_RE.match(code) for code in exclude):
            raise CommandError("site_recode_exclude_invalid")
        Organization = django_apps.get_model("organizations", "Organization")
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("site_recode_organization_unknown")
            try:
                with transaction.atomic():
                    if options["undo"]:
                        items = undo_recode(organization, options["undo"].strip())
                        for item in items:
                            self.stdout.write(f"  {item['new']} → {item['old']}")
                        summary = {"undone": len(items)}
                        batch = options["undo"].strip()
                    else:
                        result = plan(organization, exclude=exclude)
                        batch = new_batch_id()
                        for item in result["items"]:
                            self.stdout.write(f"  {item['old']} → {item['new']}  {item['name'][:80]}")
                        for code in result["has_qku_duplicate"]:
                            self.stdout.write(f"  {code}: QKU dublikatı var — əvvəl merge_subjects")
                        if result["items"]:
                            apply_recode(organization, result["items"], batch=batch)
                        summary = dict(result["counts"])
                    if not options["apply"]:
                        transaction.set_rollback(True)
            except RecodeError as exc:
                raise CommandError(f"site_recode_{exc}") from None
        mode = "apply" if options["apply"] else "dry_run"
        self.stdout.write(f"{PREFIX} mode={mode} batch={batch if options['apply'] else 'none'}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(summary.items())))
