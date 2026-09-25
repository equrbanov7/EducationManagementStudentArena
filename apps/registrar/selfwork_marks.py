"""Sərbəst iş lövhəsinin YAZI servisləri — mövzu əlavə/sil, təhvil işarəsi / BAL (jurnal mənbəyi).

``journal_extras`` modul-ölçü büdcəsinə görə bölünüb; adlar oradan re-eksport
olunur (``journal_extras.add_selfwork_topic`` və s.) — çağıranlar üçün API
dəyişməyib, yeni açar sözlər (``points``) isə opsionaldır.

Kilid qaydaları (əvvəlki kimi, bala genişləndirilib):

* jurnal kilidli (RİM bağlayıb) → heç nə yazılmır;
* boş xanaya təhvil/bal HƏR ZAMAN yazılır; mövcud qiymətin geri alınması və ya
  dəyişməsi yalnız 2 saat içində (bal silmə saxtakarlığına qarşı) — sonra yalnız
  sənədli düzəliş (``allow_locked=True``, ``item_corrections``);
* «Fənn qovluğu»ndan gələn bal (``source=subject_folder``) lövhədə OXU-ONLY-dir —
  onu yalnız sənədli düzəliş dəyişir;
* kilid sırası: açılış → qeydiyyat → işarə (``correction_target_locks`` ilə eyni).
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.registrar import grade_audit
from apps.registrar import selfwork_points as rules
from apps.registrar import selfwork_structure as structure
from apps.registrar.gradebook import MARK_EDIT_WINDOW, journal_is_locked
from apps.registrar.models import Enrollment, SelfWorkMark, SelfWorkTopic
from core.http_ids import parse_uuid

#: ``set_selfwork_mark(points=...)`` verilmədikdə (köhnə çağıranlar — yalnız ``done``).
UNSET = object()


def _audit_item(topic) -> str:
    return f"Sərbəst iş · {topic.title[:60]}"


def _is_checklist(topic, *marks) -> bool:
    """Köhnə çeklist xanası (1 bal, real bal yoxdur) — audit mətni əvvəlki kimi «0/1» qalır."""
    return topic.max_points == 1 and all(mark is None or mark.points is None for mark in marks)


def audit_value(mark, topic) -> str:
    """Audit izində xananın dəyəri: çeklist «1»/«0», bal «4» / «4.5», qiymətsiz «—»."""
    if _is_checklist(topic, mark):
        return "1" if (mark is not None and mark.done) else "0"
    return rules.display(rules.effective_points(mark, topic)) if rules.is_graded(mark) else "—"


# ── Mövzular ─────────────────────────────────────────────────────────────────


@transaction.atomic
def add_selfwork_topic(*, offering, title) -> SelfWorkTopic | None:
    """Yeni sərbəst iş mövzusu — sillabus strukturuna tabe.

    Strukturlu jurnalda (2 × 5 / 1 × 10 / 10 × 1) yalnız BOŞ slot doldurulur (N-dən
    artıq mövzu yoxdur); strukturu hələ tətbiq olunmamış jurnalda əvvəl struktur
    qurulur. Köhnə çeklist jurnalında əvvəlki qayda: ≤10 mövzu × 1 bal (Σ ≤ 10)."""
    title = (title or "").strip()
    if not title or journal_is_locked(offering):
        return None
    structure.lock_offering(offering)  # paralel «+ mövzu» Σ ≤ 10 həddini keçməsin
    plan = structure.ensure_structure(offering)
    topics = structure.offering_topics(offering)
    slot = structure.next_topic_slot(plan, topics)
    if slot is None:
        return None
    slot_index, max_points = slot
    structure.ensure_selfwork_component(offering)
    return SelfWorkTopic.objects.create(
        organization=offering.organization,
        offering=offering,
        title=title[:255],
        order=max((topic.order for topic in topics), default=0) + 1,
        slot_index=slot_index,
        max_points=max_points,
    )


def topic_delete_block_reason(topic) -> str:
    """Mövzu silinə bilməzsə səbəb kodu: ``folder_marks`` (fənn qovluğu balı var) və ya ``""``."""
    has_folder_marks = (
        SelfWorkMark.objects.filter(topic=topic, source=rules.SOURCE_SUBJECT_FOLDER)
        .filter(Q(done=True) | Q(points__isnull=False))
        .exists()
    )
    return "folder_marks" if has_folder_marks else ""


@transaction.atomic
def delete_selfwork_topic(*, topic, by_user=None) -> bool:
    """Mövzunu sil. İşarələr də silinir (CASCADE) → giriş balı düşür, yəni akademik
    nəticə dəyişir; itən təhvillər/ballar audit izinə yazılır (2026-08 auditi).

    Fənn qovluğundan gələn balı olan mövzu SİLİNMİR (bal yalnız sənədli düzəlişlə dəyişir)."""
    if journal_is_locked(topic.offering) or topic_delete_block_reason(topic):
        return False
    offering, title = topic.offering, topic.title
    # Bal = təhvil (DB CHECK) — ``done`` süzgəci bütün qiymətli işarələri tutur.
    losing = list(SelfWorkMark.objects.filter(topic=topic, done=True).select_related("enrollment__student"))
    try:
        topic.delete()  # Correction evidence varsa PROTECT akademik tarixi saxlayır.
    except ProtectedError:
        return False
    # Silinmiş obyektin sahələri yaddaşda qalır — audit dəyəri (çeklist «1», bal «4») onlardan.
    grade_audit.log_grade_changes(
        offering=offering,
        by_user=by_user,
        kind="component",
        changes=[
            {
                "student": grade_audit.student_label(mark.enrollment),
                "item": f"Sərbəst iş · {(title or '')[:60]}",
                "old": audit_value(mark, topic),
                "new": "—",
            }
            for mark in losing
        ],
    )
    return True


# ── İşarə / bal ──────────────────────────────────────────────────────────────


def _target(topic, mark, done, points):
    """İstənən vəziyyət ``(done, points)`` və ya ``None`` (etibarsız istək)."""
    if points is UNSET:
        if topic.max_points == 1 or not done:
            return bool(done), None
        # Bal mövzusunda balsız «təhvil» mənasızdır: artıq qiymətlidirsə dəyişmir.
        return (True, mark.points) if rules.is_graded(mark) else None
    try:
        value = rules.parse_points(points)
    except ValueError:
        return None
    if value is None:
        return False, None
    if value <= 0 or value > topic.max_points:
        return None
    return True, (None if topic.max_points == 1 else value)


@transaction.atomic
def set_selfwork_mark(
    *, offering, topic_id, enrollment_id, done, by_user=None, allow_locked=False, points=UNSET
) -> bool:
    """Təhvil işarəsi (çeklist) və ya BAL (bal strukturlu mövzu) — jurnal mənbəyi.

    * çeklist mövzusu (``max_points=1``): ``done`` 1/0 (əvvəlki davranış);
    * bal mövzusu: ``points`` = 0 < bal ≤ max (``None`` / ``""`` = «—», qiymət yox);
    * ``allow_locked`` — YALNIZ sənədli düzəliş/geri alma yolu: 2 saat pəncərəsini
      və fənn qovluğu balının oxu-only qorumasını keçir.
    Qaytarır: ``True`` (yazıldı və ya dəyişiklik yoxdur), ``False`` (qəbul olunmadı)."""
    if journal_is_locked(offering):
        return False
    topic_pk, enrollment_pk = parse_uuid(topic_id), parse_uuid(enrollment_id)
    if topic_pk is None or enrollment_pk is None:
        return False
    topic = SelfWorkTopic.objects.filter(pk=topic_pk, offering=offering).first()
    # Codex audit §14 (2026-09-13): «oxu → yaz» — iki paralel toggle eyni tələbə
    # üçün `uniq_selfwork_topic_enrollment`-ə çırpılırdı; qeydiyyat sətri
    # kilidlənir (sıra: açılış → qeydiyyat → işarə).
    enrollment = (
        offering.enrollments.filter(pk=enrollment_pk, status=Enrollment.Status.ENROLLED).select_for_update().first()
    )
    if topic is None or enrollment is None:
        return False
    mark = SelfWorkMark.objects.select_for_update().filter(topic=topic, enrollment=enrollment).first()
    target = _target(topic, mark, done, points)
    if target is None:
        return False
    new_done, new_points = target
    now = timezone.now()
    if mark is None:
        if not new_done:
            return True  # onsuz da yoxdur
        old = audit_value(None, topic)
        mark = SelfWorkMark.objects.create(
            organization=offering.organization,
            topic=topic,
            enrollment=enrollment,
            done=True,
            points=new_points,
            source=rules.SOURCE_JOURNAL,
            graded_at=now,
            entered_by=by_user,
        )
    else:
        if (bool(mark.done), mark.points) == (new_done, new_points):
            return True
        if not allow_locked and rules.is_graded(mark):
            if mark.source == rules.SOURCE_SUBJECT_FOLDER:
                return False  # fənn qovluğu balı — yalnız sənədli düzəliş
            if (now - mark.updated_at) > MARK_EDIT_WINDOW:
                return False  # verilmiş işi 2 saatdan sonra geri almaq/dəyişmək olmaz (İKT keçir)
        old = audit_value(mark, topic)
        mark.done = new_done
        mark.points = new_points
        mark.graded_at = now if new_done else None
        mark.entered_by = by_user
        mark.save(update_fields=["done", "points", "graded_at", "entered_by", "updated_at"])
    grade_audit.log_grade_changes(
        offering=offering,
        by_user=by_user,
        kind="component",
        changes=[
            {
                "student": grade_audit.student_label(enrollment),
                "item": _audit_item(topic),
                "old": old,
                "new": audit_value(mark, topic),
            }
        ],
    )
    return True


__all__ = [
    "UNSET",
    "add_selfwork_topic",
    "audit_value",
    "delete_selfwork_topic",
    "set_selfwork_mark",
    "topic_delete_block_reason",
]
