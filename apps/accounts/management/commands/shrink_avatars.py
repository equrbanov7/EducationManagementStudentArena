"""Mövcud profil şəkillərini (avatar) kiçilt — PERF-2 H5 (2026-10-17).

Yeni yükləmələr artıq ``apps/accounts/services/avatar_image.py`` ilə ≤512 px WebP-yə
çevrilir. Bu əmr KÖHNƏ faylları eyni qaydaya salır.

DEFOLT QURU QAÇIŞDIR — heç nə yazmır, yalnız nəyin dəyişəcəyini və qənaəti çap edir.

* ``--apply`` — yeni WebP faylı ``avatars/`` altına yazır və profili ona yönəldir
  (``QuerySet.update`` — ``updated_at`` dəyişmir, siqnal işləmir). Köhnə fayl
  SİLİNMİR (geri qaytarmaq üçün diskdə qalır).
* ``--delete-originals`` (yalnız ``--apply`` ilə) — köhnə faylı da silir.
* Ötürülür: artıq ≤512 px VƏ ``--min-bytes``-dan (defolt 150 KB) kiçik fayl, və ya yeni
  kodlaşdırma köhnədən kiçik olmayan fayl (format fərq etmir). Piksel tavanını aşan fayl «xəta».
* ``--limit`` — ən çox N profil (sınaq üçün).

İstifadə::

    manage.py shrink_avatars                      # hesabat
    manage.py shrink_avatars --apply --limit 20   # ilk 20 faylı çevir
"""

from __future__ import annotations

import warnings
from pathlib import Path
from uuid import uuid4

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from PIL import Image

from apps.accounts.models import UserProfile
from apps.accounts.services.avatar_image import AVATAR_FORMAT_EXTENSION, AVATAR_MAX_SIDE, encode_avatar_bytes
from apps.accounts.services.profile_avatar import AVATAR_PREFIX
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


def _kb(value: int) -> str:
    return f"{value / 1024:.0f} KB"


class Command(BaseCommand):
    help = "Köhnə avatar fayllarını ≤512 px WebP-yə kiçilt (defolt: quru qaçış, --apply ilə yazır)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Faylları çevir və profilləri yönəlt")
        parser.add_argument(
            "--delete-originals", action="store_true", help="--apply ilə: köhnə faylı da sil (geri dönüş yoxdur)"
        )
        parser.add_argument("--min-bytes", type=int, default=150 * 1024, help="Bundan kiçik kiçik şəkillər ötürülür")
        parser.add_argument("--limit", type=int, default=0, help="Ən çox N profil (0 = hamısı)")

    def handle(self, *args, **options):
        apply = options["apply"]
        delete_originals = apply and options["delete_originals"]
        with rls_worker_atomic(), bypass_rls():
            queryset = UserProfile.objects.exclude(avatar="").exclude(avatar__isnull=True).order_by("pk")
            if options["limit"]:
                queryset = queryset[: options["limit"]]
            rows = [(profile.pk, str(profile.avatar.name or "")) for profile in queryset.only("pk", "avatar")]
        storage = UserProfile._meta.get_field("avatar").storage

        counts = {"converted": 0, "skipped": 0, "missing": 0, "failed": 0}
        saved_bytes = 0
        for pk, name in rows:
            if not name.startswith(AVATAR_PREFIX) or not storage.exists(name):
                counts["missing"] += 1
                continue
            try:
                size = storage.size(name)
                with storage.open(name, "rb") as handle:
                    with warnings.catch_warnings():
                        warnings.simplefilter("error", Image.DecompressionBombWarning)
                        with Image.open(handle) as probe:  # yalnız başlıq — dekod yoxdur
                            small = max(probe.size) <= AVATAR_MAX_SIDE
                    if small and size < options["min_bytes"]:
                        counts["skipped"] += 1  # artıq kiçik və yüngül — formatdan asılı olmayaraq
                        continue
                    handle.seek(0)
                    data = encode_avatar_bytes(handle)  # piksel tavanı + «bomba» qoruması daxilində
            except Exception as exc:  # noqa: BLE001 — bir zədəli / nəhəng fayl əmri dayandırmamalıdır
                counts["failed"] += 1
                self.stderr.write(f"  ! {name}: {exc}")
                continue
            if len(data) >= size:
                counts["skipped"] += 1  # yeni kodlaşdırma kiçik deyil — dəyişməyə dəyməz
                continue

            counts["converted"] += 1
            saved_bytes += size - len(data)
            self.stdout.write(f"  {name}: {_kb(size)} → {_kb(len(data))}")
            if not apply:
                continue
            new_name = storage.save(f"{AVATAR_PREFIX}{uuid4().hex}{AVATAR_FORMAT_EXTENSION}", ContentFile(data))
            with rls_worker_atomic(), bypass_rls():
                updated = UserProfile.objects.filter(pk=pk, avatar=name).update(avatar=new_name)
            if not updated:  # arada istifadəçi şəkli dəyişib — yeni faylı at, köhnəyə toxunma
                storage.delete(new_name)
                continue
            if delete_originals and Path(name).name != Path(new_name).name:
                storage.delete(name)

        mode = "TƏTBİQ OLUNDU" if apply else "QURU QAÇIŞ (heç nə yazılmadı; --apply ilə yazılır)"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: çevriləcək/çevrilən {counts['converted']}, ötürülən {counts['skipped']}, "
                f"fayl yoxdur {counts['missing']}, xəta {counts['failed']}; qənaət ≈ {_kb(saved_bytes)}"
            )
        )
