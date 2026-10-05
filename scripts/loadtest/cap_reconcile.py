"""Cavab bütövlüyü — yük testində UĞURLU deyilən hər yazının bazada olduğunu yoxlayır.

`manage.py shell -c "exec(open(PATH).read())"` ilə, test stack-in owner DB URL-i ilə.
  * imtahan: finish-dən sonra yazılmış gözlənilən seçimlər ↔ ExamAnswer.selected_options
  * jurnal: müəllimin saxladığı (və düzəltdiyi) xanalar ↔ LessonMark (status, bal)
  * midterm/kollokvium: ComponentScore (son yazı qalib — eyni xana bir neçə pillədə)
  * yekun imtahan balı: FinalGrade.exam_score + hər yazıya ExamScoreEntry sübut sətri
  * final mərkəzi: `expected-answers` sətirləri `kind=final` ilə ayrıca hesabatlanır
  * canlı viktorina: `answer_saved` alınmış hər cavab ↔ LiveAnswer (pin, ləqəb, sual, variant)
"""

import json
import os
from pathlib import Path

from apps.exams.models import ExamAttempt
from apps.exams.services.option_tokens import option_token
from apps.live_exam.models import LiveAnswer
from apps.registrar.models import ComponentScore, LessonMark
from apps.registrar.models.exam_score_entry import ExamScoreEntry
from apps.registrar.models.grading import FinalGrade
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
    rows = load("expected-answers")
    for kind in sorted({row.get("kind", "exam") for row in rows} or {"exam"}):
        expected = {row["attempt"]: row["selected"] for row in rows if row.get("kind", "exam") == kind}
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
        result[kind] = {
            "expected_attempts": len(expected),
            "found_attempts": found,
            "finished_attempts": finished,
            "answers_checked": answers,
            "mismatches": len(bad),
            "examples": bad[:10],
        }

    # Eyni jurnal bir neçə pillədə saxlanıla bilər — yalnız SON gözlənti yoxlanır
    # (fayllar pillə adına görə sıralanır: 01-, 02-, ...).
    latest = {}
    for row in load("expected-marks"):
        latest.setdefault(row["offering"], {}).update(row["marks"])
    marks_expected = [{"offering": k, "marks": v} for k, v in latest.items()]
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

    # Midterm/kollokvium — son gözlənti qalib (fayllar pillə sırası ilə oxunur).
    latest = {}
    for row in load("expected-midterm"):
        latest.update({(row["offering"], key): value for key, value in row["scores"].items()})
    stored = {
        f"{c}:{e}": None if score is None else int(score)
        for c, e, score in ComponentScore.objects.filter(
            component__offering_id__in={offering for offering, _key in latest}
        ).values_list("component_id", "enrollment_id", "score")
    }
    mism, examples = 0, []
    for (offering, key), want in latest.items():
        got = stored.get(key)
        if got != want:
            mism += 1
            if len(examples) < 10:
                examples.append({"offering": offering, "cell": key, "want": want, "got": got})
    result["midterm"] = {
        "journals": len({offering for offering, _key in latest}),
        "cells_checked": len(latest),
        "mismatches": mism,
        "examples": examples,
    }

    # Yekun imtahan balı — FinalGrade + sübut sətri (ExamScoreEntry) hər yazılmış bal üçün.
    finals = {}
    for row in load("expected-finals"):
        finals.update({enrollment: score for enrollment, score in row["scores"].items()})
    grades = {
        str(e): None if s is None else int(s)
        for e, s in FinalGrade.objects.filter(enrollment_id__in=list(finals)).values_list("enrollment_id", "exam_score")
    }
    evidence = {
        str(e) for e in ExamScoreEntry.objects.filter(enrollment_id__in=list(finals)).values_list("enrollment_id", flat=True)
    }
    bad = [
        {"enrollment": e, "want": want, "got": grades.get(e), "evidence": e in evidence}
        for e, want in finals.items()
        if grades.get(e) != want or e not in evidence
    ]
    result["final_scores"] = {"cells_checked": len(finals), "mismatches": len(bad), "examples": bad[:10]}

    live_rows = load("expected-live")
    if live_rows:
        stored = {}
        for pin, nickname, qid, choice, choices in LiveAnswer.objects.filter(
            session__pin__in={r["pin"] for r in live_rows}
        ).values_list("session__pin", "player__nickname", "question_id", "choice_id", "choice_ids"):
            stored[(pin, nickname, int(qid))] = {int(c) for c in (choices or []) if str(c).isdigit()} | (
                {int(choice)} if choice else set()
            )
        bad = [
            r
            for r in live_rows
            if int(r["option_id"]) not in stored.get((r["pin"], r["nickname"], int(r["question_id"])), set())
        ]
        result["live"] = {
            "sessions": len({r["pin"] for r in live_rows}),
            "answers_checked": len(live_rows),
            "mismatches": len(bad),
            "examples": bad[:10],
        }

(RUN_DIR / "reconciliation.json").write_text(json.dumps(result, indent=2))
print("CAP_RECONCILE " + json.dumps(result))
