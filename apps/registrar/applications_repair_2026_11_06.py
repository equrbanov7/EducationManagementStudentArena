"""RİM müraciətləri 2026-11-06 — sabit id-li düzəlişlər (sahib: «müraciətləri həll et, təsdiq gözləmə»).

* **MR-000236** (Reyhan Əhmədova, 136 Si-2): köhnə sistemdə «Psixologiya 136Si2» jurnalı səhvən «Çapaqədər, çap və
  çapdan sonrakı proseslərdə komputer texnikası…» fənninə bağlanmışdı (köhnə 15136/15137, fənn 1797) — köçürmədə
  jurnal həmin adla gəldi. Onun dərsləri və xanaları qrupun «Psixologiya» jurnalına birləşir (``Merger``, keep).

* **Murad Əkbərli** (sahib 2026-11-06: «Murad Əkbərlinin bütün jurnallarında uşaq sayında problem var — siyahıda 25,
  içəridə 1»): jurnalların sahibidir və bütün yükü (mühazirə + seminar) ondadır, amma köhnə sistemdən gələn
  ``JournalShare`` sətirləri (öz 1-2 tələbəlik payı + köhnə/passiv müəllimin 24-30 tələbəlik payı + başqa sektorun
  müəlliminin mühazirə payı) onun görünüşünü daraldırdı. Bu 7 jurnalda bütün aktiv paylar söndürülür (silinmir) —
  sahib tam jurnalı görür.

İdempotentdir. Şəxsi məlumat yoxdur — YALNIZ id-lər.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .twin_merge import Merger

MR236_PAIRS = (
    {
        "source": "45985e6b-0500-42e8-a80c-cfc4243601a3",
        "target": "e2a4155d-8e96-41e8-bc92-d635eb306429",
        "target_marks": "keep",
    },
)


MURAD_TEACHER = 9530
MURAD_OFFERINGS = (
    "cf82f7b6-5f85-42f2-8d40-8100540e0a7a",
    "8ebdadee-c42d-4aa3-a104-e1858f641842",
    "cc1a642b-9afc-4944-acc2-8b17e854759e",
    "cc34852b-18c2-400b-850c-8585bc54b5ad",
    "cd635763-18d6-438d-aa98-c9e4a13396fe",
    "c3404a1a-7654-443a-b5c7-76a03aa5e681",
    "130364c1-6958-48ea-bca3-09e0dc75ba71",
)
MURAD_REASON = "Sahib 2026-11-06: köhnə sistemdən gələn dar paylar sahibin (Murad Əkbərli) jurnal görünüşünü daraldırdı"


def release_murad_shares(*, organization, actor, counts) -> None:
    from .journal_shares import forget

    Offering, Share = django_apps.get_model("registrar", "CourseOffering"), django_apps.get_model(
        "registrar", "JournalShare"
    )
    for offering in Offering.objects.filter(organization=organization, pk__in=MURAD_OFFERINGS):
        if offering.instructor_id != MURAD_TEACHER:
            counts["murad_offering_owner_changed_skipped"] += 1
            continue
        shares = list(Share.objects.filter(organization=organization, offering=offering, is_active=True))
        if not shares:
            counts["murad_offering_already_full"] += 1
            continue
        Share.objects.filter(pk__in=[share.pk for share in shares]).update(is_active=False, updated_at=timezone.now())
        forget(offering)
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=offering,
            old_values={"active_shares": [str(share.pk) for share in shares]},
            new_values={"active_shares": []},
            reason=MURAD_REASON,
        )
        counts["murad_shares_deactivated"] += len(shares)
        counts["murad_offerings_fixed"] += 1


def run(*, organization, actor, counts) -> None:
    Merger(organization=organization, actor=actor, counts=counts).run([dict(pair) for pair in MR236_PAIRS])
    release_murad_shares(organization=organization, actor=actor, counts=counts)
