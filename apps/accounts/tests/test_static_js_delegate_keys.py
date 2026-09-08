"""`EMSDelegate.on(event, selector)` açarları fayllar arasında TƏKRARLANMAMALIDIR.

`static/js/ems_ajax_init.js` eyni «hadisə|seçici» açarını ikinci dəfə qeyd edəndə
əvvəlki dinləyicini ƏVƏZ EDİR (yığmır). 2026-09-08-də `teaching_office_groups.js`
`form[data-tof-form]` üçün «yenidən aç» qeydi əlavə edəndə `teaching_office.js`-in
JSON göndəriş dinləyicisini sildi — bütün kabinet dialoqları tam səhifə POST
etməyə başladı. Bu test həmin sinif reqressiyanı statik olaraq tutur: eyni açar
yalnız BİR faylda ola bilər (fayl daxilində təkrar — məs. EMSReady içində — normaldır).
"""

import re
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

_ON_CALL = re.compile(r'\.on\(\s*"([a-z]+)"\s*,\s*"([^"]+)"')


class DelegateKeyUniquenessTest(SimpleTestCase):
    def test_no_delegate_key_is_registered_from_two_files(self):
        base = Path(settings.BASE_DIR)
        roots = [base / "static" / "js", *base.glob("apps/*/static")]
        owners = defaultdict(set)
        for root in roots:
            for path in root.rglob("*.js"):
                text = path.read_text(encoding="utf-8", errors="ignore")
                if "EMSDelegate" not in text and "DELEGATE" not in text:
                    continue
                for event, selector in _ON_CALL.findall(text):
                    owners[(event, selector)].add(str(path.relative_to(base)))
        duplicates = {key: sorted(files) for key, files in owners.items() if len(files) > 1}
        self.assertEqual(duplicates, {}, f"eyni EMSDelegate açarı bir neçə faylda: {duplicates}")
