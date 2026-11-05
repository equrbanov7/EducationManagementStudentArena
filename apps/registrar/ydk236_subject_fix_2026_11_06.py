"""236 YDK «Ümumi xarici dil» — kataloq kartı QKU-2693 səhv adla gəlmişdi (sahib 2026-11-06).

Sahib: «Ümumi xarici dil olaraq düzəlt getsin — köhnə sistemdə ad elə gəlibsə, deməli elədir.» Köhnə sistemdə
fənn 2693 = «Ümumi xarici dil» (60 s, Albina Qasımova, 236 YDK); kart QKU-2693 isə «Vo İP sistemlərinin
təhlükəsizliyi» adı ilə idi (əsl VoİP = QKU-2577). Ona görə:

* QKU-2693 kartı → «Ümumi xarici dil», kafedra «Xarici dillər» (236 YDK jurnalı və yük sətri öz-özünə düzəlir);
* həmin karta səhvən bağlanmış 233 İ az / ing BOŞ (dərssiz) payız jurnalları QKU-2577-dəki əsl VoİP jurnallarına
  birləşir (``Merger``);
* yaz 2233İ boş jurnalı və yük sətri QKU-2577-yə keçir (mövcud ``fix_offering_subject`` əmri).

Yalnız id-lər; idempotent.
"""

from __future__ import annotations

import re
from io import StringIO

from django.apps import apps as django_apps
from django.core.management import call_command
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .twin_merge import Merger

SUBJECT = "11e49bcc-2cea-4092-9af7-e8756fcefcf9"
NAME = "Ümumi xarici dil"
CHAIR = "b17f7d56-7690-47ab-90c4-6cd3d402951a"
REASON = "Sahib 2026-11-06: QKU-2693 köhnə sistemdə «Ümumi xarici dil»dir (236 YDK) — kart adı düzəldildi"
TWIN_PAIRS = (
    {"source": "b362b194-81ae-424e-ba4f-ccc1231226f6", "target": "73b15d03-e3c1-4834-a9cc-6d4d2e099554"},
    {"source": "9fe17b43-a44b-496b-8881-d86a5eb7a41b", "target": "0574e663-0ce9-4522-9241-01b7ee0bd0fc"},
)
SPRING_OFFERING = "77dc32fb-9474-491e-a569-41e44fa0aa0d"
SPRING_ROW = "96a44df4-5f88-4324-95fa-3ada640f4aa0"
VOIP_SUBJECT = "5978ae05-0e59-4d65-a072-cd660faf49e9"


def run(*, organization, actor, counts, apply=False) -> None:
    Merger(organization=organization, actor=actor, counts=counts).run(
        [dict(pair, target_marks="keep") for pair in TWIN_PAIRS]
    )
    _spring(organization, actor, counts, apply)
    _rename(organization, actor, counts)


def _spring(organization, actor, counts, apply) -> None:
    Offering = django_apps.get_model("registrar", "CourseOffering")
    if Offering.objects.filter(organization=organization, pk=SPRING_OFFERING, subject_id=VOIP_SUBJECT).exists():
        counts["spring_already_fixed"] += 1
        return
    if not Offering.objects.filter(organization=organization, pk=SPRING_OFFERING).exists():
        counts["spring_missing"] += 1
        return
    out = StringIO()
    args = ["--org", organization.slug, "--actor", actor.username, f"--offering={SPRING_OFFERING}"]
    args += [f"--subject={VOIP_SUBJECT}", f"--row={SPRING_ROW}"] + (["--apply"] if apply else [])
    call_command("fix_offering_subject", *args, stdout=out)
    for line in out.getvalue().splitlines():
        if line.startswith("offering_subject_fix: ") and "=" in line:
            for pair in line.split()[1:]:
                key, _, value = pair.partition("=")
                if re.fullmatch(r"[a-z_]+", key) and value.isdigit():
                    counts[f"spring_{key}"] += int(value)


def _rename(organization, actor, counts) -> None:
    Subject = django_apps.get_model("registrar", "Subject")
    subject = Subject.objects.filter(organization=organization, pk=SUBJECT).first()
    if subject is None:
        counts["subject_missing"] += 1
        return
    if subject.name == NAME and str(subject.chair_unit_id) == CHAIR:
        counts["subject_already_renamed"] += 1
        return
    old = {"name": subject.name, "chair_unit": str(subject.chair_unit_id or "")}
    Subject.objects.filter(pk=subject.pk).update(name=NAME, chair_unit_id=CHAIR, updated_at=timezone.now())
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=subject,
        old_values=old,
        new_values={"name": NAME, "chair_unit": CHAIR},
        reason=REASON,
    )
    counts["subject_renamed"] += 1
