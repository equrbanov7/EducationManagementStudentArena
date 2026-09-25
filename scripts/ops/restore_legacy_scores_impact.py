"""J12 təmirinin NƏTİCƏYƏ təsiri — planın toxunduğu BÜTÜN qeydiyyatlar (oxu-yalnız).

İstifadə (``manage.py shell``-ə ötürülür; heç nə yazmır)::

    RESTORE_IMPACT_PLAN=<plan>.jsonl.gz RESTORE_IMPACT_PLAN_SHA256=<sha> \\
    RESTORE_IMPACT_OUT=/tmp/impact_before.csv python manage.py shell < scripts/ops/restore_legacy_scores_impact.py

Tətbiqdən ƏVVƏL və SONRA işlədilir, iki CSV müqayisə olunur
(``RESTORE_IMPACT_BEFORE=<əvvəlki csv>`` verilərsə müqayisə dərhal çap olunur).
Hər sətir: qeydiyyat pk-sının qısa hash-i + giriş/yekun/hərf/keçid/davamiyyət/qayıb
saatı — ad YOX.  CSV repoya DÜŞMÜR.
"""

import csv
import hashlib
import os
from collections import Counter

from django.apps import apps as django_apps

from apps.legacy_import.services.repair_lesson_recovery import REPAIR_KEY
from apps.legacy_import.services.repair_plan_file import read_plan
from apps.registrar import finals
from core.rls import bypass_rls

PLAN = os.environ["RESTORE_IMPACT_PLAN"]
SHA = os.environ["RESTORE_IMPACT_PLAN_SHA256"]
OUT = os.environ.get("RESTORE_IMPACT_OUT", "/tmp/restore_impact.csv")
BEFORE = os.environ.get("RESTORE_IMPACT_BEFORE", "")
FIELDS = ("entry_score", "total", "letter", "passed", "failed", "attendance_score", "status_code", "absence_hours")

plan = read_plan(PLAN, expected_sha256=SHA, repair=REPAIR_KEY)
wanted = sorted({mark["enrollment_id"] for mark in plan.of("mark")})
Enrollment = django_apps.get_model("registrar", "Enrollment")
rows = {}
with bypass_rls():
    for start in range(0, len(wanted), 500):
        chunk = Enrollment.objects.filter(pk__in=wanted[start : start + 500]).select_related(
            "offering__assessment_scheme", "offering__subject"
        )
        for enrollment in chunk:
            result = finals.compute_final_result(enrollment=enrollment)
            key = hashlib.sha256(str(enrollment.pk).encode()).hexdigest()[:16]
            rows[key] = {
                "enrollment": key,
                **{field: result.get(field) for field in FIELDS if field != "absence_hours"},
                "absence_hours": enrollment.absence_hours,
            }

with open(OUT, "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=("enrollment", *FIELDS))
    writer.writeheader()
    writer.writerows(rows[key] for key in sorted(rows))
print(f"restore_impact: {len(rows)} qeydiyyat → {OUT}")

if BEFORE:
    with open(BEFORE, encoding="utf-8") as handle:
        before = {row["enrollment"]: row for row in csv.DictReader(handle)}
    changed: Counter = Counter()
    for key, row in rows.items():
        old = before.get(key)
        if old is None:
            changed["əvvəl yox idi"] += 1
            continue
        for field in FIELDS:
            if str(row[field]) != str(old[field]):
                changed[field] += 1
        if str(row["passed"]) != str(old["passed"]) or str(row["failed"]) != str(old["failed"]):
            changed[f"keçid {old['passed']}/{old['failed']} → {row['passed']}/{row['failed']}"] += 1
    print("dəyişən sahələr (qeydiyyat sayı):")
    for field, count in sorted(changed.items()):
        print(f"  {field}: {count}")
