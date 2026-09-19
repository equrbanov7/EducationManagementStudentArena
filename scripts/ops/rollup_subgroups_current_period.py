"""Sahib qərarı 2026-09-20: alt qrup tələbələrini birləşik qrupun jurnalına yığ.

Məs. «234 K az» qrupunun 2026/2027 Payız açılışlarında tələbə yoxdur — uşaqlar
«234 K-1» və «234 K-2»-dədir. Skript CARİ dövrün belə açılışlarını tapır və hər
alt qrup tələbəsini «alt qrupdan əlavə» kimi (provenans + audit, qrup dəyişmir)
birləşik jurnala yazır. Məntiq: apps/registrar/subgroup_rollup.py.

İstehsalda: docker exec -i <app> python manage.py shell < scripts/ops/rollup_subgroups_current_period.py
Yalnız oxumaq: DRY=1 docker exec -i -e DRY=1 <app> python manage.py shell < …
Mühit: ORG_SLUG (default qku), ACTOR (default superadmin), PERIOD_ID (default cari dövr).
"""

import os

from django.contrib.auth import get_user_model

from apps.organizations.models import AcademicPeriod, Organization
from apps.registrar import subgroup_rollup
from core.rls import bypass_rls

DRY = os.environ.get("DRY") == "1"
ORG_SLUG = os.environ.get("ORG_SLUG", "qku")
ACTOR = os.environ.get("ACTOR", "superadmin")
PERIOD_ID = os.environ.get("PERIOD_ID", "")
REASON = "Alt qruplar birləşik qrupun jurnalına yığıldı (sahib qərarı 2026-09-20, TAPŞIRIQ birləşik qrupa verilib)."

User = get_user_model()

with bypass_rls():
    org = Organization.objects.get(slug=ORG_SLUG)
    actor = User.objects.get(username=ACTOR)
    if PERIOD_ID:
        period = AcademicPeriod.objects.get(organization=org, pk=PERIOD_ID)
    else:
        period = AcademicPeriod.objects.get(organization=org, is_current=True, is_active=True)
    print(f"[{'DRY' if DRY else 'APPLY'}] org={org.slug} period={period} actor={actor.username}")
    candidates = subgroup_rollup.find_candidates(org, period)
    for cand in candidates:
        print(
            f"  {cand.offering.group.name} · {cand.offering.subject.code} {cand.offering.subject.name}"
            f" ← {', '.join(f'{g.name}' for g in cand.subgroups)} ({len(cand.records)} tələbə)"
        )
    report = subgroup_rollup.rollup(org, period, by_user=actor, reason=REASON, dry=DRY)
    print(
        f"offerings={report['offerings']} added={report['added']} "
        f"skipped_present={report['skipped_present']} errors={len(report['errors'])}"
    )
    for err in report["errors"]:
        print("  ERR", err)
