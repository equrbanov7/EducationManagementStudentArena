"""RİM müraciətləri 2026-11-05 — sabit id-li düzəlişlər (sahib: «Aydının və digər müəllimlərin problemlərini fix elə»).

Şifrəli plan faylı əvəzinə cütlər burada sabitdir (YALNIZ id-lər, şəxsi məlumat yoxdur). Hər iş mövcud, sınanmış
qaydalarla gedir:

* **MR-190** (Aydın Yusifov) — köhnə sistemin qayıb/seminar balları əkiz jurnaldadır (köhnə fənn adı altında), müəllim
  isə rəsmi jurnalda işləyir → :class:`.twin_merge.Merger` W → T. T-də artıq xana olan cütlər ``target_marks: keep``
  (T-ninki qalır). 235 İ ing əkizi imtahana bağlıdır (``source_linked_elsewhere``) — burada YOXDUR.
* **MR-161** (Ədilağa Məlikov) — 234 M rus: boş əkiz «İntensiv təsərrüfatların yaradılması» jurnalı datalı jurnala
  birləşir (:mod:`.twin_merge_empty`); fənn sonra ``fix_offering_subject`` ilə yerində düzəlir.
* **MR-110** — müəllimin təsdiqi ilə 07.10.2026 «Riyazi analiz» qayıbı → «iştirak» (``journal_unlock`` — sənədli
  düzəlişin rəsmi yolu), qayıb saatı yenidən hesablanır, audit.

İdempotentdir: ikinci qaçışda birləşmiş cüt ``already_merged``, xana ``absence_fix_already_present`` sayılır.
"""

from __future__ import annotations

from django.apps import apps as django_apps

from core.audit import log_action
from core.constants import AuditAction

from .twin_merge import Merger
from .twin_relocate import recompute_absences

PAIRS = (
    # MR-190 · 235 KE ing «Web texnologiyalar» (QKU-2517) → «Veb texnologiyalar» (QKU-2689); T boşdur.
    {"source": "d3997166-2418-4357-89bc-313c6b0bd69b", "target": "561c4324-49f0-4dd1-81be-7583ba676ab3"},
    # MR-190 · 234 İT ing «Verilənlərin bazası sistemləri» (QKU-267) → SAYT-0014; T-də müəllimin yeni dərsləri var.
    {
        "source": "7a2f6737-9363-4f62-96da-5b3a49f5e745",
        "target": "bbc42780-8b70-4e67-b237-2d7b06b56426",
        "target_marks": "keep",
    },
    # MR-190 · 234 K ing — eyni müəllim, eyni əkiz.
    {
        "source": "27c23c9d-3331-45fb-9856-5b666ba434a4",
        "target": "155b8a8b-42e1-4e77-b832-e8273979ff83",
        "target_marks": "keep",
    },
    # MR-161 · 234 M rus — boş əkiz (QKU-2536) datalı jurnala (QKU-1817); fənn sonra fix_offering_subject ilə.
    {"source": "47fd2c25-ecf0-4c61-b144-e121ee073e0c", "target": "cd5c8ee3-304e-44a9-8d52-dd98c8ac756a"},
)

MR110_MARK = "e5fd4de0-53fe-46f6-b06a-8b9329c3355c"
MR110_ENROLLMENT = "9076d556-c88c-49e0-88f7-90e3b93341f6"
MR110_OFFERING = "9a8f672d-8918-415a-bb7f-100157bf3279"
MR110_REASON = "MR-000110: müəllimin təsdiqi — 07.10.2026 dərsində tələbə iştirak edib (RİM 2026-11-05)"


def fix_mr110_mark(*, organization, actor, counts) -> None:
    """Tək xana: ``absent`` → ``present`` (yalnız gözlənilən jurnal + qeydiyyat + balsız xana)."""

    from core.rls import journal_unlock

    LessonMark = django_apps.get_model("registrar", "LessonMark")
    mark = (
        LessonMark.objects.select_for_update()
        .select_related("enrollment")
        .filter(
            organization=organization,
            pk=MR110_MARK,
            enrollment_id=MR110_ENROLLMENT,
            lesson__offering_id=MR110_OFFERING,
        )
        .first()
    )
    if mark is None:
        counts["absence_fix_missing"] += 1
        return
    if mark.status == "present":
        counts["absence_fix_already_present"] += 1
        return
    if mark.status != "absent" or mark.score is not None:
        counts["absence_fix_unexpected"] += 1
        return
    with journal_unlock():
        LessonMark.objects.filter(pk=mark.pk).update(status="present")
    recompute_absences([mark.enrollment])
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=mark,
        old_values={"status": "absent"},
        new_values={"status": "present"},
        reason=MR110_REASON,
        resource_type="registrar.LessonMark",
        resource_id=str(mark.pk),
    )
    counts["absence_fix_applied"] += 1


def run(*, organization, actor, counts) -> None:
    Merger(organization=organization, actor=actor, counts=counts).run([dict(pair) for pair in PAIRS])
    fix_mr110_mark(organization=organization, actor=actor, counts=counts)
