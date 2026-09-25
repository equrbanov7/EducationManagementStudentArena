"""Tələbə görünüşünün yoxlanması — J12 təmirindən ƏVVƏL və SONRA (2026-09-25).

İstifadə (``manage.py shell``-ə ötürülür; PROD NÜSXƏSİNDƏ İŞLƏTMƏYİN — giriş
sessiya sətri yazır; yalnız atılabilən klonda və ya tətbiqdən sonra serverdə)::

    RESTORE_VERIFY_PLAN=<plan>.jsonl.gz RESTORE_VERIFY_PLAN_SHA256=<sha> \\
    RESTORE_VERIFY_OUT=/tmp/restore_verify_after.csv RESTORE_VERIFY_STUDENTS=8 \\
    python manage.py shell < scripts/ops/restore_legacy_scores_verify.py

Nə edir:
* planın xana aldığı qeydiyyatlardan ən çox RƏQƏMLİ bal bərpa olunan N AKTİV
  tələbəni seçir (+ ən çox qayıb bərpa olunan N/2);
* hər biri üçün ``finals.compute_final_result`` (giriş/yekun/hərf/davamiyyət)
  və transkriptin kumulyativ ÜOMG-si hesablanır;
* test klienti ilə ``force_login`` edib «Fənlərim» / «Nəticələrim» / «Ümumi
  tədris məlumatı» bölmələrini render edir (status + xəta axtarışı);
  köçürülmüş hesablar ilk girişdə ``/accounts/set-password/``-ə yönləndirilir
  (``password_change_required``) — klon repetisiyasında seçilən tələbələr üçün
  bu bayraq əvvəlcədən ayrıca SQL ilə söndürülür: ``RESTORE_VERIFY_LIST_ONLY=1``
  seçilən istifadəçi pk-larını çap edib ÇIXIR (skript özü heç nə dəyişmir);
* nəticə CSV-yə yazılır — ad YOX, yalnız qeydiyyat/istifadəçi pk-sının qısa
  hash-i (PII çıxmır).  CSV repoya DÜŞMÜR.
"""

import csv
import hashlib
import os
from collections import Counter

from django.apps import apps as django_apps
from django.test import Client

from apps.legacy_import.services.repair_lesson_recovery import REPAIR_KEY
from apps.legacy_import.services.repair_plan_file import read_plan
from apps.registrar import finals, transcript
from core.rls import bypass_rls

PLAN = os.environ["RESTORE_VERIFY_PLAN"]
SHA = os.environ["RESTORE_VERIFY_PLAN_SHA256"]
OUT = os.environ.get("RESTORE_VERIFY_OUT", "/tmp/restore_verify.csv")
COUNT = int(os.environ.get("RESTORE_VERIFY_STUDENTS", "8"))
SECTIONS = ("my-subjects", "my-results", "overall-academic")
HOST = os.environ.get("RESTORE_VERIFY_HOST", "localhost")
LIST_ONLY = os.environ.get("RESTORE_VERIFY_LIST_ONLY") == "1"


def _short(value) -> str:
    return hashlib.sha256(str(value).encode()).hexdigest()[:10]


plan = read_plan(PLAN, expected_sha256=SHA, repair=REPAIR_KEY)
scores: Counter = Counter()
absences: Counter = Counter()
for mark in plan.of("mark"):
    if mark["score"] is not None:
        scores[mark["enrollment_id"]] += 1
    if mark["status"] == "absent":
        absences[mark["enrollment_id"]] += 1

Enrollment = django_apps.get_model("registrar", "Enrollment")
Profile = django_apps.get_model("accounts", "UserProfile")
StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")

rows = []
with bypass_rls():
    touched = set(scores) | set(absences)
    enrollments = {
        str(item.pk): item
        for item in Enrollment.objects.filter(pk__in=sorted(touched)).select_related("student", "offering__subject")
    }
    active = set(
        Profile.objects.filter(
            user_id__in={e.student_id for e in enrollments.values()}, access_state="active"
        ).values_list("user_id", flat=True)
    )
    chosen, seen = [], set()
    # Əvvəl ən çox rəqəmli bal, sonra ən çox qayıb bərpa olunan AKTİV tələbələr.
    for ranking, quota in ((scores, COUNT), (absences, COUNT // 2)):
        picked = 0
        for pk, _count in sorted(ranking.items(), key=lambda item: (-item[1], item[0])):
            item = enrollments.get(pk)
            if item is None or item.student_id not in active or item.student_id in seen:
                continue
            seen.add(item.student_id)
            chosen.append(item)
            picked += 1
            if picked >= quota:
                break
    if LIST_ONLY:
        print("restore_verify_users:", ",".join(str(item.student_id) for item in chosen))
        raise SystemExit(0)
    for item in chosen:
        result = finals.compute_final_result(enrollment=item)
        record = StudentAcademicRecord.objects.filter(student=item.student).select_related("program").first()
        data = transcript.build_student_transcript(
            student=item.student, organization=item.organization, program=record.program if record else None
        )
        rows.append(
            {
                "enrollment": _short(item.pk),
                "student": _short(item.student_id),
                "subject_code": item.offering.subject.code,
                "restored_scores": scores.get(str(item.pk), 0),
                "restored_absences": absences.get(str(item.pk), 0),
                "absence_hours": item.absence_hours,
                "entry_score": result["entry_score"],
                "exam": result["effective_exam"],
                "total": result["total"],
                "letter": result["letter"],
                "passed": result["passed"],
                "failed": result["failed"],
                "attendance_score": result["attendance_score"],
                "status_code": result["status_code"],
                "cumulative_uomg": data.get("cumulative_gpa"),
                "uomg_available": data.get("cumulative_gpa_available"),
                "_user": item.student,
            }
        )

for row in rows:
    client = Client(HTTP_HOST=HOST)
    client.force_login(row.pop("_user"))
    for section in SECTIONS:
        response = client.get("/accounts/profile/", {"section": section}, follow=False)
        body = response.content.decode("utf-8", "replace") if response.status_code == 200 else ""
        row[f"http_{section}"] = response.status_code
        if response.status_code in (301, 302):
            row[f"http_{section}"] = f"{response.status_code}→{response.get('Location', '')}"
        row[f"err_{section}"] = int("Traceback" in body or "Server Error" in body)

fields = [key for key in (rows[0].keys() if rows else [])]
with open(OUT, "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
print(f"restore_verify: {len(rows)} tələbə → {OUT}")
for row in rows:
    print(
        f"  {row['student']} {row['subject_code']:>10} bal+{row['restored_scores']:<3} qb+{row['restored_absences']:<3} "
        f"giriş={row['entry_score']} yekun={row['total']} {row['letter']} ÜOMG={row['cumulative_uomg']} "
        + " ".join(f"{section}={row[f'http_{section}']}" for section in SECTIONS)
    )
