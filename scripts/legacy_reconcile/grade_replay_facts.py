"""J12 replay nəticəsini immutable grade-fact mənbə payload-una çevir.

Əsas grade-fact fazası təqvim və komponent xanalarını qəsdən arxivləşdirmir:
onlar kanonik jurnal cədvəllərinə yazılır. J12 yalnız iki istisnanı əlavə
``LegacyGradeFact`` kimi saxlayır: fərqli-dəyər toqquşmasının uduzanı və dərsə
bağlana bilməyən writable təqvim xanası. Bu modul həmin kiçik dəsti replay-dən
müstəqil source gözləntisinə çevirir.
"""

from __future__ import annotations

from .analysis import DOMAIN_COMPONENTS, DOMAIN_MARKS


def _row(
    *,
    source_table,
    source_pk,
    is_archive,
    student_ref,
    journal_ref,
    lesson_ref,
    score_code,
    raw_value,
):
    """``grade_facts.PAYLOAD_WIDTH`` ilə eyni 25-sütunlu source sətri."""

    enrollment_ref = f"{journal_ref}:{student_ref}"
    return [
        source_table,
        str(source_pk),
        "other",
        score_code,
        "1" if is_archive else "0",
        student_ref,
        journal_ref,
        lesson_ref,
        "",
        enrollment_ref,
        "",
        "",
        "",
        "",
        raw_value,
        "NULL",
        "NULL",
        "NULL",
        "NULL",
        "NULL",
        "NULL",
        "",
        "",
        "NULL",
        "",
    ]


def replay_grade_fact_rows(replay) -> list[list]:
    """J12-nin yaratmalı olduğu əlavə faktları source identity üzrə qaytar."""

    if replay is None:
        return []
    rows: list[list] = []
    for evidence in replay.conflict_evidence:
        # ``im``/``im2`` uduzanları əsas grade-fact fazasında onsuz da hər xam
        # source PK üçün saxlanır; J12 onları ikinci dəfə yaratmır.
        if evidence.domain not in {DOMAIN_MARKS, DOMAIN_COMPONENTS}:
            continue
        rows.append(
            _row(
                source_table=evidence.source_table,
                source_pk=evidence.source_pk,
                is_archive=evidence.is_archive,
                student_ref=evidence.student_ref,
                journal_ref=evidence.journal_uniqid,
                lesson_ref=evidence.target_ref if evidence.domain == DOMAIN_MARKS else "",
                score_code=evidence.month_id,
                raw_value=evidence.raw_value,
            )
        )
    for evidence in replay.unresolved_calendar_evidence:
        rows.append(
            _row(
                source_table=evidence.source_table,
                source_pk=evidence.source_pk,
                is_archive=evidence.is_archive,
                student_ref=evidence.student_ref,
                journal_ref=evidence.journal_uniqid,
                lesson_ref=(f"calendar:{evidence.month:02d}:{evidence.day}:{evidence.time_text}"),
                score_code=f"{evidence.month:02d}",
                raw_value=evidence.raw_value,
            )
        )
    rows.sort(key=lambda row: (str(row[0]), int(row[1])))
    return rows


def replay_grade_fact_keys(replay) -> set[tuple[str, int]]:
    return {(str(row[0]), int(row[1])) for row in replay_grade_fact_rows(replay)}


__all__ = ["replay_grade_fact_keys", "replay_grade_fact_rows"]
