"""Canlı imtahan ES modullarının nisbi importları versiyalı olmalıdır (2026-09-29).

Niyə: prod-da nginx ``/static/``-i ``Cache-Control: public, immutable`` + 30 gün ilə verir, Django-nun
``CompressedManifestStaticFilesStorage``-i isə modul daxilindəki ``import './audio.js'`` yollarını hash-li
adlara ÇEVİRMİR. Versiyasız import deploy-dan sonra brauzerin köhnə modulunu (30 günə qədər) yeni kodla
qarışdırır → ``SyntaxError: does not provide an export named …`` → host/oyunçu ekranı boş qalır.

Qayda: ``host_lobby/`` və ``player/`` qrafındakı BÜTÜN nisbi importlar EYNİ ``?v=`` tokenini daşıyır
(fərqli token eyni modulun iki nüsxəsini yükləyər → paylaşılan vəziyyət parçalanar). Modul dəyişəndə
token hər yerdə birlikdə yenilənir (məs. ``sed -i '' 's/?v=lx20260929/?v=lxYYYYMMDD/g'``).
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

STATIC_JS = Path(__file__).resolve().parents[1] / "static" / "js"
GRAPHS = ("host_lobby", "player")
IMPORT_RE = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(\s*|\bimport\s+)(['"])(\.{1,2}/[^'"]+)\1""")


class LiveModuleImportVersionTest(SimpleTestCase):
    def _specifiers(self):
        for graph in GRAPHS:
            for path in sorted((STATIC_JS / graph).glob("*.js")):
                for match in IMPORT_RE.finditer(path.read_text(encoding="utf-8")):
                    yield path.relative_to(STATIC_JS), match.group(2)

    def test_every_relative_import_is_versioned_with_one_token(self):
        tokens = set()
        unversioned = []
        for path, spec in self._specifiers():
            version = re.search(r"\?v=([A-Za-z0-9_.-]+)$", spec)
            if not version:
                unversioned.append(f"{path}: {spec}")
            else:
                tokens.add(version.group(1))
        self.assertEqual(unversioned, [], "versiyasız nisbi import (keş qarışıqlığı riski)")
        self.assertLessEqual(len(tokens), 1, f"fərqli versiya tokenləri: {sorted(tokens)}")

    def test_imported_files_exist(self):
        for path, spec in self._specifiers():
            target = (STATIC_JS / path).parent / spec.split("?", 1)[0]
            with self.subTest(module=str(path), spec=spec):
                self.assertTrue(target.resolve().is_file(), f"{spec} tapılmadı")
