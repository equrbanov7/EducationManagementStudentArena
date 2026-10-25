"""``audit_staff_placement`` — müəllim/heyət yerləşdirmə auditi və düzəlişi (sahib 2026-10-25; DRY-RUN DEFOLT).

Sahib: «Kafedraların verdiyi siyahıdakı müəllimləri yoxla — həmin kafedranın altında olsun, başqasına düşməsin …
dekan, kafedra müdiri, laborant düzgündürmü … dərs yükü olan hər rol (dekan, tədris işçisi, imtahan mərkəzi
işçisi) müəllim profili kimi də görünsün … aktiv olmayanları blokla, kafedra deaktiv görsün.»

Mənbələr (şəxsi data — repoya DÜŞMÜR): ``--forma7`` (Forma 7), ``--structure`` (struktur/heyət siyahısı),
``--load FAYL=KAFEDRA`` (kafedranın dərs yükü faylı, təkrarlanır) və ya hamısı bir ``--bundle`` zip-də (bax
``staff_placement.sources``). Plan: ``staff_placement.plan``.

* defolt — YALNIZ saylar (stdout), adlı hesabat ``--report`` (0600 Markdown) / ``--details`` (0600 CSV);
* ``--apply`` — ``JOIN`` / ``PRIMARY`` / ``DEACTIVATE`` (paket ``placement-…``, ``--undo`` ilə geri);
* ``--block-inactive`` (``--apply`` ilə) — Forma 7-də olmayan, dərs yükü/cari jurnalı OLMAYAN, struktur/yük
  faylında adı keçməyən müəllim hesablarını ``reconcile_teacher_roster``-in MÖVCUD mexanizmi ilə bloklayır
  (inzibati rollar qorunur; paket ``roster-…`` — ``reconcile_teacher_roster --undo`` ilə geri).

Qapılar: ``--apply`` ilə ``--reason`` (≥20 simvol); repetisiya markeri olmayan bazada
``--i-know-this-is-production``. Təkrar ``--apply`` → 0 yazı (idempotent).
"""

from __future__ import annotations

import io
import pathlib

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.services.staff_placement import apply as placement_apply
from apps.accounts.services.staff_placement import plan as placement_plan
from apps.accounts.services.staff_placement import report as placement_report
from apps.accounts.services.staff_placement import sources as placement_sources
from apps.accounts.services.teacher_roster import apply as roster_apply
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

from .reconcile_teacher_roster import _chair_overrides, _disposable_database


def _load_pairs(values):
    pairs = []
    for value in values or []:
        if "=" not in value:
            raise CommandError(f"placement_load_invalid: {value!r} («fayl.xlsx=Kafedra adı» formatı)")
        path, chair = value.rsplit("=", 1)
        pairs.append((pathlib.Path(path.strip()).expanduser().read_bytes(), chair.strip(), pathlib.Path(path).name))
    return pairs


class Command(BaseCommand):
    help = "Heyət yerləşdirmə auditi: Forma 7 + struktur siyahısı + yük faylları ↔ sistem (dry-run defolt)."

    def add_arguments(self, parser):
        parser.add_argument("--organization", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--forma7", default="", help="Forma 7 (.xlsx)")
        parser.add_argument("--structure", default="", help="Struktur/heyət siyahısı (.xlsx)")
        parser.add_argument("--load", action="append", default=[], help="«fayl.xlsx=Kafedra adı» (təkrarlana bilər)")
        parser.add_argument("--bundle", default="", help="zip + manifest.json (bax staff_placement.sources)")
        parser.add_argument("--chair-map", action="append", default=[], help="«Fayldakı kafedra=Sistemdəki bölmə»")
        parser.add_argument("--academic-year", default="2026/2027", help="Tədris ili (dərs yükü üçün)")
        parser.add_argument("--report", default="", help="Adlı Markdown hesabat yolu (0600)")
        parser.add_argument("--details", default="", help="Adlı CSV yolu (0600)")
        parser.add_argument("--apply", action="store_true", help="Düzəlişləri YAZ (defolt: yalnız hesabat)")
        parser.add_argument("--block-inactive", action="store_true", help="--apply: aktiv olmayanları blokla")
        parser.add_argument("--undo", default="", help="placement-… paketini geri qaytar")
        parser.add_argument("--reason", default="", help="Qərarın səbəbi (≥20 simvol) — --apply ilə məcburi")
        parser.add_argument("--actor", default="", help="Aktorun istifadəçi adı (defolt: təşkilatın sahibi)")
        parser.add_argument("--i-know-this-is-production", action="store_true", help="Markersiz bazada icazə")

    def handle(self, *args, **options):
        organization = (
            django_apps.get_model("organizations", "Organization")
            .objects.filter(slug=str(options["organization"]).strip())
            .first()
        )
        if organization is None:
            raise CommandError(f"placement_organization_unknown: {options['organization']!r}")
        user_model = django_apps.get_model("auth", "User")
        username = str(options["actor"] or "").strip()
        actor = user_model._default_manager.filter(username=username).first() if username else organization.owner
        if actor is None:
            raise CommandError(f"placement_actor_unknown: {username!r}")
        writes = bool(options["apply"] or options["undo"])
        if writes and not (_disposable_database() or options["i_know_this_is_production"]):
            raise CommandError("placement_target_not_disposable: real bazada --i-know-this-is-production verin.")
        if options["block_inactive"] and not options["apply"]:
            raise CommandError("placement_block_requires_apply: --block-inactive yalnız --apply ilə")
        with rls_worker_atomic(), bypass_rls():
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            if options["undo"]:
                try:
                    result = placement_apply.undo(options["undo"].strip(), actor=actor, reason=options["reason"])
                except roster_apply.RosterError as error:
                    raise CommandError(f"placement_{error.code}: {error.message}") from None
                self.stdout.write(f"GERİ QAYTARILDI — {options['undo']}: {result}")
                return
            self._run(organization, actor, options)

    def _sources(self, organization, options):
        from apps.organizations.models import OrgUnit
        from apps.organizations.public import kafedra_unit_types

        forma7 = structure = None
        loads = _load_pairs(options["load"])
        overrides = _chair_overrides(options["chair_map"])
        if options["bundle"]:
            try:
                forma7, structure, bundle_loads, bundle_map = placement_sources.read_bundle(options["bundle"])
            except placement_sources.SourceError as error:
                raise CommandError(f"placement_{error.code}: {error.message}") from None
            loads += bundle_loads
            overrides = {**bundle_map, **overrides}
        if options["forma7"]:
            forma7 = pathlib.Path(options["forma7"]).expanduser().read_bytes()
        if options["structure"]:
            structure = pathlib.Path(options["structure"]).expanduser().read_bytes()
        if forma7 is None and structure is None and not loads:
            raise CommandError("placement_no_sources: --forma7 / --structure / --load və ya --bundle verin")
        kafedra_types = kafedra_unit_types(organization)
        units = list(OrgUnit.objects.filter(organization=organization, is_active=True))
        chairs = [unit for unit in units if unit.unit_type in kafedra_types]
        result = placement_sources.Sources()
        if forma7 is not None:
            placement_sources.read_forma7(forma7, chairs, overrides, result)
        if structure is not None:
            placement_sources.read_structure(structure, units, kafedra_types, result)
        for blob, chair, label in loads:
            placement_sources.read_load(blob, chair, chairs, overrides, result, label=label)
        return result, forma7, overrides

    def _block_plan(self, organization, forma7, overrides, plan, year):
        if forma7 is None:
            return None
        from apps.accounts.services.teacher_roster.parsing import read_workbook
        from apps.accounts.services.teacher_roster.plan import build_plan

        roster = read_workbook(io.BytesIO(forma7))
        return build_plan(
            organization,
            roster,
            academic_year=year,
            chair_overrides=overrides,
            protect_ids=placement_plan.protect_ids(plan),
            workload=False,
        )

    def _run(self, organization, actor, options):
        year = options["academic_year"]
        sources, forma7, overrides = self._sources(organization, options)
        plan = placement_plan.build(organization, sources, academic_year=year)
        block_plan = self._block_plan(organization, forma7, overrides, plan, year)
        for key, value in placement_report.summary(plan, block_plan).items():
            self.stdout.write(f"  {key:32s} {value}")
        if options["report"]:
            placement_report.write_private(options["report"], placement_report.render_markdown(plan, block_plan))
            self.stdout.write("Hesabat yazıldı (0600).")
        if options["details"]:
            from core.export_safety import safe_csv_writer

            buffer = io.StringIO()
            safe_csv_writer(buffer).writerows(placement_report.details_rows(plan))
            placement_report.write_private(options["details"], buffer.getvalue())
        if not options["apply"]:
            self.stdout.write("\n(DRY-RUN — heç nə yazılmadı. Yazmaq üçün --apply --reason … verin.)")
            return
        try:
            result = placement_apply.execute(plan, actor=actor, reason=options["reason"])
        except roster_apply.RosterError as error:
            raise CommandError(f"placement_{error.code}: {error.message}") from None
        self.stdout.write(
            f"\nYAZILDI — paket {result['batch']}: üzvlük əlavə {len(result['join'])}, əsas kafedra "
            f"{len(result['primary'])}, deaktiv {len(result['deactivate'])}.\n"
            f"Geri qaytarma: manage.py audit_staff_placement --organization {organization.slug} --undo {result['batch']}"
        )
        if options["block_inactive"] and block_plan is not None:
            blocked = roster_apply.execute(
                block_plan, actor=actor, reason=options["reason"], do_updates=False, do_blocks=True
            )
            self.stdout.write(
                f"BLOKLANDI — paket {blocked['batch']}: {len(blocked['blocked'])} (alınmadı {len(blocked['failed'])}). "
                f"Geri: manage.py reconcile_teacher_roster --organization {organization.slug} --undo {blocked['batch']}"
            )
