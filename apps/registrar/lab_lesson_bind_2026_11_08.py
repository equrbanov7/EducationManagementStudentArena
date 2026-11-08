"""Qrupsuz yazılmış lab dərsini lab qrupuna bağla (sahib 2026-11-08: «Bəli, bağla»).

236 EM «Fizikanın əsasları» 03.11 lab dərsi jurnal Lab-1 / Lab-2-yə bölünməmişdən (2026-11-07) əvvəl yazılıb — qrupsuz
qaldığı üçün Lab-2-nin 18 xanası boş görünürdü. Xanaların 19-u Lab-1-in bütün tələbələrinə, biri bir Lab-2 tələbəsinədir.
Dərs Lab-1-ə bağlanır; həmin Lab-2 tələbəsinin qeydi SİLİNMİR — qrid onu «əvvəlki qrupun dərsi» kimi oxunan göstərir
və qayıb/bal hesabında qalır (:mod:`apps.registrar.lab_groups`). Servisin «başqa qrupun qeydi varsa dəyişmə» qaydası
burada şüurlu olaraq keçilir (sahibin qərarı) — qoruyucular: dərs lab növündədir, açılış dəyişməyib, qrup jurnalda
var, qeydli tələbələrin ÇOXU hədəf qrupdadır, dərs hələ qrupsuzdur. ``--undo`` yalnız bu əmrin bağladığı və dəyişməmiş
dərsi qrupsuz edir.
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps

from core.audit import log_action
from core.constants import AuditAction

from . import lab_groups

REASON = "Sahib 2026-11-08: qrupsuz lab dərsi (jurnal bölünməmişdən əvvəl yazılıb) Lab qrupuna bağlandı"
UNDO_REASON = "Sahib 2026-11-08: lab dərsinin qrup bağının geri qaytarılması"
RESOURCE = "registrar.lab_lesson_bind"
#: (dərs, açılış, lab qrupu)
PLAN = (
    ("0a0d7a39-386f-4479-af71-e89156a2fa4c", "2c802889-5118-4712-89f6-97e850824d63", 1),
    # 236 K Fizika 27.10 lab (audit 3): 9 Lab-1 qeydi + 1 Lab-2 (İsmayılova M.) — eyni hal, Lab-1.
    ("befdb559-0dfe-461f-a0ba-9c9039e11cef", "0d82dc92-f3b3-44b0-85a4-386b5036c5c6", 1),
)


def _model(name):
    return django_apps.get_model("registrar", name)


def _majority(lesson, group) -> bool:
    groups = Counter(_model("LessonMark").objects.filter(lesson=lesson).values_list("enrollment__lab_group", flat=True))
    return groups.get(group, 0) * 2 > sum(groups.values())


def run(*, organization, actor, counts, undo=False) -> None:
    Lesson = _model("Lesson")
    for lesson_id, offering_id, group in PLAN:
        lesson = (
            Lesson.objects.select_for_update()
            .select_related("offering")
            .filter(organization=organization, pk=lesson_id, offering_id=offering_id)
            .first()
        )
        if lesson is None or lesson.kind != "lab":
            counts["lesson_missing_or_not_lab"] += 1
            continue
        if undo:
            if lesson.lab_group != group:
                counts["undo_not_bound"] += 1
                continue
            lesson.lab_group = None
            lesson.save(update_fields=["lab_group", "updated_at"])
            counts["undo_unbound"] += 1
            log_action(
                AuditAction.UPDATE,
                user=actor,
                organization=organization,
                obj=lesson,
                old_values={"lab_group": group},
                new_values={"lab_group": None},
                reason=UNDO_REASON,
                resource_type=RESOURCE,
                resource_id=str(lesson.pk),
            )
            continue
        if lesson.lab_group == group:
            counts["already_bound"] += 1
        elif lesson.lab_group is not None:
            counts["bound_elsewhere_skipped"] += 1
        elif group not in lab_groups.offering_groups(lesson.offering):
            counts["group_missing_skipped"] += 1
        elif not _majority(lesson, group):
            counts["marks_not_majority_skipped"] += 1
        else:
            lesson.lab_group = group
            lesson.save(update_fields=["lab_group", "updated_at"])
            counts["bound"] += 1
            log_action(
                AuditAction.UPDATE,
                user=actor,
                organization=organization,
                obj=lesson,
                old_values={"lab_group": None},
                new_values={"lab_group": group},
                reason=REASON,
                resource_type=RESOURCE,
                resource_id=str(lesson.pk),
            )


__all__ = ["PLAN", "REASON", "run"]
