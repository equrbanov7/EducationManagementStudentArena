import os

import django
from django.template.loader import get_template

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

files = [
    "audit/list.html",
    "blog/create_question.html",
    "accounts/pending_review_detail.html",
    "accounts/partials/_student_org_management_content.html",
    "accounts/partials/_superadmin_org_features_content.html",
    "admin/verify_otp.html",
]
out = []
ok = bad = 0
for f in files:
    try:
        get_template(f)
        out.append("OK   " + f)
        ok += 1
    except Exception as e:
        out.append("FAIL " + f + " -> " + repr(e)[:200])
        bad += 1
out.append("SUMMARY ok=%d bad=%d" % (ok, bad))
with open(os.path.join(os.path.dirname(__file__), "_tplcheck_out.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
print("written")
