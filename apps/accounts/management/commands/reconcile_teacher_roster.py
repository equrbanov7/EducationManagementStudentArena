"""``reconcile_teacher_roster`` — «Forma 7» aktiv müəllim siyahısını hesablarla tutuşdurur (sahib 2026-10-11).

Sahib: «Sənə aktiv olaraq olan bütün müəllimləri atdım — hal-hazırda kim işləyirsə o. Digər hesablar
bloklanıb dayandırılacaq.»

NƏ EDİR (``apps.accounts.services.teacher_roster``):
    * faylı oxuyur (kafedra blokları; ad / elmi dərəcə / ştat normallaşdırılır);
    * hər sətri mövcud hesabla tutuşdurur (soyad + ad + ata adı; eyni kafedra üstün) — tapıldı / çox mənalı /
      ata adı fərqli / oxşar / yoxdur; defolt YENİ HESAB YARATMIR (yoxdursa hesabatda siyahı);
    * tapılanlara: ``UserProfile.academic_title/academic_degree`` (fərq varsa) və illik yük profili
      (vəzifə / ştat payı / saathesabı) — kafedra fərqi YALNIZ hesabatdır, köçürmə yoxdur;
    * ``--create-missing`` ilə YALNIZ «hesab yoxdur» sətirlərinə FİN-siz müəllim hesabı yaradır (kafedra
      üzvlüyü, elmi ad/dərəcə, yük profili; parol yoxdur — RİM verir, və ya ``--credentials-out`` 0600 CSV);
    * siyahıda olmayan MÜƏLLİM hesablarını mövcud «Hesabı dayandır» servisi ilə bloklayır (səbəb «İşdən
      ayrılıb / müqavilə bitib», müraciət «Kadrlar şöbəsi»); inzibati rol daşıyanlar, sahib, superuser və
      tələbələr HEÇ VAXT bloklanmır.

Qapılar: DEFOLT DRY-RUN; ``--apply`` ilə ``--reason`` (≥20 simvol) MƏCBURİDİR; repetisiya markeri olmayan
bazada ``--i-know-this-is-production`` tələb olunur. Hər ``--apply`` paket id-si verir; ``--undo <paket>``
onu geri qaytarır. Təkrar ``--apply`` idempotentdir (dəyişməyən yazılmır, bloklu yenidən bloklanmır).

İstifadə::

    manage.py reconcile_teacher_roster forma7.xlsx --organization qku --report /tmp/roster.md
    manage.py reconcile_teacher_roster forma7.xlsx --organization qku --apply \\
        --reason "Forma 7 (2026/2027) aktiv müəllim siyahısı — sahibin 2026-10-11 tapşırığı" \\
        --actor <rim.istifadəçi> --i-know-this-is-production
    manage.py reconcile_teacher_roster --organization qku --undo roster-20261011-101500-ab12 \\
        --actor <rim.istifadəçi> --i-know-this-is-production
"""

from __future__ import annotations

import csv
import pathlib

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.accounts.services.teacher_roster import apply as roster_apply
from apps.accounts.services.teacher_roster import report as roster_report
from apps.accounts.services.teacher_roster.parsing import read_workbook
from apps.accounts.services.teacher_roster.plan import build_plan
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

REHEARSAL_GUC = "emsarena.rehearsal_target"
REHEARSAL_VALUE = "disposable"


def _disposable_database() -> bool:
    if connection.vendor != "postgresql":
        return True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting(%s, true)", [REHEARSAL_GUC])
            row = cursor.fetchone()
    except Exception:  # noqa: BLE001 — marker oxuna bilmirsə baza «real» sayılır (fail-closed)
        return False
    return bool(row) and str(row[0] or "").strip() == REHEARSAL_VALUE


def _chair_overrides(values) -> dict:
    overrides = {}
    for value in values or []:
        if "=" not in value:
            raise CommandError(f"roster_chair_map_invalid: {value!r} («Fayldakı ad=Sistemdəki ad» formatı)")
        left, right = value.split("=", 1)
        overrides[left.strip()] = right.strip()
    return overrides


class Command(BaseCommand):
    help = "«Forma 7» müəllim siyahısını hesablarla tutuşdurur: hesabat (defolt), --apply, --undo <paket>."

    def add_arguments(self, parser):
        parser.add_argument("xlsx", nargs="?", default="", help="Forma 7 Excel faylı (.xlsx)")
        parser.add_argument("--organization", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--sheet", default="", help="Vərəq adı (defolt: «Aktiv - Passiv» və ya birinci)")
        parser.add_argument("--academic-year", default="", help="Tədris ili (defolt: fayldan, yoxsa 2026/2027)")
        parser.add_argument(
            "--chair-map", action="append", default=[], help="«Fayldakı kafedra=Sistemdəki bölmə» (təkrarlana bilər)"
        )
        parser.add_argument("--protect", action="append", default=[], help="Heç vaxt bloklanmayacaq istifadəçi adı")
        parser.add_argument("--report", default="", help="Markdown hesabatın yolu")
        parser.add_argument("--details", default="", help="Tam siyahı CSV yolu (şəxsi məlumat — lokal saxlayın)")
        parser.add_argument("--max-names", type=int, default=10, help="Hesabatda kateqoriya başına ad sayı")
        parser.add_argument("--apply", action="store_true", help="Dəyişiklikləri YAZ (defolt: yalnız hesabat)")
        parser.add_argument("--skip-blocks", action="store_true", help="--apply: bloklamanı ötür")
        parser.add_argument("--skip-updates", action="store_true", help="--apply: profil/yük yeniləməsini ötür")
        parser.add_argument(
            "--create-missing",
            action="store_true",
            help="«Hesab yoxdur» sətirlərinə FİN-siz müəllim hesabı yarat (yalnız bu kateqoriya)",
        )
        parser.add_argument(
            "--credentials-out",
            default="",
            help="--create-missing --apply: birdəfəlik parolların CSV yolu (0600); verilməsə hesablar parolsuz yaranır",
        )
        parser.add_argument("--undo", default="", help="Paketi geri qaytar (paket id-si)")
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
            raise CommandError(f"roster_organization_unknown: {options['organization']!r}")
        actor = self._actor(organization, options["actor"])
        writes = bool(options["apply"] or options["undo"])
        if writes and not (_disposable_database() or options["i_know_this_is_production"]):
            raise CommandError(
                f"roster_target_not_disposable: bazada {REHEARSAL_GUC}='{REHEARSAL_VALUE}' markeri yoxdur — "
                "real bazada --i-know-this-is-production verin."
            )
        with rls_worker_atomic(), bypass_rls():
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            if options["undo"]:
                self._undo(options["undo"], actor, options["reason"])
                return
            self._run(organization, actor, options)

    def _actor(self, organization, username):
        user_model = django_apps.get_model("auth", "User")
        username = str(username or "").strip()
        actor = user_model._default_manager.filter(username=username).first() if username else organization.owner
        if actor is None:
            raise CommandError(f"roster_actor_unknown: {username!r}")
        return actor

    def _run(self, organization, actor, options):
        path = pathlib.Path(options["xlsx"] or "").expanduser()
        if not options["xlsx"] or not path.exists():
            raise CommandError(f"roster_file_not_found: {str(path)!r}")
        try:
            roster = read_workbook(path, options["sheet"])
        except ValueError as exc:
            raise CommandError(f"roster_{exc}") from None
        year = options["academic_year"] or roster.academic_year or "2026/2027"
        user_model = django_apps.get_model("auth", "User")
        protect_ids = set(
            user_model._default_manager.filter(username__in=options["protect"]).values_list("pk", flat=True)
        )
        plan = build_plan(
            organization,
            roster,
            academic_year=year,
            chair_overrides=_chair_overrides(options["chair_map"]),
            protect_ids=protect_ids,
        )
        if options["create_missing"]:
            from apps.accounts.services.teacher_roster.create import plan_new_accounts

            plan.new_accounts = plan_new_accounts(plan)
        elif options["credentials_out"]:
            raise CommandError("roster_credentials_without_create: --credentials-out yalnız --create-missing ilə")
        self._print_summary(plan)
        if options["report"]:
            pathlib.Path(options["report"]).expanduser().write_text(
                roster_report.render_markdown(plan, max_names=max(0, options["max_names"])), encoding="utf-8"
            )
            self.stdout.write(f"Hesabat: {options['report']}")
        if options["details"]:
            with pathlib.Path(options["details"]).expanduser().open("w", encoding="utf-8", newline="") as handle:
                csv.writer(handle).writerows(roster_report.details_csv_rows(plan))
            self.stdout.write(f"Tam siyahı: {options['details']}")
        if not options["apply"]:
            self.stdout.write("\n(DRY-RUN — heç nə yazılmadı. Yazmaq üçün --apply --reason … verin.)")
            return
        try:
            result = roster_apply.execute(
                plan,
                actor=actor,
                reason=options["reason"],
                do_updates=not options["skip_updates"],
                do_blocks=not options["skip_blocks"],
                keep_passwords=bool(options["credentials_out"]),
            )
        except roster_apply.RosterError as error:
            raise CommandError(f"roster_{error.code}: {error.message}") from None
        if result["credentials"]:
            from apps.accounts.services.teacher_roster.create import write_credentials

            write_credentials(options["credentials_out"], result["credentials"])
            self.stdout.write(f"Birdəfəlik parollar (0600): {options['credentials_out']}")
        self.stdout.write(
            f"\nYAZILDI — paket {result['batch']}: yeni hesab {len(result['created'])}, profil "
            f"{len(result['profiles'])}, yük profili "
            f"{len(result['workload'])}, bloklandı {len(result['blocked'])}, alınmadı {len(result['failed'])}.\n"
            f"Geri qaytarma: manage.py reconcile_teacher_roster --organization {organization.slug} "
            f"--undo {result['batch']}"
        )

    def _undo(self, batch_id, actor, reason):
        try:
            result = roster_apply.undo(batch_id.strip(), actor=actor, reason=reason)
        except roster_apply.RosterError as error:
            raise CommandError(f"roster_{error.code}: {error.message}") from None
        self.stdout.write(
            f"GERİ QAYTARILDI — paket {batch_id}: blokdan çıxdı {len(result['unblocked'])}, "
            f"profil {result['profiles']}, yük profili {result['workload']}, ötürüldü {len(result['skipped'])}."
        )
        created = result.get("created") or {}
        if created:
            self.stdout.write(
                f"  yaradılmış hesablar: silindi {len(created['deleted'])}, bloklandı (istifadə olunub) "
                f"{len(created['deactivated'])}, toxunulmadı {len(created['kept'])}."
            )

    def _print_summary(self, plan):
        data = roster_report.summary(plan)
        self.stdout.write(
            f"=== Forma 7 — {plan.organization.slug} · {plan.academic_year} · "
            f"{data['rows']} sətir / {data['chairs']} kafedra ==="
        )
        for status in roster_report.STATUS_ORDER:
            self.stdout.write(f"  {roster_report.STATUS_LABELS[status]:42s} {data['statuses'].get(status, 0)}")
        self.stdout.write(f"  {'uyğun hesab (unikal)':42s} {data['matched_accounts']}")
        for flag, count in sorted(data["flags"].items()):
            self.stdout.write(f"    · {flag:38s} {count}")
        self.stdout.write(f"  profil sahəsi dəyişəcək: {data['profile_fields']} · yük profili: {data['workload']}")
        self.stdout.write(
            f"  BLOKLANACAQ: {data['block']} · qorunan: {data['protected']} {data['protected_reasons']} · "
            f"onsuz da bloklu: {data['already_blocked']}"
        )
        if data["create"] is not None:
            self.stdout.write(f"  YENİ HESAB yaradılacaq (FİN-siz, «hesab yoxdur»): {data['create']}")
        for chair, mapped in plan.chair_map.items():
            unit = mapped["unit"]
            self.stdout.write(f"    kafedra «{chair}» → {unit[1] if unit else '—'} ({mapped['score']:.2f})")
