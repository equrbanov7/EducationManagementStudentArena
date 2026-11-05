"""``merge_psychology_duplicates_20261106`` — Psixologiya 1-ci kurs: 11-05-də qalan dublikat cütləri (sahib 2026-11-06).

Sahib: «sənə göndərdiyim faylla sistemdəki qrup uşaqlarının sayı eyni olsun … əlavə olaraq kimisə saxlama orda».
11-05 birləşməsində (``merge_psychology_duplicates_20261105``) üç cüt ``duplicate_has_login`` ilə atlanmışdı — hər iki
hesabla giriş olub, tələbə indi ATİS hesabı ilə girir (son giriş ATİS-dədir) → ``allow_login`` ilə birləşir (xanalar
ATİS hesabına köçür, dublikat dondurulur). Dördüncü cüt (036 P ing) siyahıda «Makhmudova» yazılışı ilə tutulmamışdı.
``duplicate`` = delta hesabı, ``keep`` = ATİS hesabı; YALNIZ id-lər. İş :mod:`merge_duplicate_student`-dədir (eyni
qapılar, ``stmerge-…`` paketi, ``--undo``). DEFOLT DRY-RUN.
"""

from __future__ import annotations

import json
import os
import tempfile

from django.core.management import call_command
from django.core.management.base import BaseCommand

#: (duplicate — delta hesabı, keep — ATİS hesabı, dublikatın girişi olsa da birləşsin)
PAIRS = (
    (11371, 9428, False),
    (11037, 8880, True),
    (11049, 9323, True),
    (11052, 9352, True),
)
#: Ad yazılışı fərqlidir (Sabina «Makhmudova» / ATİS «Mahmudova») — sahib eyni şəxs kimi təsdiqləyib (2026-11-06).
ALLOW_NAME = frozenset({11371})


class Command(BaseCommand):
    help = "Psixologiya 1-ci kurs: 11-05-də qalan 4 dublikat cütünü ATİS hesabına birləşdirir (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        handle, path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                rows = [
                    {"duplicate": d, "keep": k, "allow_login": allow, "allow_name": d in ALLOW_NAME}
                    for d, k, allow in PAIRS
                ]
                json.dump({"format": "student-merge/1", "pairs": rows}, stream)
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
