"""İmtahan zallarını prod-da işarələmək (sahib 2026-10-01: «B korpusunda 03, 28, 38 imtahan zalı»).

``manage.py mark_exam_halls`` komandasını çağırır (0070 miqrasiyası + komanda prod image-ində
olandan SONRA işləyir). Default DRY-RUN; ``HALLS_APPLY=yes`` → yazır. İdempotentdir, hər dəyişiklik
audit loqa düşür (komandanın özü).

Mühit dəyişənləri (prod-exam-ops.yml ötürür):
    HALLS_ORG       təşkilat slug (məs. qku)
    HALLS_BUILDING  korpus («B», «Korpus B» …)
    HALLS_ROOMS     vergüllə otaq nömrələri (03,28,38)
    HALLS_APPLY     "yes" → faktiki yazır
    HALLS_UNMARK    "yes" → zallardan çıxarır
"""

import os

from django.core.management import call_command

args = [
    "--org",
    os.environ.get("HALLS_ORG", "").strip(),
    "--building",
    os.environ.get("HALLS_BUILDING", "").strip(),
    "--rooms",
    os.environ.get("HALLS_ROOMS", "").strip(),
]
if os.environ.get("HALLS_APPLY") == "yes":
    args.append("--apply")
if os.environ.get("HALLS_UNMARK") == "yes":
    args.append("--unmark")
print("mark_exam_halls", " ".join(a for a in args if a))
call_command("mark_exam_halls", *args)
