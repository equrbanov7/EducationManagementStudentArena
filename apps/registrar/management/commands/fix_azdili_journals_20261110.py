"""``fix_azdili_journals_20261110`` — Azərbaycan dili kafedrasının iki jurnal düzəlişi (sahib 2026-11-10, defolt dry-run).

1. **236 M ADİAK** («Azərbaycan dilində işgüzar və akademik kommunikasiya») — köhnə sistemdə qrup iki müəllimə
   bölünmüşdü (Hüseynzadə Vəfa + Məmmədova Solmaz). Digər dörd qrupda (KE / İT / EM / SBİO) paylar köhnə siyahılara
   bərabərdir; 236 M-də isə əvvəldən başqa siyahılar qalıb (``apply_first_year_splits_20261107`` → ``_conflict``).
   Sahib: «köhnədə necə idisə elə olsun» — hər iki payın siyahısı köhnə sistemin siyahısı ilə ƏVƏZ olunur (plan:
   ``first_year_splits_2026_11_07.json`` → ``shares.adiak_m``; yalnız id-lər). Siyahıda olmayan tələbə qrupsuz qalır
   (sahib görür).
2. **409/6MBA** — köhnə sistemdə jurnal (14926) «Akademik yazı və oxu» kartı ilə açılıb, amma onun sillabusu (7711)
   «Akademik yazı və etika» fənninindir; paralel 409/6MBA ing jurnalı və kafedranın rəsmi yük faylı da «etika»dır.
   Yəni dərslər səhv fənn kartının jurnalındadır. Dərsləri/xanaları olan «oxu» jurnalı (W) təsdiqli «etika»
   sillabusu olan rəsmi «etika» jurnalına (T, xanasız) birləşdirilir (:class:`apps.registrar.twin_merge.Merger`).
   Yük sətrinin fənni əvvəlcədən veb ilə «etika»ya dəyişdirilir (sinxron «oxu» jurnalını yenidən açmasın).

Stdout-a YALNIZ saylar (``lab_groups: açar=say …``). İdempotentdir.
"""

from __future__ import annotations

import re

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError

from ...first_year_splits_2026_11_07 import _audit, _enrolled, plan
from ...twin_merge import Merger
from .relocate_twin_enrollment import run_plan

PREFIX = "lab_groups:"
SPLIT_KEY = "adiak_m"
SECOND_TEACHER = 11608  # Məmmədova Solmaz (solmaz.memmedova3) — köhnə sistemdə işçi 1070
#: Səhv fənn kartındakı jurnal (Akademik yazı və oxu, dərslərlə) → rəsmi jurnal (Akademik yazı və etika, 409/6MBA).
TWIN_PAIRS = ({"source": "a8923008-f83e-408b-a37a-996d5c215797", "target": "6817a9ac-ffee-47a9-b6ba-4143c19238b6"},)


def split_m(*, organization, actor, counts) -> None:
    from ...journal_shares import forget

    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    JournalShare = django_apps.get_model("registrar", "JournalShare")
    spec = plan()["shares"][SPLIT_KEY]
    key = SPLIT_KEY
    offering = (
        CourseOffering.objects.select_for_update()
        .filter(organization=organization, pk=spec["offering"], is_active=True)
        .first()
    )
    if offering is None:
        counts[f"{key}_offering_missing"] += 1
        return
    if offering.instructor_id != spec["owner"]:
        counts[f"{key}_owner_changed_skipped"] += 1
        return
    rows = _enrolled(offering)
    owner_rows, other_rows = set(spec["owner_rows"]), set(spec["other_rows"])
    if not (owner_rows | other_rows) <= set(rows):
        counts[f"{key}_roster_changed_skipped"] += 1
        return
    active = list(JournalShare.objects.select_for_update().filter(offering=offering, is_active=True))
    own = next((share for share in active if share.teacher_id == offering.instructor_id), None)
    other = next((share for share in active if share.teacher_id == SECOND_TEACHER), None)
    counts[f"{key}_foreign_shares"] += sum(
        1 for share in active if share.teacher_id not in (offering.instructor_id, SECOND_TEACHER)
    )
    if own is None or other is None:
        counts[f"{key}_share_missing_skipped"] += 1
        return
    for share, wanted, side in ((own, owner_rows, "owner"), (other, other_rows, "other")):
        current = {str(pk) for pk in share.enrollments.values_list("pk", flat=True)}
        if current == wanted:
            counts[f"{key}_{side}_already"] += 1
            continue
        share.enrollments.set(wanted)
        counts[f"{key}_{side}_replaced"] += 1
        _audit(
            actor,
            organization,
            share,
            {"enrollments": sorted(current)},
            {"enrollments": sorted(wanted), "rule": "sahib 2026-11-10: köhnədə necə idisə"},
            str(share.pk),
        )
    counts[f"{key}_ungrouped"] += len(set(rows) - owner_rows - other_rows)
    forget(offering)


class Command(BaseCommand):
    help = (
        "Sahib 2026-11-10: 236 M ADİAK alt qrupları köhnə siyahı ilə + 409/6MBA boş əkiz birləşməsi (defolt dry-run)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        def runner(organization, actor, counts):
            split_m(organization=organization, actor=actor, counts=counts)
            Merger(organization=organization, actor=actor, counts=counts).run(list(TWIN_PAIRS))

        try:
            run_plan(self, options=options, prefix=PREFIX, runner=runner)
        except CommandError:
            raise
        except Exception as exc:  # prod-data-ops yalnız kodu göstərir
            raise CommandError(failure_code(exc)) from exc


def failure_code(exc) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"azdili_journals_failed_{slug}"[:120]
