"""``merge_psychology_duplicates_20261105`` — Psixologiya məktəbi 1-ci kurs dublikat hesabları (sahib 2026-11-05).

Sahib: «bu qruplardakı uşaqlar səhv düşübdü … uşaqları düzgün yerlərə bərpa etmək» (rəsmi siyahı: 036ing, 136Sİ ing,
036, 136Sİ-1, 136Sİ-2, 136TSPX). Kök səbəb: hər tələbənin İKİ aktiv hesabı — ATİS (2026-09-19) + köhnə sistem deltası
(2026-10-23) — eyni qrupda; qruplar ikiqat görünürdü. 49 cüt (``duplicate`` = delta hesabı, ``keep`` = ATİS hesabı)
rəsmi siyahıdakı ad + soyad + ata adı ilə tutuşdurulub (YALNIZ id-lər, şəxsi məlumat yoxdur).

İş :mod:`merge_duplicate_student`-ə ötürülür (plan faylı müvəqqəti yaradılır): eyni plan qapıları (ad, FİN, doğum
tarixi, dublikatın girişi olmamalı, delta-yaradılmış olmalı), eyni ``stmerge-…`` paketi və ``--undo``. DEFOLT DRY-RUN.
"""

from __future__ import annotations

import json
import os
import tempfile

from django.core.management import call_command
from django.core.management.base import BaseCommand

#: (duplicate — delta hesabı, keep — ATİS hesabı)
PAIRS = (
    (10968, 8458),
    (10990, 8518),
    (10991, 8531),
    (10993, 8571),
    (10994, 8593),
    (10995, 8634),
    (10996, 8685),
    (10997, 8729),
    (11743, 8730),
    (10998, 8786),
    (10999, 8812),
    (11000, 8875),
    (11001, 9022),
    (11744, 9024),
    (11002, 9054),
    (11745, 9111),
    (11003, 9127),
    (11004, 9135),
    (11006, 9193),
    (11007, 9197),
    (11009, 9219),
    (11012, 9281),
    (11017, 9296),
    (11018, 9310),
    (11020, 9325),
    (11022, 9372),
    (11030, 8524),
    (11031, 8550),
    (11032, 8552),
    (11033, 8711),
    (11034, 8714),
    (11035, 8789),
    (11036, 8853),
    (11037, 8880),
    (11038, 8908),
    (11039, 8970),
    (11043, 9212),
    (11046, 9284),
    (11048, 9306),
    (11049, 9323),
    (11050, 9329),
    (11052, 9352),
    (11056, 9354),
    (11751, 9367),
    (11060, 9408),
    (11102, 9142),
    (11103, 9177),
    (11104, 9178),
    (11042, 9156),
)


class Command(BaseCommand):
    help = "Psixologiya 1-ci kurs: delta dublikat hesablarını ATİS hesabına birləşdirir (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        handle, path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(
                    {"format": "student-merge/1", "pairs": [{"duplicate": d, "keep": k} for d, k in PAIRS]}, stream
                )
            extra = ["--apply"] if options["apply"] else []
            call_command(
                "merge_duplicate_student",
                "--org",
                options["org"],
                "--actor",
                options["actor"],
                "--file",
                path,
                *extra,
                stdout=self.stdout,
            )
        finally:
            os.unlink(path)
