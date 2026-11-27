"""Dublikat fənlər, 3-cü dövrə (sahib 2026-11-12) — eyni qrupun OXŞAR adlı iki aktiv jurnalı → bir jurnal.

Sahib (Səbinə Nobari, 533 Bi ing): «İnformasiya texnologiyaları» (QKU-1047, yalnız mühazirə) və «İnformasiya
texnologiyaları (ixtisas üzrə)» (QKU-845) — eyni müəllim, eyni tələbələr, eyni günlərdə eyni dərs iki jurnalda; müəllim
birində «fənnin dərs saatı həddi keçir» səbəbindən yeni dərs aça bilmir. «Bir fənn, bir jurnal; başqa müəllimlərdə də
eyni problem ola bilər, onlara da bax.»

Kataloq kartlarına TOXUNULMUR (iki kart başqa qruplarda ayrı-ayrı fənlər kimi yaşaya bilər — kafedra baxışı C1);
yalnız konkret qrupun cari dövrdəki iki jurnalı :class:`.duplicate_journal_merge_2026_11_11.JournalMerge` ilə
birləşir (heç bir xana / bal itmir, fərqli dəyərlər manifestdə, geri qaytarma paketlə).

**Namizəd cüt** — cari dövr, eyni qrup, ikisi də aktiv, fənn kartları FƏRQLİ və adlar :func:`similar_kind` üzrə
oxşardır: ``same`` (normallaşdırılmış ad eyni) və ya ``qualifier`` (biri digərinin «(ixtisas üzrə)» kimi izahlı
forması). Hərf fərqi («typo») qaydası YOXDUR: prod dry-run-u «Kəmiyyət əsaslı …» / «Keyfiyyət əsaslı tədqiqat
metodları» (iki hərf fərqi, FƏRQLİ fənlər) cütünü tutdu — «-1» / «-2», «I» / «II» kimi hissələr də birləşmir.

**Saxlanılan jurnal** (hədəf): qrupun tədris planında (qrup tələbələrinin akademik qeydlərinin planları) YALNIZ bir
kart varsa — o; ikisi də plandadırsa cüt toxunulmur (``similar_skip_both_in_plan`` — həqiqətən fərqli fənlər); heç
biri plandadırsa — dərs yükündə (bu dövr + qrup) saatı çox olan kart; yük də bərabərdirsə toxunulmur
(``similar_skip_no_signal``). :data:`EXCLUDED` — sahibin «birləşdirmə» dediyi cütlər (jurnal id-ləri).
"""

from __future__ import annotations

from collections import defaultdict

from django.apps import apps as django_apps

from core.audit import log_action
from core.constants import AuditAction

from .duplicate_journal_merge_2026_11_11 import JournalMerge
from .subject_duplicates import normalized_subject_key

#: Normallaşdırılmış adın sonundakı izah (``normalized_subject_key("(ixtisas üzrə)")``) — ad onsuz eyni fəndir.
QUALIFIERS = ("ixtisasuzre",)
#: Birləşdirilməyəcək cütlər: ``frozenset({jurnal_a, jurnal_b})``.
EXCLUDED: frozenset = frozenset()


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def _base(key: str) -> str:
    for suffix in QUALIFIERS:
        if key.endswith(suffix) and len(key) > len(suffix):
            return key[: -len(suffix)]
    return key


#: Yiyəlik hal şəkilçiləri (qatlanmış: ı/ü → i/u) — «Verilənlər» / «Verilənlərin bazası sistemləri» (2026-11-27).
GENITIVE_SUFFIXES = ("nin", "nun", "in", "un")


def _words(name: str) -> list:
    return [key for key in (normalized_subject_key(word) for word in str(name or "").split()) if key]


def _genitive_pair(left: str, right: str) -> bool:
    short, long_ = sorted((left, right), key=len)
    tail = long_[len(short) :]
    return short.isalpha() and len(short) >= 4 and long_.startswith(short) and tail in GENITIVE_SUFFIXES


def _inflection(left: str, right: str) -> bool:
    """Sözlər eynidir, YALNIZ bir və ya bir neçə söz yiyəlik şəkilçisi ilə fərqlənir (hərf səhvi sayılmır)."""
    a, b = _words(left), _words(right)
    if len(a) != len(b) or a == b:
        return False
    return all(x == y or _genitive_pair(x, y) for x, y in zip(a, b))


def similar_kind(left: str, right: str) -> str:
    """``same`` / ``qualifier`` / ``inflection`` və ya ``""`` (oxşar deyil)."""
    a, b = normalized_subject_key(left), normalized_subject_key(right)
    if not a or not b:
        return ""
    if a == b:
        return "same"
    if _base(a) == _base(b):
        return "qualifier"
    if _inflection(left, right):
        return "inflection"
    return ""


def student_pairs(organization, period, *, counts, lines) -> None:
    """YALNIZ OXUYUR (2026-11-27): eyni tələbənin cari dövrdə OXŞAR adlı iki fənn üzrə iki aktiv jurnalı — tələbə
    kabinetində «eyni fənn iki dəfə». Qrupdan asılı deyil (ana qrup + alt qrup jurnalı da tutulur)."""
    if period is None:
        return
    rows = (
        _model("Enrollment")
        ._base_manager.filter(
            organization=organization, status="enrolled", offering__period=period, offering__is_active=True
        )
        .values_list("student_id", "offering_id", "offering__subject_id", "offering__subject__name")
        .order_by("student_id", "offering_id")
    )
    by_student = defaultdict(list)
    for student_id, offering_id, subject_id, name in rows:
        by_student[student_id].append((offering_id, subject_id, name))
    pairs = defaultdict(set)
    kinds = {}
    for student_id, items in by_student.items():
        for index, left in enumerate(items):
            for right in items[index + 1 :]:
                if left[1] == right[1]:
                    continue
                kind = similar_kind(left[2], right[2])
                if not kind:
                    continue
                key = tuple(sorted((left[0], right[0]), key=str))
                pairs[key].add(student_id)
                kinds[key] = kind
    offerings = {
        row.pk: row
        for row in _model("CourseOffering")
        ._base_manager.filter(pk__in={pk for key in pairs for pk in key})
        .select_related("subject")
    }
    for number, (key, students) in enumerate(sorted(pairs.items(), key=lambda kv: (-len(kv[1]), str(kv[0]))), 1):
        counts[f"student_pairs_{kinds[key]}"] += 1
        counts["student_pairs_students"] += len(students)
        left, right = (offerings[pk] for pk in key)
        lines.append(
            " ".join(
                [
                    f"pair={number}",
                    f"kind={kinds[key]}",
                    f"students={len(students)}",
                    f"left={left.pk}",
                    f"left_code={(left.subject.code or 'none').lower()}",
                    f"left_group={left.group_id or 'none'}",
                    f"right={right.pk}",
                    f"right_code={(right.subject.code or 'none').lower()}",
                    f"right_group={right.group_id or 'none'}",
                    f"teachers={'same' if left.instructor_id == right.instructor_id else 'differ'}",
                ]
            )
        )


def group_plans(group_id) -> list:
    rows = _model("StudentAcademicRecord")._base_manager.filter(group_id=group_id)
    return sorted({str(value) for value in rows.values_list("curriculum_id", flat=True)})


def _plan_subjects(plans, subject_ids) -> set:
    if not plans:
        return set()
    rows = _model("CurriculumSubject")._base_manager.filter(curriculum_id__in=plans, subject_id__in=subject_ids)
    return set(rows.values_list("subject_id", flat=True))


def _load_hours(offering) -> int:
    rows = _model("TeachingTaskRow", "workload")._base_manager.filter(
        period_id=offering.period_id, subject_id=offering.subject_id, groups=offering.group_id
    )
    return sum(row.lecture_total + row.seminar_total + row.lab_total for row in rows)


def _facts(offering) -> dict:
    lessons = _model("Lesson").objects.filter(offering=offering)
    marks = _model("LessonMark").objects.filter(lesson__offering=offering)
    students = _model("Enrollment").objects.filter(offering=offering).exclude(status="dropped")
    return {
        "lessons": lessons.count(),
        "marks": marks.count(),
        "scores": marks.filter(score__isnull=False).count(),
        "students": students.count(),
        "load": _load_hours(offering),
    }


def candidates(organization, period) -> list:
    """``[(source, target, kind, decision, plans)]`` — cari dövrün oxşar adlı jurnal cütləri (sabit sıra)."""
    if period is None:
        return []
    rows = (
        _model("CourseOffering")
        ._base_manager.filter(organization=organization, period=period, is_active=True, group__isnull=False)
        .select_related("subject")
        .order_by("pk")
    )
    boxes = defaultdict(list)
    for offering in rows:
        boxes[offering.group_id].append(offering)
    out = []
    for group_id, items in sorted(boxes.items(), key=lambda kv: str(kv[0])):
        for index, left in enumerate(items):
            for right in items[index + 1 :]:
                if left.subject_id == right.subject_id:
                    continue
                kind = similar_kind(left.subject.name, right.subject.name)
                if not kind:
                    continue
                plans = group_plans(group_id)
                out.append((*_decide(left, right, plans), kind, plans))
    return out


def _decide(left, right, plans):
    """``(source, target, decision)`` — modulun sənədindəki qayda ilə."""
    if frozenset({str(left.pk), str(right.pk)}) in EXCLUDED:
        return left, right, "skip_excluded"
    in_plan = _plan_subjects(plans, [left.subject_id, right.subject_id])
    if left.subject_id in in_plan and right.subject_id in in_plan:
        return left, right, "skip_both_in_plan"
    if in_plan:
        target = left if left.subject_id in in_plan else right
        return (right if target is left else left), target, "merge_plan"
    hours = {row.pk: _load_hours(row) for row in (left, right)}
    if hours[left.pk] == hours[right.pk]:
        return left, right, "skip_no_signal"
    target = max((left, right), key=lambda row: hours[row.pk])
    return (right if target is left else left), target, "merge_load"


def run(*, organization, actor, counts, batch, lines, period, resource, kind, reason) -> list:
    """Namizədləri sayır, ``merge_*`` qərarlıları birləşdirir; birləşən cütlərin siyahısını qaytarır."""
    merger = JournalMerge(organization=organization, actor=actor, counts=counts, batch=batch)
    merged = []
    for number, (source, target, decision, similarity, plans) in enumerate(candidates(organization, period), 1):
        counts[f"similar_{similarity}"] += 1
        counts[f"similar_{decision}"] += 1
        left, right = _facts(source), _facts(target)
        line = [
            f"similar={number}",
            f"group={source.group_id}",
            f"kind={similarity}",
            f"decision={decision}",
            f"source={source.pk}",
            f"source_code={(source.subject.code or 'none').lower()}",
            f"target={target.pk}",
            f"target_code={(target.subject.code or 'none').lower()}",
            f"teachers={'same' if source.instructor_id == target.instructor_id else 'differ'}",
        ]
        line += [f"source_{key}={value}" for key, value in left.items()]
        line += [f"target_{key}={value}" for key, value in right.items()]
        if decision.startswith("merge"):
            merger.run([{"source": str(source.pk), "target": str(target.pk), "reviewed": True, "curricula": plans}])
            _index, delta = merger.report[-1]
            done = bool(delta.get("pairs_merged"))
            # Dayanmış cütün deltası YALNIZ səbəb sayğacıdır (JournalMerge.run sayları geri qaytarır).
            line.append(f"result={'merged' if done else (sorted(delta) or ['not_merged'])[0]}")
            if done:
                merged.append({"source": str(source.pk), "target": str(target.pk)})
        lines.append(" ".join(line))
    for index, delta in merger.report:
        if delta:
            lines.append(f"pair={index} " + " ".join(f"{key}={value}" for key, value in sorted(delta.items())))
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        new_values={"ops": ["similar"], "pairs": len(merged)},
        changes={"kind": kind, "batch": batch, "ops": ["similar"], "catalogue_audits": [], "similar": merged},
        reason=reason,
        resource_type=resource,
        resource_id=batch,
    )
    return merged


__all__ = ["EXCLUDED", "QUALIFIERS", "candidates", "group_plans", "run", "similar_kind", "student_pairs"]
