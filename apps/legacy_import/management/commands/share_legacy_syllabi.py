"""``share_legacy_syllabi`` — köhnə sistemdə bir neçə jurnalın işlətdiyi BİR sillabus (sahib 2026-10-27; dry-run DEFAULT).

    manage.py share_legacy_syllabi --bundle delta.json.gz --organization qku                  # dry-run (geri qaytarılır)
    manage.py share_legacy_syllabi --bundle delta.json.gz --organization qku --teacher ad.soyad
    manage.py share_legacy_syllabi --bundle delta.json.gz --organization qku --apply --i-know-this-is-production

Artıq köçürülmüş data üçün FILL-ONLY təmir: köhnə sistemdə eyni sillabusu işlədən jurnallardan biri köçmüş
sillabusu göstərir, digəri isə «sillabus yoxdur» deyirsə, ikincisi birincinin dosyesinə SURƏTSİZ bağlanır
(``SyllabusShare``, ``source=legacy``). Sillabusu olan jurnal toxunulmur, başqa müəllimin sillabusu paylaşılmır.
Qaydalar ``apps/legacy_import/services/delta/syllabi_share.py``-dadır; icra ``legacy_delta_apply`` ilə EYNİ
orkestratordur (bir tranzaksiya, dry-run sonda geri qaytarılır, apply-da ``legacy_import.delta_batch`` audit sətri
— ``created.syllabus_shares`` = bağlanan açılışların id-ləri).

Paket — istənilən ``legacy_delta_extract`` çıxışı (adi delta və ya ``--teacher-syllabi``; jurnalların ``groups_id``-si
və ``groups`` bölməsi DOLU olmalıdır). Stdout-a YALNIZ saylar: bir ``syllabi_share: açar=say …`` sətri.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.legacy_import.services.delta.apply import execute
from apps.legacy_import.services.delta.bundle import BundleError, file_sha256, read_bundle
from apps.legacy_import.services.delta.syllabi_backfill import TeacherSyllabiPhaseMismatch
from apps.legacy_import.services.delta.syllabi_share import COUNTER_KEYS, PHASE
from apps.legacy_import.services.repair_support import (
    add_repair_arguments,
    assert_writable_target,
    resolve_actor,
    resolve_organization,
)
from core.rls_pooling import rls_worker_atomic

PREFIX = "syllabi_share:"


def _bundle_has_groups(bundle: dict) -> bool:
    journals = bundle.get("journals") or []
    return bool(bundle.get("groups")) and any(str(row.get("groups_id") or "[]") != "[]" for row in journals)


class Command(BaseCommand):
    help = "Köhnə sistemin «bir sillabus — bir neçə jurnal» faktını sillabussuz jurnallara paylaşır (dry-run default)."

    def add_arguments(self, parser):
        add_repair_arguments(parser)
        parser.add_argument("--bundle", required=True, help="legacy_delta_extract paketi (.json.gz)")
        parser.add_argument("--expected-sha256", default="", help="Paketin gözlənilən sha256-sı (fail-closed)")
        parser.add_argument("--teacher", default="", help="Yalnız bu müəllimin (istifadəçi adı) jurnalları")

    def handle(self, *args, **options):
        if options["apply"] and options["dry_run"]:
            raise CommandError("legacy_repair_mode_conflict: --apply və --dry-run birlikdə verilə bilməz")
        path = options["bundle"]
        if options["expected_sha256"] and file_sha256(path) != options["expected_sha256"].strip().lower():
            raise CommandError("syllabi_share_bundle_digest_mismatch")
        try:
            bundle = read_bundle(path)
        except BundleError as error:
            raise CommandError(str(error)) from None
        if not _bundle_has_groups(bundle):
            raise CommandError("syllabi_share_bundle_without_groups")
        import datetime

        from django.contrib.auth import get_user_model

        with rls_worker_atomic():
            if options["apply"]:
                assert_writable_target(allow_production=bool(options["i_know_this_is_production"]))
            organization = resolve_organization(options["organization"])
            actor = resolve_actor(organization, options["actor"])
            teacher_id = None
            if options["teacher"].strip():
                teacher_id = (
                    get_user_model()
                    .objects.filter(username=options["teacher"].strip())
                    .values_list("pk", flat=True)
                    .first()
                )
                if teacher_id is None:
                    raise CommandError("syllabi_share_teacher_unknown")
            try:
                run = execute(
                    organization=organization,
                    actor=actor,
                    bundle=bundle,
                    apply=bool(options["apply"]),
                    until=datetime.date.today(),
                    phases=(PHASE,),
                    setup=lambda delta_run: setattr(delta_run, "share_teacher_id", teacher_id),
                )
            except TeacherSyllabiPhaseMismatch as error:
                raise CommandError(str(error)) from None
        counters = run.summary()["counters"]
        pairs = [("mode", "apply" if options["apply"] else "dry_run")]
        pairs += [(key, counters.get(f"{PHASE}.{key}", 0)) for key in COUNTER_KEYS]
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in pairs))
