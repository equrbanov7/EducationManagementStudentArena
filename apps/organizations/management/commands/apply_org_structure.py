"""Təşkilat strukturunu plan JSON-una görə yeni formaya salır — DRY-RUN defolt.

    manage.py apply_org_structure --org qku --plan scripts/data/qku_structure_2026_09_27.json
    manage.py apply_org_structure --org qku --plan … --apply

Məntiq və qaydalar: :mod:`apps.organizations.structure_plan` (köhnə ad/yer
``settings.history``-də qalır, idempotentdir).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.organizations.structure_plan import apply_structure_plan, load_plan
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Struktur planını tətbiq edir (vahid adı/yeri, yeni vahidlər, ixtisas köçürməsi) — dry-run defolt."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilat slug-ı")
        parser.add_argument("--plan", required=True, help="Plan JSON faylı")
        parser.add_argument("--apply", action="store_true", help="Yaz (defolt: yalnız hesabat)")
        parser.add_argument("--actor", default="", help="Audit üçün istifadəçi adı (opsional)")

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model

        from apps.organizations.models import Organization

        try:
            plan = load_plan(options["plan"])
        except (OSError, ValueError) as exc:
            raise CommandError(f"Plan oxunmadı: {exc}") from exc
        with rls_worker_atomic():
            organization = Organization.objects.filter(slug=options["org"]).first()
            if organization is None:
                raise CommandError(f"Təşkilat tapılmadı: {options['org']}")
            actor = None
            if options["actor"]:
                actor = get_user_model().objects.filter(username=options["actor"]).first()
            with transaction.atomic():
                report = apply_structure_plan(organization, plan, apply=options["apply"], actor=actor)
                if report.problems and options["apply"]:
                    transaction.set_rollback(True)
        self.stdout.write(f"\n=== STRUKTUR PLANI · {organization.name} · {plan.get('source')} ===")
        for line in report.lines:
            self.stdout.write(f"  {line}")
        self.stdout.write("\nXülasə: " + ", ".join(f"{k} {v}" for k, v in sorted(report.counts.items())))
        if report.problems:
            self.stdout.write(
                self.style.ERROR("PROBLEMLƏR (apply geri qaytarıldı):" if options["apply"] else "PROBLEMLƏR:")
            )
            for problem in report.problems:
                self.stdout.write(f"  · {problem}")
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("\nDRY-RUN — heç nə yazılmadı. Yazmaq üçün: --apply"))
        elif not report.problems:
            self.stdout.write(self.style.SUCCESS("\n✓ Struktur planı tətbiq olundu."))
