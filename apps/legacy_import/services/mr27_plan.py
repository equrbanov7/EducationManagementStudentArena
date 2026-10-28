"""MR27 üçün qapalı mənbə planı: sərbəst SQL və ya əlavə şəxs/tarix qəbul etmir."""

import hashlib
import json
from pathlib import Path

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
OFFERING = "567a6fc3-df03-4cac-beca-7f0674ea9137"
GROUP = "25266fd8-38a5-465e-b1d1-79665de0e246"
PARENT = "6a49504c-60ca-43d9-8d07-44f35994d152"
EXISTING_STUDENT = 2510
TEACHER = 8415
DATES = {
    "2026-09-21": "lecture",
    "2026-09-24": "lecture",
    "2026-09-28": "seminar",
    "2026-10-05": "lecture",
    "2026-10-08": "seminar",
    "2026-10-12": "lecture",
    "2026-10-19": "lecture",
}
POINTS = {
    10127: (5352749, 5375757, 5391381, 5440612, 5473808, 5491704, 5547933),
    10128: (5352751, 5375759, 5391383, 5440613, 5473731, 5491706, 5547935),
    10129: (5352750, 5375758, 5391382, 5440499, 5473850, 5491705, 5547934),
}


class RecoveryError(ValueError):
    """Yalnız sabit xəta kodu — şəxsi dəyər/log yoxdur."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, default=str).encode()).hexdigest()


def load(path, expected):
    raw = Path(path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if len(raw) > 100_000 or len(expected) != 64 or sha != expected.lower():
        raise RecoveryError("plan_digest_mismatch")
    try:
        data = json.loads(raw)
    except ValueError:
        raise RecoveryError("invalid_json") from None
    try:
        validate(data)
    except RecoveryError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError):
        raise RecoveryError("plan_shape") from None
    return data, sha, len(raw)


def validate(data):
    from .field_contracts import GROUP_STRUCTURE_FIELDS, SPECIALITY_STRUCTURE_FIELDS, STUDENT_IDENTITY_FIELDS

    if data.get("format") != "mr27-recovery/1":
        raise RecoveryError("plan_format")
    specialty, group = data.get("speciality", {}), data.get("group", {})
    if (
        specialty.get("id") != 103
        or specialty.get("name") != "Bioekelogiya"
        or specialty.get("speciality_code") != "005566"
        or specialty.get("department_id") != 35
    ):
        raise RecoveryError("speciality_scope")
    if (
        group.get("id") != 902
        or group.get("speciality_id") != 103
        or group.get("name") != "510/6BİEO"
        or group.get("bak_or_mag") != "mag"
        or int(group.get("start_year", 0)) != 2026
    ):
        raise RecoveryError("group_scope")
    students = data.get("students", [])
    if {row.get("id") for row in students} != {10127, 10128} or len(students) != 2:
        raise RecoveryError("student_scope")
    names = {10127: ("Fatimə", "Əliyeva", "Allahverdi"), 10128: ("Rəqsanə", "Cəfərli", "Ruslan")}
    for row in students:
        if (
            tuple(row.get(k) for k in ("first_name", "last_name", "father_name")) != names[row["id"]]
            or row.get("group_id") != 902
            or row.get("status") != 0
            or int(row.get("join_date") or 0) != 2026
            or bool(row.get("fincode"))
        ):
            raise RecoveryError("student_source_mismatch")
    for rows, contract in (
        ([specialty], SPECIALITY_STRUCTURE_FIELDS),
        ([group], GROUP_STRUCTURE_FIELDS),
        (students, STUDENT_IDENTITY_FIELDS),
    ):
        if any(set(row) != set(contract.allowed_fields) for row in rows):
            raise RecoveryError("source_projection")
    expected = []
    for student, ids in POINTS.items():
        for (date, kind), pk in zip(DATES.items(), ids):
            score = 9 if date == "2026-10-08" and student != 10129 else None
            status = "absent" if date == "2026-10-05" and student == 10129 else "present"
            expected.append(
                dict(
                    source_point_id=pk,
                    legacy_student_id=student,
                    date=date,
                    kind=kind,
                    time="20:10:00",
                    status=status,
                    score=score,
                )
            )
    if sorted(data.get("marks", []), key=lambda row: row.get("source_point_id", 0)) != sorted(
        expected, key=lambda row: row["source_point_id"]
    ):
        raise RecoveryError("mark_source_mismatch")
