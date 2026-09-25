"""Hazırda oxuyan tələbələrin kabinet görünüşü — bərpadan ƏVVƏL və SONRA (2026-09-25).

İstifadə (``manage.py shell``-ə ötürülür; YALNIZ atılabilən klonda — test klienti
giriş sessiyası yazır, transkript qurucusu çatışmayan sxemi tənbəl yaradır)::

    RESTORE_VERIFY_USERS=101,202,303 RESTORE_VERIFY_OUT=/tmp/current_verify_after.csv \\
    python manage.py shell < scripts/ops/restore_current_students_verify.py

Hər istifadəçi üçün:

* ``transcript.build_student_transcript`` — sətir sayı, qəti nəticəli sətir, ÜOMG
  (hesablanırmı), qazanılmış kredit; ``student_credit_totals`` («Fənlərim» kredit qutusu);
* test klienti ilə ``force_login`` → «Fənlərim» (``my-subjects``), «Nəticələrim»
  (``my-results``), «Ümumi tədris məlumatı» (``overall-academic``): HTTP status,
  xəta izi, səhifədə görünən akademik sətir sayı və ÜOMG mətni;
* ``access_state`` — arxivdəki tələbə üçün giriş bağlıdır (``user_access_is_login_blocked``),
  onda render yoxlanmır, sətir ``blocked`` yazılır.

Köçürülmüş hesablar ilk girişdə ``/accounts/set-password/``-ə yönləndirilir
(``password_change_required``) — klonda seçilən istifadəçilər üçün bu bayraq əvvəlcədən
ayrıca SQL ilə söndürülməlidir (skript özü heç bir istifadəçi sahəsini dəyişmir).
CSV-də ad YOXDUR — yalnız istifadəçi pk-sının qısa hash-i.  CSV repoya DÜŞMÜR.
"""

import csv
import hashlib
import os
import re

from django.apps import apps as django_apps
from django.test import Client

from apps.accounts.identity import user_access_is_login_blocked
from apps.organizations.models import Organization
from apps.registrar import transcript
from core.rls import bypass_rls

USERS = [int(value) for value in os.environ["RESTORE_VERIFY_USERS"].split(",") if value.strip()]
OUT = os.environ.get("RESTORE_VERIFY_OUT", "/tmp/restore_current_verify.csv")
HOST = os.environ.get("RESTORE_VERIFY_HOST", "localhost")
ORG_SLUG = os.environ.get("RESTORE_VERIFY_ORG", "qku")
SECTIONS = ("my-subjects", "my-results", "overall-academic")
_ROW = re.compile(r'class="oa-row[ "]')
_UOMG = re.compile(r'oa-summary-box--uomg">.*?class="oa-summary-n[^"]*"[^>]*>\s*([^<]+?)\s*<', re.S)
_ACADEMIC = re.compile(r'results_type=academic[^>]*>\s*[^<]*<span class="tab-count">(\d+)</span>', re.S)


def _short(value) -> str:
    return hashlib.sha256(str(value).encode()).hexdigest()[:10]


def _first(pattern, text, default=""):
    match = pattern.search(text)
    return match.group(1).strip() if match else default


organization = Organization.objects.get(slug=ORG_SLUG)
User = django_apps.get_model("auth", "User")
Profile = django_apps.get_model("accounts", "UserProfile")
rows = []
with bypass_rls():
    users = {user.pk: user for user in User.objects.filter(pk__in=USERS)}
    states = dict(Profile.objects.filter(user_id__in=USERS).values_list("user_id", "access_state"))
    for pk in USERS:
        user = users.get(pk)
        if user is None:
            rows.append({"student": _short(pk), "access_state": "no account"})
            continue
        data = transcript.build_student_transcript(student=user, organization=organization)
        record_rows = [row for semester in data["semesters"] for row in semester["rows"]]
        credits = transcript.student_credit_totals(student=user, organization=organization)
        rows.append(
            {
                "student": _short(pk),
                "_user": user,
                "access_state": states.get(pk, ""),
                "login_blocked": bool(user_access_is_login_blocked(user)),
                "record_rows": len(record_rows),
                "definite_rows": sum(1 for row in record_rows if row["in_gpa"]),
                "legacy_no_result_rows": sum(
                    1 for row in record_rows if row["result"].get("status_code") == "legacy_no_result"
                ),
                "uomg": data["cumulative_gpa"],
                "uomg_available": data["cumulative_gpa_available"],
                "credits_earned": data["total_credits_earned"],
                "credits_in_progress": credits["in_progress"],
            }
        )

for row in rows:
    user = row.pop("_user", None)
    if user is None:
        continue
    if row["login_blocked"]:
        for section in SECTIONS:
            row[f"http_{section}"] = "blocked"
        continue
    client = Client(HTTP_HOST=HOST)
    client.force_login(user)
    for section in SECTIONS:
        response = client.get("/accounts/profile/", {"section": section}, follow=False)
        body = response.content.decode("utf-8", "replace") if response.status_code == 200 else ""
        status = response.status_code
        row[f"http_{section}"] = f"{status}→{response.get('Location', '')}" if status in (301, 302) else status
        row[f"err_{section}"] = int("Traceback" in body or "Server Error" in body)
        if section == "overall-academic":
            row["page_rows"] = len(_ROW.findall(body))
            row["page_uomg"] = _first(_UOMG, body)
        elif section == "my-results":
            row["page_academic_count"] = _first(_ACADEMIC, body)

fields = []
for row in rows:
    fields.extend(key for key in row if key not in fields)
with open(OUT, "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
print(f"restore_current_verify: {len(rows)} tələbə → {OUT}")
for row in rows:
    print(
        f"  {row['student']} {row.get('access_state', ''):>8} sətir={row.get('record_rows', '-')} "
        f"səhifədə={row.get('page_rows', '-')} nəticələrim={row.get('page_academic_count', '-')} "
        f"ÜOMG={row.get('uomg')} ({row.get('page_uomg', '-')}) kredit={row.get('credits_earned', '-')} "
        + " ".join(f"{section}={row.get(f'http_{section}', '-')}" for section in SECTIONS)
    )
