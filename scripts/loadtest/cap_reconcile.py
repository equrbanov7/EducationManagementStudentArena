"""Cavab bütövlüyü — yük testində UĞURLU deyilən hər yazının bazada olduğunu yoxlayır.

`manage.py shell -c "exec(open(PATH).read())"` ilə, test stack-in owner DB URL-i ilə.
  * imtahan: finish-dən sonra yazılmış gözlənilən seçimlər ↔ ExamAnswer.selected_options
  * jurnal: müəllimin saxladığı (və düzəltdiyi) xanalar ↔ LessonMark (status, bal)
"""

import json
import os
from pathlib import Path

from apps.exams.models import ExamAttempt
from apps.exams.services.option_tokens import option_token
from apps.registrar.models import LessonMark
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

RUN_DIR = Path(os.environ["CAP_RUN_DIR"])


def load(prefix):
    rows = []
    for path in sorted(RUN_DIR.glob(f"{prefix}-*.jsonl")):
        rows.extend(json.loads(line) for line in path.read_text().splitlines() if line.strip())
    return rows


result = {}
with rls_worker_atomic(), bypass_rls():
    expected = {row["attempt"]: row["selected"] for row in load("expected-answers")}
    bad, answers, finished = [], 0, 0
    attempts = ExamAttempt.objects.filter(pk__in=list(expected)).prefetch_related("answers__selected_options")
    found = 0
    for attempt in attempts:
        found += 1
        if attempt.finished_at is not None:
            finished += 1
        actual = {}
        for answer in attempt.answers.all():
            ids = [option.id for option in answer.selected_options.all()]
            if ids:
                actual[str(answer.question_id)] = {option_token(attempt.pk, i) for i in ids}
            answers += 1
        wanted = {qid: {value} for qid, value in expected[attempt.pk].items()}
        if actual != wanted:
            bad.append({"attempt": attempt.pk, "missing": sorted(set(wanted) - set(actual))[:5]})
    result["exam"] = {
        "expected_attempts": len(expected),
        "found_attempts": found,
        "finished_attempts": finished,
        "answers_checked": answers,
        "mismatches": len(bad),
        "examples": bad[:10],
    }

    marks_expected = load("expected-marks")
    cells = mism = 0
    examples = []
    for row in marks_expected:
        stored = {
            f"{m.lesson_id}:{m.enrollment_id}": [m.status, None if m.score is None else int(m.score)]
            for m in LessonMark.objects.filter(lesson__offering_id=row["offering"])
        }
        for key, (status, score) in row["marks"].items():
            cells += 1
            got = stored.get(key)
            want_score = None if status == "absent" else score
            if got is None or got[0] != status or got[1] != want_score:
                mism += 1
                if len(examples) < 10:
                    examples.append({"offering": row["offering"], "cell": key, "want": [status, want_score], "got": got})
    result["journal"] = {"journals": len(marks_expected), "cells_checked": cells, "mismatches": mism, "examples": examples}

(RUN_DIR / "reconciliation.json").write_text(json.dumps(result, indent=2))
print("CAP_RECONCILE " + json.dumps(result))
