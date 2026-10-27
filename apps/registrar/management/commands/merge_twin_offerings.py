"""``merge_twin_offerings`` — yanlış fənn adı altındakı «əkiz» açılışı rəsmi açılışa birləşdirir (RİM 2026-10-27).

MR-26, MR-29, MR-30.3 və ``LEGACY_DELTA_2026_10`` §10.4-ün qalan əkizləri. Qaydalar: :mod:`apps.registrar.twin_merge`.
Plan faylı (``twin-merge/1``, YALNIZ id-lər) lokal qurulur: ``python manage.py build_twin_repair_plans``. DEFOLT
DRY-RUN (eyni kod, geri qaytarılır). Stdout-a YALNIZ saylar (``twin_merge: açar=say …``).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from ...twin_merge import FORMAT, Merger
from .relocate_twin_enrollment import add_plan_arguments, load_plan, run_plan

PREFIX = "twin_merge:"


class Command(BaseCommand):
    help = "Yanlış fənn adı altındakı əkiz açılışı rəsmi açılışa birləşdirir (plan faylı ilə; defolt dry-run)."

    def add_arguments(self, parser):
        add_plan_arguments(parser, FORMAT)

    def handle(self, *args, **options):
        data = load_plan(options["file"], FORMAT, "twin_merge")

        def runner(organization, actor, counts):
            Merger(organization=organization, actor=actor, counts=counts).run(data.get("pairs") or [])

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
