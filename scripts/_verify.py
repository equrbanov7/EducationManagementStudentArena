import os

import django
from django.template.loader import get_template
from django.utils import translation
from django.utils.translation import pgettext

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

out = []

# 1. templates still load
tpls = [
    "audit/list.html",
    "blog/create_question.html",
    "accounts/pending_review_detail.html",
    "accounts/partials/_student_org_management_content.html",
    "accounts/partials/_superadmin_org_features_content.html",
    "admin/verify_otp.html",
    "accounts/profile/sections/_category_management.html",
]
for t in tpls:
    try:
        get_template(t)
        out.append("LOAD OK   " + t)
    except Exception as e:
        out.append("LOAD FAIL " + t + " " + repr(e)[:160])

checks = [("audit.list", "col_time"), ("common", "search"), ("accounts.student_org", "remove_from_org")]
for lang in ["az", "en", "ru", "tr"]:
    with translation.override(lang):
        vals = ["%s/%s=%r" % (c, k, pgettext(c, k)) for c, k in checks]
        out.append("[%s] " % lang + " | ".join(vals))

open(os.path.join(os.path.dirname(__file__), "_verify_out.txt"), "w", encoding="utf-8").write("\n".join(out))
print("done")
