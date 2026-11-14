"""``remove_pre_semester_lessons_20261114`` — semestrdən əvvəlki dərslər yenidən silinir + müəllimə bildiriş.

Sahib 2026-11-14: «ayın 15-dən əvvələ müəllim nə isə dərs yazıbsa silinsin və müəllimə də bildiriş kimi göndər ki,
ayın 15-dən əvvələ dərs yazılıbdı deyə». Qaydalar 11-08 qaçışı ilə eynidir (:mod:`apps.registrar.pre_semester_lessons`:
cari semestr, ``date < start_date``, rəsmi düzəlişli dərs qalır, hamısı audit-də). Bu qaçışın audit sətirləri ÖZ
``REASON`` mətni ilədir — ``--undo`` yalnız bu əmrin sildiklərini qaytarır (11-08 qaçışına toxunmur), bildirişlər
geri götürülmür.

``--notify`` — silinən dərslərin müəllimlərinə (dərsin müəllimi → jurnalın müəllimi → dərsi yaradan) hərəsinə BİR
daxili bildiriş: jurnal(lar), silinən tarixlər (gg.aa.iiii) və səbəb. Bildiriş silmə ilə eyni tranzaksiyadadır — yalnız
silmə commit olunanda görünür; dry-run-da yazılmır, amma ``teachers_notified`` «göndəriləcək» sayı göstərir.
Defolt dry-run; stdout-a YALNIZ saylar (ad yoxdur).
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError

from ... import pre_semester_lessons as service
from .relocate_twin_enrollment import run_plan

PREFIX = "pre_semester:"
REASON = "Sahib 2026-11-14: semestrin başlanğıcından əvvəl tarixli dərslər yenidən silindi (müəllimə bildirişlə)"


def failure_code(exc: Exception) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"pre_semester_failed_{slug}"[:120]


class Command(BaseCommand):
    help = (
        "Sahib 2026-11-14: semestrin başlanğıcından əvvəl tarixli dərslər (xanaları ilə) silinir, --notify ilə "
        "müəllimə bildiriş (defolt dry-run)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--notify", action="store_true", help="Hər müəllimə bir daxili bildiriş")
        parser.add_argument("--undo", action="store_true", help="Bu əmrin sildiklərini audit izinə görə qaytar")

    def handle(self, *args, **options):
        if options["undo"] and options["notify"]:
            raise CommandError("pre_semester_undo_does_not_notify")

        def runner(organization, actor, counts):
            if options["undo"]:
                service.undo(organization, actor, counts, reason=REASON)
                return
            removed = service.remove(organization, actor, counts, reason=REASON)
            if options["notify"]:
                service.notify_teachers(organization, removed, counts)

        try:
            run_plan(self, options=options, prefix=PREFIX, runner=runner)
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız CommandError kodunu göstərir
            raise CommandError(failure_code(exc)) from None
