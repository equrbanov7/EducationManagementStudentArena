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
Hər qaçışın paket id-si var; ``--undo --batch <id>`` jurnal + kataloq + kod addımlarını geri qaytarır (``takers``
yerləşdirmələri rəsmi tarixçə sətirləridir — «Alt qrup yerləşdirməsi» tarixçəsindən geri götürülür).
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
                    duplicates.undo(organization=organization, actor=actor, counts=counts, batch=batch)
                else:
                    registrar_ops = tuple(op for op in ops if op in duplicates.OPS)
                    if registrar_ops:
                        batch = duplicates.run(
                            organization=organization,
                            actor=actor,
                            counts=counts,
                            ops=registrar_ops,
                            batch=batch,
                            lines=lines,
                        )
                    else:
                        duplicates.report(organization=organization, counts=counts)
                    if "takers" in ops:
                        journal_missing_takers.run(
                            organization=organization,
                            actor=actor,
                            counts=counts,
                            period=duplicates.current_period(organization),
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
