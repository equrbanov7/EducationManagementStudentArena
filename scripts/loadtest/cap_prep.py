"""Pillə-öncəsi hazırlıq — `manage.py shell -c "exec(open(PATH).read())"` ilə (izolə test bazası).

`CAP_PREP=final_pins` (finalcenter): final imtahanı (`seed.final_exam_id`) üçün
`stress_student_{START..START+COUNT-1}` tələbələrinə fərdi PIN (`ExamStudentPin`) və
`StudentExamAttemptGrant` (gün qaydası: eyni gündə ikinci rəsmi imtahan — eyni gündə
təkrar run-larda eyni tələbələr düşə bilər). PIN hamı üçün eynidir (`seed.final_pin`):
yoxlama dəyəri (PBKDF2 `check_password`) hər giriş üçün real ilə eyni qiymətə başa gəlir,
amma seed 1000-lərlə yavaş hash hesablamır.
"""

import json
import os
import time

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password

from apps.exams.domain.student_access import ExamStudentPin, StudentExamAttemptGrant
from apps.exams.models import Exam
from apps.exams.services.final_center.pins import _fernet
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

KIND = os.environ["CAP_PREP"]
START = int(os.environ.get("CAP_PREP_START", "1"))
COUNT = int(os.environ.get("CAP_PREP_COUNT", "0"))
PAD = int(os.environ.get("CAP_STUDENT_PAD", "3"))
SEED = json.loads(open(os.environ["CAP_SEED_FILE"]).read())
User = get_user_model()

started = time.monotonic()
if KIND == "final_pins":
    with rls_worker_atomic(), bypass_rls():
        exam = Exam.objects.get(pk=SEED["final_exam_id"])
        raw_pin = SEED["final_pin"]
        pin_hash = make_password(raw_pin)
        cipher = _fernet().encrypt(raw_pin.encode()).decode()
        names = [f"stress_student_{i:0{PAD}d}" for i in range(START, START + COUNT)]
        ids = list(User.objects.filter(username__in=names).values_list("id", flat=True))
        have = set(ExamStudentPin.objects.filter(exam=exam, student_id__in=ids).values_list("student_id", flat=True))
        ExamStudentPin.objects.bulk_create(
            [ExamStudentPin(exam=exam, student_id=i, pin_hash=pin_hash, pin_cipher=cipher) for i in ids if i not in have],
            batch_size=1000,
            ignore_conflicts=True,
        )
        ExamStudentPin.objects.filter(exam=exam, student_id__in=ids).update(
            pin_hash=pin_hash, pin_cipher=cipher, revoked_at=None, expires_at=None
        )
        granted = set(
            StudentExamAttemptGrant.objects.filter(exam=exam, student_id__in=ids).values_list("student_id", flat=True)
        )
        StudentExamAttemptGrant.objects.bulk_create(
            [StudentExamAttemptGrant(exam=exam, student_id=i, extra_attempts=1) for i in ids if i not in granted],
            batch_size=1000,
            ignore_conflicts=True,
        )
    print("CAP_PREP", json.dumps({"kind": KIND, "students": len(ids), "seconds": round(time.monotonic() - started, 1)}))
else:
    raise SystemExit(f"naməlum CAP_PREP: {KIND}")
