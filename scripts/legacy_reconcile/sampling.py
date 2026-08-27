"""§3 «Nümunə-yoxlama»: 20 təsadüfi tələbə üçün köhnə/yeni yan-yana müqayisə.

Seçim TƏKRARLANA BİLƏNdir — eyni toxum, eyni tələbələr.  Beləliklə sabah eyni
əmr eyni 20 nəfəri göstərir və sahib fərqi izləyə bilər.
"""

from __future__ import annotations

from decimal import Decimal

from . import source_sql as S
from . import target_sql as T
from .analysis import clean_legacy_text, entry_score, pick_sample, summarise_cells, total_score

SAMPLE_SIZE = 20
SAMPLE_SEED = 20260827


def collect_sample(source, target, target_facts: dict, *, size: int = SAMPLE_SIZE, seed: int = SAMPLE_SEED) -> list:
    """Nümunə tələbələri seç və hər biri üçün mənbə/hədəf tərəfi topla."""

    pool = source.query("nümunə hovuzu", S.STUDENT_POOL_SQL)
    identity = {row[0]: row for row in pool}
    student_bridge = target_facts["students"]
    eligible = [key for key in identity if key in student_bridge]
    chosen = stratified_sample(eligible, target_facts["enrollments"], seed=seed, size=size)
    if not chosen:
        return []

    legacy_ids = [int(value) for value in chosen]
    cells = summarise_cells(source.query("nümunə xanaları", S.sample_cells_sql(legacy_ids)))
    subjects = {row[0]: row[1] for row in source.query("jurnal → fənn", S.journal_subject_sql())}
    yekun = _index_yekun(source.query("nümunə yekun", S.sample_yekun_sql(legacy_ids)))

    user_ids = [int(student_bridge[key]) for key in chosen]
    target_identity = {str(row[0]): row for row in target.query("nümunə şəxsiyyət", T.SAMPLE_IDENTITY_SQL, (user_ids,))}
    target_rows = _index_target(target.query("nümunə yazılışlar", T.SAMPLE_ENROLLMENT_SQL, (user_ids,)))

    enrollment_bridge = target_facts["enrollments"]
    return [
        _build_student(
            legacy_key=key,
            identity=identity[key],
            user_id=str(student_bridge[key]),
            target_identity=target_identity,
            cells=cells,
            subjects=subjects,
            yekun=yekun,
            target_rows=target_rows,
            enrollment_bridge=enrollment_bridge,
        )
        for key in chosen
    ]


def stratified_sample(eligible, enrollment_bridge, *, seed: int, size: int) -> list:
    """Yarısı yazılışı KÖÇƏN, yarısı KÖÇMƏYƏN tələbədən — qəsdən bərabər bölgü.

    Sırf təsadüfi seçim bu datada demək olar ki, həmişə arxiv tələbələrini
    gətirir (``yekun`` sətirləri köhnə buraxılışlara aiddir) və nümunə «heç nə
    köçməyib» mənzərəsinə çevrilir.  Bərabər bölgü hər iki mənzərəni göstərir:
    köçən datanın xana-bəxana düzgünlüyünü VƏ köçməyənin miqyasını.
    """

    with_enrollment = {int(key.split(":", 1)[1]) for key in enrollment_bridge if ":" in key}
    migrated = [key for key in eligible if int(key) in with_enrollment]
    skipped = [key for key in eligible if int(key) not in with_enrollment]
    half = size // 2
    picked = pick_sample(migrated, seed=seed, size=half) + pick_sample(skipped, seed=seed + 1, size=size - half)
    if len(picked) < size:  # bir tərəf boşdursa qalanı digərindən doldur
        rest = [key for key in eligible if key not in set(picked)]
        picked += pick_sample(rest, seed=seed + 2, size=size - len(picked))
    return sorted(picked)


def _index_yekun(rows) -> dict:
    index: dict = {}
    for student_id, uniqid, lesson_name, girish, exam, total in rows:
        index[(str(student_id), uniqid)] = {
            "fenn": lesson_name,
            "girish": _clean(girish),
            "imtahan": _clean(exam),
            "yekun": _clean(total),
        }
    return index


def _index_target(rows) -> dict:
    index: dict = {}
    for row in rows:
        index[row[1]] = {
            "fenn": row[2],
            "qayib": int(row[3] or 0),
            "uzrlu": int(row[4] or 0),
            "seminar": Decimal(str(row[5] or 0)),
            "kollokvium": Decimal(str(row[6] or 0)),
            "serbest": Decimal(str(row[7] or 0)),
            "imtahan": None if row[8] is None else Decimal(str(row[8])),
            "tekrar": None if row[9] is None else Decimal(str(row[9])),
            "bonus": Decimal(str(row[10] or 0)),
            "cap": int(row[11] or 50),
            "status": row[12],
        }
    return index


def _clean(value):
    """Legacy ``-1`` sentineli (NULL) → ``None``."""

    if value in (None, "", "NULL"):
        return None
    number = Decimal(str(value))
    return None if number < 0 else number


def _build_student(
    *, legacy_key, identity, user_id, target_identity, cells, subjects, yekun, target_rows, enrollment_bridge
):
    """Bir tələbənin mənbə/hədəf sətirlərini fənn-fənn cütləşdir."""

    target_row = target_identity.get(user_id)
    uniqids = sorted(
        {uniqid for student_key, uniqid in cells if student_key == str(legacy_key)}
        | {uniqid for student_key, uniqid in yekun if student_key == str(legacy_key)}
    )
    # Bir neçə legacy jurnal EYNİ açılışa birləşdiyi üçün eyni fənn iki dəfə
    # görünə bilər.  Belə sətirlərin HAMISI «birləşmə» kimi işarələnir — nə
    # birincisi, nə ikincisi müstəqil uyğunsuzluq deyil: «yeni» sütunu hər iki
    # legacy jurnalın birləşmiş nəticəsidir.
    enrollment_of = {uniqid: enrollment_bridge.get(f"{uniqid}:{legacy_key}") for uniqid in uniqids}
    merged_enrollments = {
        pk for pk in enrollment_of.values() if pk is not None and list(enrollment_of.values()).count(pk) > 1
    }
    subject_rows = []
    for uniqid in uniqids:
        source_cells = cells.get((str(legacy_key), uniqid), {})
        source_yekun = yekun.get((str(legacy_key), uniqid), {})
        enrollment_pk = enrollment_of[uniqid]
        target_cells = target_rows.get(enrollment_pk) if enrollment_pk else None
        merged = enrollment_pk in merged_enrollments
        subject_rows.append(
            {
                "uniqid": uniqid,
                "fenn": clean_legacy_text(source_yekun.get("fenn") or subjects.get(uniqid, uniqid)),
                "source": source_cells,
                "source_yekun": source_yekun,
                "target": target_cells,
                "merged": merged,
                "computed": _computed(target_cells),
                "reason": _reason(source_cells, source_yekun, enrollment_pk, target_cells, merged),
            }
        )
    matched = sum(1 for row in subject_rows if row["target"] is not None)
    return {
        "legacy_id": legacy_key,
        "user_id": user_id,
        "source_name": clean_legacy_text(identity[1]),
        "source_group": clean_legacy_text(identity[2]),
        "source_speciality": clean_legacy_text(identity[3]),
        "target_name": clean_legacy_text(target_row[1]) if target_row else "",
        "target_group": clean_legacy_text(target_row[2]) if target_row else "",
        "target_program": clean_legacy_text(target_row[3]) if target_row else "",
        "target_status": target_row[4] if target_row else "",
        "membership_active": bool(target_row[5]) if target_row else False,
        "subjects": subject_rows,
        "matched": matched,
        "total_subjects": len(subject_rows),
    }


def _computed(target_cells) -> dict:
    """Hədəf tərəfin giriş/yekun balını ``compute_final_result`` güzgüsü ilə hesabla."""

    if not target_cells:
        return {}
    entry = entry_score(target_cells["seminar"], target_cells["kollokvium"], target_cells["cap"])
    return {
        "girish": entry,
        "yekun": total_score(entry, target_cells["imtahan"], target_cells["tekrar"], target_cells["bonus"]),
    }


def _reason(source_cells, source_yekun, enrollment_pk, target_cells, merged=False) -> str:
    """Fərq varsa KONKRET səbəb — «bilinmir» yazmaqdansa boş buraxılır."""

    if enrollment_pk is None:
        if source_cells or source_yekun:
            return "yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb)"
        return ""
    if target_cells is None:
        return "yazılış ledger-də var, registrar-da tapılmadı"
    if merged:
        return "bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir"
    return ""
