from apps.exams.models import CodingExamQuestion, CodingTestCase, ExamQuestion


def _next_question_order(exam):
    last_question = exam.questions.order_by("-order", "-id").first()
    return (last_question.order + 1) if last_question else 1


def build_coding_payload_from_exam_form(cleaned_data):
    return {
        "language": cleaned_data.get("coding_language") or CodingExamQuestion.LANGUAGE_PYTHON,
        "title": (cleaned_data.get("coding_question_title") or "").strip(),
        "problem_statement": (cleaned_data.get("coding_problem_statement") or "").strip(),
        "input_description": cleaned_data.get("coding_input_description") or "",
        "output_description": cleaned_data.get("coding_output_description") or "",
        "example_input": cleaned_data.get("coding_example_input") or "",
        "example_output": cleaned_data.get("coding_example_output") or "",
        "time_limit_seconds": cleaned_data.get("coding_time_limit_seconds") or 2,
        "memory_limit_mb": cleaned_data.get("coding_memory_limit_mb") or 128,
        "max_score": cleaned_data.get("coding_max_score") or 100,
        "starter_code": cleaned_data.get("coding_starter_code") or "",
        "allow_file_creation": bool(cleaned_data.get("coding_allow_file_creation")),
        "allow_multiple_files": bool(cleaned_data.get("coding_allow_multiple_files")),
        "enable_code_execution": bool(cleaned_data.get("coding_enable_code_execution")),
    }


def build_coding_payload_from_question_form(cleaned_data):
    return {
        "language": cleaned_data.get("language") or CodingExamQuestion.LANGUAGE_PYTHON,
        "title": (cleaned_data.get("title") or "").strip(),
        "problem_statement": (cleaned_data.get("problem_statement") or "").strip(),
        "input_description": cleaned_data.get("input_description") or "",
        "output_description": cleaned_data.get("output_description") or "",
        "example_input": cleaned_data.get("example_input") or "",
        "example_output": cleaned_data.get("example_output") or "",
        "time_limit_seconds": cleaned_data.get("time_limit_seconds") or 2,
        "memory_limit_mb": cleaned_data.get("memory_limit_mb") or 128,
        "max_score": cleaned_data.get("max_score") or 100,
        "starter_code": cleaned_data.get("starter_code") or "",
        "allow_file_creation": bool(cleaned_data.get("allow_file_creation")),
        "allow_multiple_files": bool(cleaned_data.get("allow_multiple_files")),
        "enable_code_execution": bool(cleaned_data.get("enable_code_execution")),
    }


def sync_coding_test_cases(coding_question, *, visible_cases, hidden_cases):
    CodingTestCase.objects.filter(coding_question=coding_question).delete()
    rows = []
    order = 1
    for case in [*(visible_cases or []), *(hidden_cases or [])]:
        rows.append(
            CodingTestCase(
                coding_question=coding_question,
                input_data=case["input_data"],
                expected_output=case["expected_output"],
                visibility=case["visibility"],
                point_value=case["point_value"],
                order=order,
            )
        )
        order += 1
    if rows:
        CodingTestCase.objects.bulk_create(rows)


def upsert_coding_question(exam, *, payload, visible_cases=None, hidden_cases=None, base_question=None):
    if base_question is None:
        base_question = ExamQuestion(exam=exam, order=_next_question_order(exam))

    base_question.exam = exam
    base_question.text = payload["title"]
    base_question.correct_answer = ""
    base_question.answer_mode = "single"
    base_question.points = max(int(payload.get("max_score") or 1), 1)
    base_question.time_limit_seconds = max(int(payload.get("time_limit_seconds") or 1), 1)
    base_question.is_active = True
    base_question.save()

    coding_question, _ = CodingExamQuestion.objects.get_or_create(
        question=base_question,
        defaults={
            "language": payload["language"],
            "title": payload["title"],
            "problem_statement": payload["problem_statement"],
        },
    )

    for field_name in (
        "language",
        "title",
        "problem_statement",
        "input_description",
        "output_description",
        "example_input",
        "example_output",
        "time_limit_seconds",
        "memory_limit_mb",
        "max_score",
        "starter_code",
        "allow_file_creation",
        "allow_multiple_files",
        "enable_code_execution",
    ):
        setattr(coding_question, field_name, payload[field_name])
    coding_question.save()

    sync_coding_test_cases(
        coding_question,
        visible_cases=visible_cases or [],
        hidden_cases=hidden_cases or [],
    )
    return base_question, coding_question
