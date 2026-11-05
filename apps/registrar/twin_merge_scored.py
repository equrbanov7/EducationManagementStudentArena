"""BALLI (Midterm …) və imtahana bağlı əkizin rəsmi jurnala birləşdirilməsi (sahib 2026-11-05: «əkiz jurnalları birləşdir»).

:class:`.twin_merge.Merger` datalı əkizi (W) iki halda QƏSDƏN dayandırır: W-də komponent balı var
(``source_has_scores``) və W imtahana bağlıdır (``source_linked_elsewhere``). 235 İ ing (MR-190) məhz belədir: W-də
köhnə sistemin qayıb/seminar xanaları + onlayn imtahan 83-ün 18 Midterm balı, imtahan W-yə bağlı; müəllim isə rəsmi
jurnalda (T) işləyir. Bu modul əvvəl həmin iki maneəni rəsmi şəkildə T-yə daşıyır, sonra adi ``Merger`` (``keep``) işləyir.

Qaydalar (cüt öz savepoint-ində; nəsə dayanarsa cütün BÜTÜN yazıları geri qaytarılır):

* **bal** — W-nin hər ``ComponentScore``-u T-nin EYNİ növ + addakı komponentinə (aralıq komponenti T-də yoxdursa
  ``interim_components.ensure_kollokviums`` ilə — müəllimin tabı ilə eyni xana), eyni tələbənin T qeydiyyatına.
  Bal, ``entered_by``, ``exam_source`` (cəhd id-si) və ``created_at`` EYNİ qalır — imtahanın təkrar sinxronu
  (``midterm_bridge``) T-də eyni mənbəni tapır və heç nə yazmır. Tavanı fərqli komponent, sənədli düzəlişli və ya
  rubrikalı bal, T-də FƏRQLİ balı olan xana → cüt dayanır (``score_conflict_differs`` …, heç nə yazılmır); T-də
  EYNİ bal varsa W-ninki sadəcə silinir (``scores_duplicate_on_target``). Yazı ``journal_unlock`` ilə (sistem
  yazısının rəsmi yolu), T jurnalının qiymət tarixçəsinə audit (fail-closed);
* **imtahan bağı** — ``Exam.journal_offerings``: W → T (:func:`.twin_merge_empty.repoint_exam_links`);
* sonra ``Merger`` (cütdə ``"target_marks": "keep"``) — dərslər, xanalar, sillabus, cədvəl, W ləğvi; birləşmə
  olmasa (``both_have_marks``, ``source_corrected`` …) yuxarıdakılar da geri qaytarılır (``scored_pair_rolled_back``);
* **jurnal payı** — W-nin aktiv payları T-yə (:class:`.twin_merge_empty.EmptyTwinMerge` qaydası ilə; müəllim T-nin
  sahibidirsə W-də qalır);
* W və T üçün audit — ``changes.manifest`` (köçən balların köhnə/yeni id-ləri, imtahan bağları, paylar).

İdempotentdir: ikinci qaçışda W passivdir → ``already_merged``, 0 yazı.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .twin_merge import Merger
from .twin_merge_empty import EmptyTwinMerge, repoint_exam_links

KIND = "twin_merge_scored"
#: ``Merger``-in birləşdirmədiyi halların sayğacları — dayanma səbəbi ``merger_<açar>`` kimi çıxır.
_MERGER_STOPS = (
    "both_have_marks",
    "source_corrected",
    "source_has_scores",
    "source_linked_elsewhere",
    "target_enrollment_blocked",
    "pair_integrity_error",
    "target_enrollment_inactive",
)
REASON = "Ballı/imtahana bağlı əkiz jurnalın rəsmi jurnala birləşdirilməsi — sahib 2026-11-05 (MR-190/MR-161)"


class PairStop(Exception):
    """Cüt dayanır — səbəb ``counts``-a yazılır, cütün yazıları geri qaytarılır."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _model(name: str):
    return django_apps.get_model("registrar", name)


def _target_enrollment(row, target, existing, actor):
    """T-də tələbənin qeydiyyatı — yoxdursa ``Merger._enrollments`` ilə EYNİ qaydada yaradılır."""

    found = existing.get(row.student_id)
    if found is not None:
        if found.status != "enrolled":
            raise PairStop("score_target_enrollment_inactive")
        return found
    guest = row.source_group_id is not None and row.source_group_id != target.group_id
    try:
        with transaction.atomic():
            found = _model("Enrollment").objects.create(
                organization_id=target.organization_id,
                student_id=row.student_id,
                offering=target,
                kind=row.kind,
                status="enrolled",
                source_group_id=row.source_group_id if guest else None,
                added_by=actor if guest else None,
                added_at=timezone.now() if guest else None,
            )
    except IntegrityError:
        raise PairStop("score_target_enrollment_blocked") from None
    existing[row.student_id] = found
    return found


class ScoreMover:
    """W qeydiyyatlarının komponent ballarını T-yə köçürür (dayanma → :class:`PairStop`)."""

    def __init__(self, *, source, target, actor, counts):
        self.source, self.target, self.actor, self.counts = source, target, actor, counts
        self._components = None

    def _component_for(self, component):
        from .interim_components import ensure_kollokviums

        if self._components is None:
            self._components = {}
        key = (component.kind, component.name.strip().lower())
        if key not in self._components:
            AssessmentComponent = _model("AssessmentComponent")
            lookup = AssessmentComponent.objects.filter(offering=self.target, kind=component.kind)
            found = lookup.filter(name__iexact=component.name.strip()).first()
            if found is None and component.kind == "kollokvium":
                ensure_kollokviums(self.target)
                found = lookup.filter(name__iexact=component.name.strip()).first()
            self._components[key] = found
        found = self._components[key]
        if found is None:
            raise PairStop("score_component_missing_on_target")
        if found.max_score != component.max_score:
            raise PairStop("score_component_max_differs")
        return found

    def _check_source(self, rows) -> None:
        pairs = [(row.component_id, row.enrollment_id) for row in rows]
        components = {component for component, _ in pairs}
        enrollments = {enrollment for _, enrollment in pairs}
        corrections = _model("ComponentScoreCorrection").objects.filter(
            component_id__in=components, enrollment_id__in=enrollments
        )
        if any(pair in pairs for pair in corrections.values_list("component_id", "enrollment_id")):
            raise PairStop("source_score_corrected")
        rubric = _model("CriterionScore").objects.filter(component_id__in=components, enrollment_id__in=enrollments)
        if rubric.exists():
            raise PairStop("source_rubric_scores")

    def move(self) -> list:
        from core.rls import journal_unlock

        ComponentScore, Enrollment = _model("ComponentScore"), _model("Enrollment")
        rows = list(
            ComponentScore.objects.select_for_update(of=("self",))
            .select_related("component", "enrollment")
            .filter(enrollment__offering=self.source)
            .order_by("created_at", "pk")
        )
        if not rows:
            return []
        self._check_source(rows)
        existing = {row.student_id: row for row in Enrollment.objects.select_for_update().filter(offering=self.target)}
        plan = []
        for row in rows:
            component = self._component_for(row.component)
            enrollment = _target_enrollment(row.enrollment, self.target, existing, self.actor)
            kept = ComponentScore.objects.select_for_update().filter(component=component, enrollment=enrollment).first()
            if kept is not None and kept.score != row.score:
                raise PairStop("score_conflict_differs")
            plan.append((row, component, enrollment, kept))
        moved = []
        with journal_unlock():  # 2 saat DB trigger-i — sistem yazısı (midterm_bridge ilə eyni rəsmi yol)
            for row, component, enrollment, kept in plan:
                entry = {"old": str(row.pk), "student": row.enrollment.student_id, "score": str(row.score)}
                if kept is None:
                    created = ComponentScore.objects.create(
                        organization_id=self.target.organization_id,
                        component=component,
                        enrollment=enrollment,
                        score=row.score,
                        entered_by_id=row.entered_by_id,
                        exam_source=row.exam_source,
                    )
                    ComponentScore.objects.filter(pk=created.pk).update(created_at=row.created_at)
                    entry["new"] = str(created.pk)
                    self.counts["scores_moved"] += 1
                else:
                    entry["kept"] = str(kept.pk)
                    self.counts["scores_duplicate_on_target"] += 1
                ComponentScore.objects.filter(pk=row.pk).delete()
                moved.append(entry)
        self._grade_audit(plan)
        return moved

    def _grade_audit(self, plan) -> None:
        from . import grade_audit

        changes = [
            {
                "student": grade_audit.student_label(enrollment),
                "item": component.name,
                "old": grade_audit.score_repr(kept.score if kept is not None else None),
                "new": grade_audit.score_repr(row.score),
                "source": f"twin_merge:{self.source.pk}",
                "note": "əkiz jurnaldan köçürüldü",
            }
            for row, component, enrollment, kept in plan
            if kept is None
        ]
        grade_audit.log_grade_changes(
            offering=self.target, by_user=self.actor, kind="component", changes=changes, fail_closed=True, reason=REASON
        )


class ScoredTwinMerge:
    def __init__(self, *, organization, actor, counts):
        self.organization = organization
        self.actor = actor
        self.counts = counts

    def run(self, pairs) -> None:
        for pair in pairs:
            before = dict(self.counts)
            with transaction.atomic():
                try:
                    self._pair(dict(pair))
                except PairStop as stop:
                    transaction.set_rollback(True)
                    # Geri qaytarılmış yazıların sayları hesabata düşməsin — yalnız dayanma səbəbi qalır.
                    self.counts.clear()
                    self.counts.update(before)
                    self.counts[stop.code] += 1
                    self.counts["scored_pair_rolled_back"] += 1

    def _pair(self, pair) -> None:
        CourseOffering = _model("CourseOffering")
        rows = {
            str(row.pk): row
            for row in CourseOffering.objects.select_for_update(of=("self",)).filter(
                organization=self.organization, pk__in=[pair.get("source"), pair.get("target")]
            )
        }
        source, target = rows.get(str(pair.get("source"))), rows.get(str(pair.get("target")))
        if source is None or target is None:
            self.counts["pair_missing"] += 1
            return
        blocked = Merger._pair_blocked(source, target)
        if blocked:
            self.counts[blocked] += 1
            return
        manifest = {"source": str(source.pk), "target": str(target.pk)}
        manifest["scores"] = ScoreMover(source=source, target=target, actor=self.actor, counts=self.counts).move()
        manifest["exam_links"] = repoint_exam_links(source.pk, target.pk)
        self.counts["exam_links_repointed"] += len(manifest["exam_links"])
        before = dict(self.counts)
        Merger(organization=self.organization, actor=self.actor, counts=self.counts).run([pair])
        if self.counts["pairs_merged"] == before.get("pairs_merged", 0):
            reason = next((key for key in _MERGER_STOPS if self.counts[key] > before.get(key, 0)), "")
            raise PairStop(f"merger_{reason}" if reason else "scored_pair_not_merged")
        students = {
            row.student_id: row
            for row in _model("Enrollment").objects.filter(offering=target).exclude(status__in=("dropped", "suspended"))
        }
        manifest["shares"] = EmptyTwinMerge(
            organization=self.organization, actor=self.actor, counts=self.counts
        )._shares(source, target, students, True)
        # Paylaşılmış sillabus bağı (``SyllabusShare``) Merger-də köçmür — ləğv olunmuş W-də qalanı görünsün.
        left = django_apps.get_model("syllabus", "SyllabusShare").objects.filter(offering=source).count()
        self.counts["syllabus_shares_left_on_source"] += left
        self.counts["pairs_merged_scored"] += 1
        self._audit(source, target, manifest)

    def _audit(self, source, target, manifest) -> None:
        summary = {
            "mode": "scored_source",
            "scores": len(manifest["scores"]),
            "exam_links": len(manifest["exam_links"]),
            "shares": len(manifest["shares"]),
        }
        for obj in (source, target):
            log_action(
                action=AuditAction.UPDATE,
                user=self.actor,
                organization=self.organization,
                obj=obj,
                reason=f"registrar: twin offering merge — {REASON}",
                new_values=summary,
                changes={"kind": KIND, "manifest": manifest},
            )


__all__ = ["KIND", "PairStop", "ScoreMover", "ScoredTwinMerge"]
