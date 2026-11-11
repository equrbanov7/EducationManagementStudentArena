"""Dublikat jurnal birləşməsinin BAL addımları (komponent balı + fərqli xanaların görünən tarixçəsi) — sahib 2026-11-11.

:class:`.duplicate_journal_merge_2026_11_11.JournalMerge`-in hissəsidir (modul ölçüsü həddinə görə ayrıdır). Qaydalar
əsas modulun sənədindədir: komponent balı T-də yoxdursa kopyalanır (mənbə cəhd id-si eyni qalır); fərqlidirsə yalnız
BİRİ imtahandan avtomatikdirsə o qalır, əks halda T-ninki; hər iki dəyər manifestdə və T-nin qiymət tarixçəsindədir.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.utils import timezone

REASON = "Sahib 2026-11-11: dublikat fənn kartının jurnalı əsas jurnala birləşdirildi (heç bir xana/bal itmədən)"
CONFLICT_NOTE = "dublikat jurnal birləşməsi: digər jurnaldakı fərqli dəyər saxlanılmadı (audit manifestində qalır)"


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


class Blocked(Exception):
    """Cüt toxunulmur — savepoint geri qaytarılır, ``reason`` sayılır (yalnız kod; şəxsi məlumat yoxdur)."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class ScoreSteps:
    """``JournalMerge``-in bal addımları — ``self.organization / actor / counts`` əsas sinifdəndir."""

    def _component(self, source_component, target, cache):
        from .interim_components import ensure_kollokviums

        key = (source_component.kind, source_component.name.strip().lower())
        if key not in cache:
            lookup = _model("AssessmentComponent").objects.filter(offering=target, kind=source_component.kind)
            found = lookup.filter(name__iexact=source_component.name.strip()).first()
            if found is None and source_component.kind == "kollokvium":
                ensure_kollokviums(target)
                found = lookup.filter(name__iexact=source_component.name.strip()).first()
            cache[key] = found
        found = cache[key]
        if found is None:
            raise Blocked("score_component_missing_on_target")
        if found.max_score != source_component.max_score:
            raise Blocked("score_component_max_differs")
        return found

    def _scores(self, source, target, by_student, manifest, conflicts) -> None:
        from core.rls import journal_unlock

        from . import grade_audit

        Score = _model("ComponentScore")
        rows = list(
            Score.objects.select_for_update(of=("self",))
            .select_related("component", "enrollment")
            .filter(enrollment__offering=source)
            .order_by("created_at", "pk")
        )
        cache, changes = {}, []
        with journal_unlock():  # 2 saat DB trigger-i — sistem yazısı (midterm_bridge ilə eyni rəsmi yol)
            for row in rows:
                enrollment = by_student.get(row.enrollment.student_id)
                if enrollment is None:
                    self.counts["scores_of_departed_students_left_on_source"] += 1
                    continue
                component = self._component(row.component, target, cache)
                kept = Score.objects.select_for_update().filter(component=component, enrollment=enrollment).first()
                change = {"student": grade_audit.student_label(enrollment), "item": component.name}
                change.update(source=f"duplicate_merge:{source.pk}", note="dublikat jurnaldan köçürüldü")
                if kept is None:
                    created = Score.objects.create(
                        organization=self.organization,
                        component=component,
                        enrollment=enrollment,
                        score=row.score,
                        entered_by_id=row.entered_by_id,
                        exam_source=row.exam_source,
                    )
                    Score.objects.filter(pk=created.pk).update(created_at=row.created_at)
                    manifest["scores_created"].append(str(created.pk))
                    self.counts["scores_copied"] += 1
                    changes.append(
                        {**change, "old": grade_audit.score_repr(None), "new": grade_audit.score_repr(row.score)}
                    )
                    continue
                if kept.score == row.score:
                    self.counts["scores_identical"] += 1
                    continue
                source_wins = bool(row.exam_source) and not kept.exam_source
                conflicts.append(
                    {
                        "type": "score",
                        "student": row.enrollment.student_id,
                        "component": component.name,
                        "source_score": str(row.pk),
                        "target_score": str(kept.pk),
                        "source_value": str(row.score),
                        "target_value": str(kept.score),
                        "kept": "source_exam_result" if source_wins else "target",
                    }
                )
                if not source_wins:
                    self.counts["scores_conflict_target_kept"] += 1
                    changes.append(
                        {
                            **change,
                            "old": grade_audit.score_repr(row.score),
                            "new": grade_audit.score_repr(kept.score),
                            "note": CONFLICT_NOTE,
                        }
                    )
                    continue
                manifest["scores_replaced"].append(
                    [str(kept.pk), str(kept.score), kept.entered_by_id, kept.exam_source]
                )
                changes.append(
                    {
                        **change,
                        "old": grade_audit.score_repr(kept.score),
                        "new": grade_audit.score_repr(row.score),
                        "note": "dublikat jurnal birləşməsi: imtahanın avtomatik nəticəsi saxlanıldı",
                    }
                )
                Score.objects.filter(pk=kept.pk).update(
                    score=row.score,
                    entered_by_id=row.entered_by_id,
                    exam_source=row.exam_source,
                    updated_at=timezone.now(),
                )
                self.counts["scores_conflict_exam_result_kept"] += 1
        grade_audit.log_grade_changes(
            offering=target, by_user=self.actor, kind="component", changes=changes, fail_closed=True, reason=REASON
        )

    def _conflict_history(self, target, conflicts) -> None:
        """Fərqli xanalar T jurnalının qiymət tarixçəsində GÖRÜNƏN qeyd olur (saxlanılmayan dəyər «əvvəlki» kimi)."""
        from . import grade_audit

        Enrollment = _model("Enrollment")
        marks = [item for item in conflicts if item["type"] == "mark"]
        rows = {str(row.pk): row for row in Enrollment.objects.filter(pk__in=[m["target_enrollment"] for m in marks])}
        changes = [
            {
                "student": grade_audit.student_label(rows[item["target_enrollment"]]),
                "item": f"{item['date']} · {item['lesson_kind']}",
                "old": grade_audit.mark_repr(*item["source_value"]),
                "new": grade_audit.mark_repr(*item["target_value"]),
                "source": f"duplicate_merge:{item['source_mark']}",
                "note": CONFLICT_NOTE,
            }
            for item in marks
        ]
        grade_audit.log_grade_changes(
            offering=target, by_user=self.actor, kind="mark", changes=changes, fail_closed=True, reason=REASON
        )


__all__ = ["CONFLICT_NOTE", "REASON", "Blocked", "ScoreSteps"]
