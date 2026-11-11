"""``merge_duplicate_subjects_20261111`` — dublikat fənlərin köklü həlli (sahib 2026-11-11). DEFOLT DRY-RUN.

Sahib: «Kompüterlərin diaqnostikası iki kartdadır, tələbədə iki kart … bütün dublikatları həll et, fənn kodu səhv
düşənləri də, standart olsun bir; imtahan verən hər kəs nəticəsini jurnalda görsün.» Əməliyyatlar (sıra ilə):

* ``journals`` / ``catalogue`` / ``codes`` — :mod:`apps.registrar.duplicate_subjects_2026_11_11` (jurnal birləşməsi
  heç bir xana / bal itirmədən, fənn kartlarının birləşməsi, kodların vahid ``QKU-N`` standartı);
* ``takers`` — imtahan vermiş, amma jurnalda olmayan tələbələr jurnala (alt qrup tələbəsi kimi, sənədsiz) əlavə
  olunur və nəticələri yazılır (:mod:`apps.exams.services.journal_missing_takers`);
* ``report`` — heç nə yazmır: qoruyucu saylar (tələbənin ikiqat kartı, eyni adlı kartlar, qeyri-standart kodlar).

Əmr exams app-ındadır, çünki registrar imtahan modellərini import etmir (modul sərhədi). Bütün DB işi
``rls_worker_atomic()`` + ``bypass_rls()`` + RLS konteksti altındadır; dry-run EYNİ kodu icra edib geri qaytarır.

TƏHLÜKƏSİZLİK: ``--apply`` YALNIZ açıq addımla (``--only journals|catalogue|codes|takers``) və ya ``--undo`` ilə işləyir —
hər addım ayrıca yazılır, ayrıca paket id-si alır və ayrıca geri qaytarılır (tərs sıra ilə: takers → codes →
catalogue → journals). ``--undo --batch <id>`` paketi TAM geri qaytarır və ya heç nə yazmır (``takers`` paketində
yalnız toxunulmamış yerləşdirmələr azad olunur). Kataloqun avtomatik (eyni ad + kredit + növ + kafedra) qrupları
yalnız ``--auto-catalogue`` ilə; defolt — yalnız plandakı açıq qruplar.
Stdout-a YALNIZ saylar (``twin_merge: açar=say …``; açarlarda rəqəm yoxdur); gözlənilməz xəta
``CommandError: duplicate_subjects_failed_<sinif>_<mətn>``.
"""

from __future__ import annotations

import re
from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.exams.services import journal_missing_takers
from apps.registrar.public import duplicate_subjects_2026_11_11 as duplicates
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "twin_merge:"
OPS = (*duplicates.OPS, "takers")


def failure_code(exc: Exception) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"duplicate_subjects_failed_{slug}"[:120]


class Command(BaseCommand):
    help = "Sahib 2026-11-11: dublikat fənlər (jurnal + kataloq + kod) və jurnalda olmayan imtahan iştirakçıları."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--only", choices=(*OPS, "report"), help="Yalnız bir əməliyyat (defolt: hamısı)")
        parser.add_argument("--batch", default="", help="Paket id-si (dupsubj-…); --undo üçün məcburi")
        parser.add_argument("--undo", action="store_true", help="--batch paketini geri qaytar")
        parser.add_argument(
            "--auto-catalogue",
            action="store_true",
            help="catalogue: planda olmayan eyni adlı (kredit + növ + kafedra eyni) kartları da birləşdir",
        )

    def _undo(self, organization, actor, counts, batch) -> None:
        found = journal_missing_takers.undo(organization=organization, actor=actor, counts=counts, batch=batch)
        if duplicates.has_batch(organization, batch):
            exam_ids = duplicates.undo(organization=organization, actor=actor, counts=counts, batch=batch)
            self._resync(exam_ids, counts)
        elif not found:
            raise CommandError("duplicate_subjects_batch_unknown")

    @staticmethod
    def _resync(exam_ids, counts) -> None:
        """Jurnal bağı geri qayıdan imtahanların rəsmi cəhdləri yenidən sinxronlaşır (köhnəlmiş avtomatik bal qalmasın)."""
        from apps.exams.models import Exam
        from apps.exams.services import exam_journal_link

        for exam in Exam.objects.filter(pk__in=[int(value) for value in exam_ids], is_deleted=False):
            exam_journal_link.resync_exam_journal(exam, notify=False)
            counts["undo_exams_resynced"] += 1

    def _run(self, options, counts, lines) -> str:
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        only = options["only"]
        ops = OPS if only is None else (() if only == "report" else (only,))
        batch = str(options["batch"] or "").strip()
        Organization = django_apps.get_model("organizations", "Organization")
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("duplicate_subjects_organization_unknown")
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            with transaction.atomic():
                if options["undo"]:
                    self._undo(organization, actor, counts, batch)
                else:
                    batch = batch or duplicates.new_batch_id()
                    registrar_ops = tuple(op for op in ops if op in duplicates.OPS)
                    if registrar_ops:
                        duplicates.run(
                            organization=organization,
                            actor=actor,
                            counts=counts,
                            ops=registrar_ops,
                            batch=batch,
                            lines=lines,
                            auto_catalogue=bool(options["auto_catalogue"]),
                        )
                    else:
                        duplicates.report(organization=organization, counts=counts)
                    if "takers" in ops:
                        journal_missing_takers.run(
                            organization=organization,
                            actor=actor,
                            counts=counts,
                            period=duplicates.current_period(organization),
                            batch=batch,
                            lines=lines,
                            allowed_exams=duplicates.PLAN.get("takers_exams") or (),
                        )
                if not options["apply"]:
                    transaction.set_rollback(True)
        return batch

    def handle(self, *args, **options):
        batch = str(options["batch"] or "").strip()
        if batch and not duplicates.BATCH_RE.match(batch):
            raise CommandError("duplicate_subjects_batch_invalid")
        if options["undo"] and not batch:
            raise CommandError("duplicate_subjects_undo_needs_batch")
        if options["apply"] and not options["undo"] and options["only"] not in OPS:
            # Dörd addımı birdən yazmaq olmaz: hər addımın dry-run-u oxunmalı, hər biri ayrıca geri qaytarıla bilməlidir.
            raise CommandError("duplicate_subjects_apply_needs_explicit_step")
        counts, lines = Counter(), []
        try:
            batch = self._run(options, counts, lines)
        except CommandError:
            raise
        except duplicates.Stop as exc:
            raise CommandError(str(exc)) from None
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız CommandError kodunu göstərir
            raise CommandError(failure_code(exc)) from None
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        for line in lines:
            self.stdout.write(f"{PREFIX} {line}")
        if counts:
            self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))
        if batch and options["apply"] and not options["undo"]:
            self.stdout.write(f"{PREFIX} batch={batch}")
