"""RİM müraciətləri 2026-11-07 (ikinci paket) — sabit id-li düzəlişlər (sahib: «müraciətləri həll et, təsdiq gözləmə»).

* **MR-000221** (Aida Heydərova, 233 K/İT/CM ing «İnformasiya texnologiyaları»): müəllimin real dərsləri və xanaları
  köhnə sistemdən «İnformasiya texnologiyaları (ixtisas üzrə)» (QKU-845) əkiz jurnallarına düşüb, yükün bağlı olduğu
  rəsmi QKU-1047 jurnalları isə boşdur — ona görə seminar yazmaq olmur. Əkizlər rəsmi jurnala birləşir
  (``Merger``, hədəf boşdur → ``keep``).

* **MR-000188** (Günay Əmirova / Yeganə Hidayətova, 434 R «İxtisasyönümlü xarici dil-3»): qrup iki alt qrupa bölünüb
  (köhnə sistemdə 14702 — Yeganə, 10 tələbə; 14703 — Günay, 9 tələbə; 29.10 midterm siyahısı ilə təsdiqlənir).
  EMS-də tək jurnal və hər iki müəllimin TAM payı var. Hər payın tələbə siyahısı alt qrupa görə qoyulur — Günay
  yalnız öz 9 tələbəsini, sahib Yeganə isə öz 10 tələbəsini + heç bir alt qrupa yazılmamış qalanları görür
  (:func:`apps.registrar.journal_shares.journal_scope`). Silinmə yoxdur.

İdempotentdir. Şəxsi məlumat yoxdur — YALNIZ id-lər.
"""

from __future__ import annotations

from django.apps import apps as django_apps

from core.audit import log_action
from core.constants import AuditAction

from .twin_merge import Merger

MR221_PAIRS = (
    {
        "source": "b82be176-b764-4a6e-9d29-16220fb62ac2",  # 233 CM ing, QKU-845 → QKU-1047
        "target": "a1a8beee-8f31-49a4-a052-18c13e4ec772",
        "target_marks": "keep",
    },
    {
        "source": "2778bb99-6c4a-4ca3-968b-69591771f417",  # 233 İT ing, QKU-845 → QKU-1047
        "target": "e8df0411-fc94-4e0f-a945-73b983d949c9",
        "target_marks": "keep",
    },
)

MR188_OFFERING = "dee9eb13-fbec-49e4-9178-0c3fda81bf94"
MR188_OWNER = 8227  # Yeganə Hidayətova
MR188_SPLIT = {
    8227: (5289, 5269, 5272, 5282, 5267, 5288, 5273, 5280, 5266, 5283),
    8373: (5405, 5407, 5408, 5277, 5286, 5281, 5271, 5285, 5287),  # Günay Əmirova
}
MR188_REASON = "MR-000188: 434 R iki alt qrup (köhnə 14702/14703 + 29.10 midterm siyahısı) — paylara tələbə siyahısı"


def split_mr188(*, organization, actor, counts) -> None:
    from .journal_shares import forget

    Offering = django_apps.get_model("registrar", "CourseOffering")
    Share = django_apps.get_model("registrar", "JournalShare")
    Enrollment = django_apps.get_model("registrar", "Enrollment")
    offering = Offering.objects.filter(organization=organization, pk=MR188_OFFERING, is_active=True).first()
    if offering is None or offering.instructor_id != MR188_OWNER:
        counts["split_offering_changed_skipped"] += 1
        return
    for teacher_id, students in MR188_SPLIT.items():
        share = (
            Share.objects.filter(organization=organization, offering=offering, teacher_id=teacher_id, is_active=True)
            .order_by("created_at")
            .first()
        )
        if share is None:
            counts["split_share_missing_skipped"] += 1
            continue
        rows = list(
            Enrollment.objects.filter(offering=offering, student_id__in=students, status="enrolled").values_list(
                "pk", flat=True
            )
        )
        if len(rows) != len(students):
            counts["split_roster_changed_skipped"] += 1
            continue
        current = set(share.enrollments.values_list("pk", flat=True))
        if current == set(rows):
            counts["split_share_already_split"] += 1
            continue
        share.enrollments.set(rows)
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=share,
            old_values={"enrollments": sorted(str(pk) for pk in current)},
            new_values={"enrollments": sorted(str(pk) for pk in rows)},
            reason=MR188_REASON,
        )
        counts["split_shares_split"] += 1
        counts["split_students_assigned"] += len(rows)
    forget(offering)


def run(*, organization, actor, counts) -> None:
    Merger(organization=organization, actor=actor, counts=counts).run([dict(pair) for pair in MR221_PAIRS])
    split_mr188(organization=organization, actor=actor, counts=counts)
