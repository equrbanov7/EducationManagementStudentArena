"""«Xaric olanlar» konteynerindəki tələbələrin girişini bağlayır (prod).

NİYƏ. 2026-09-05 QA auditi (P1-10 + P2-8) tapdı: köçürmədə «Xaric olunanlar» /
«Xaric olanlar» adlı psevdo-qruplara yığılan tələbələrin STATUSU heç vaxt
yazılmayıb — akademik qeyd hələ də ``enrolled`` görünür, deməli **girişləri
açıqdır**. Klonda bu 31 nəfər idi. Prod-da eyni qüsur davam edir.

NİYƏ AYRICA PROD-OPS SKRİPTİ (management komandası yox). Auditin
``legacy_repair_pseudo_groups`` komandası Develop-dadır, prod image-i isə
``main``-dən qurulur və orada həmin kod YOXDUR. Bu kanal skripti runner-in
checkout-undan stdin ilə ötürür, yəni deploy gözləmədən işləyir; skript isə
YALNIZ prod image-ində MÖVCUD OLAN səthləri çağırır.

NƏ EDİR (iki addım, hər ikisi mövcud, review olunmuş yollarla):

1. ``apps.registrar.movements.create_movement(kind=EXPULSION, …)`` — xam
   ``UPDATE`` YOXDUR: state maşını + append-only ``StudentMovement`` ledger
   sətri + audit.
2. Profilin ``access_state``-ini ``archived`` edir — giriş məhz orada bağlanır
   (``identity.user_access_is_login_blocked``). Develop-da bunu
   ``movements._sync_access_state`` avtomatik edir, prod image-ində o kod hələ
   yoxdur, ona görə burada AÇIQ addımdır. ``active → archived`` keçidi
   məhdudlaşdırıcı olduğu üçün 0016-nın trigger-i onu bloklamır.

NƏ ETMİR. «Level 2025-2026» (228 real tələbə) və ``Silinmelidir`` qruplarına
TOXUNMUR — onlar data-təmizliyi qərarıdır, təhlükəsizlik məsələsi deyil.
Vahidləri «xidməti» kimi işarələmək də burada YOXDUR: o sahə (``is_service_unit``)
prod sxemində hələ yoxdur, deploy-dan sonra komanda ilə edilir.

DEFAULT DRY-RUN. ``REPAIR_APPLY=yes`` verilməyibsə heç nə yazılmır.
İDEMPOTENT: artıq ``expelled``/``graduated`` olan qeyd atlanır, artıq
``archived`` olan profil toxunulmur.

Mühit dəyişənləri:
    REPAIR_ORG     təşkilat slug (default: qerbi-kaspi-universiteti)
    REPAIR_APPLY   "yes" → faktiki yazır
    REPAIR_ACTOR   əməliyyatı aparan istifadəçi adı (boş = təşkilat sahibi)
    REPAIR_ORDER   əmr nömrəsi (audit izində görünür)
"""

import os

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.organizations.models import Organization
from apps.registrar import movements
from apps.registrar.models import MovementKind, StudentAcademicRecord
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

User = get_user_model()

APPLY = (os.environ.get("REPAIR_APPLY") or "").strip().lower() == "yes"
ORG_SLUG = (os.environ.get("REPAIR_ORG") or "qerbi-kaspi-universiteti").strip()
ACTOR_USERNAME = (os.environ.get("REPAIR_ACTOR") or "").strip()
ORDER_NUMBER = (os.environ.get("REPAIR_ORDER") or "LEGACY-XARIC-2026-09").strip()

#: Səbəb mətni ≥20 simvol olmalıdır (aktor qatının qaydası) və audit izində qalır.
REASON = (
    "Legacy köçürmə auditi (2026-09-05): «Xaric olanlar» konteynerindəki qeydlərin "
    "statusu yazılmamışdı, giriş açıq qalmışdı — status rəsmiləşdirilir. "
    "Sənəd: docs/audits/2026-09-05/LEVEL_GROUPS.md"
)

#: Bu statuslardan «xaric» keçidi qanunidir (`movements.RULES` ilə eyni).
EXPELLABLE = ("enrolled", "academic_leave")


def _is_expelled_container(name) -> bool:
    """«Xaric olunanlar» VƏ yazılışı fərqli «Xaric olanlar» — hər ikisi.

    ``"olan"`` ``"olunanlar"``-ın ARDICIL alt-mətni deyil (ol-U-N-an-lar), ona
    görə hər iki yazılış açıq yoxlanılır — auditin §1 tapıntısı.
    """
    text = str(name or "").strip().casefold()
    return "xaric" in text and ("olan" in text or "olunan" in text)


@rls_worker_atomic()
@bypass_rls()
def main():
    organization = Organization.objects.get(slug=ORG_SLUG)
    actor = (
        User.objects.filter(username=ACTOR_USERNAME).first() if ACTOR_USERNAME else getattr(organization, "owner", None)
    )
    if actor is None:
        raise SystemExit(f"Aktor tapılmadı (REPAIR_ACTOR={ACTOR_USERNAME!r}, sahib də boşdur)")

    records = list(
        StudentAcademicRecord.objects.filter(organization=organization)
        .select_related("student", "group", "organization")
        .order_by("group__name", "student__last_name", "student__first_name")
    )
    targets = [record for record in records if record.group is not None and _is_expelled_container(record.group.name)]
    open_targets = [record for record in targets if record.status in EXPELLABLE]

    print("=" * 78)
    print(f"«Xaric olanlar» konteyner təmizliyi · {organization.name} · {'TƏTBİQ' if APPLY else 'DRY-RUN'}")
    print("=" * 78)
    containers = sorted({record.group.name for record in targets})
    print(f"Konteyner: {len(containers)} → {containers}")
    print(f"Konteynerdəki qeyd: {len(targets)} · statusu HƏLƏ AÇIQ olan: {len(open_targets)}")
    print(f"Aktor: {actor.username} · əmr: {ORDER_NUMBER}")
    print("-" * 78)

    profile_ids = {record.student_id for record in open_targets}
    open_profiles = {profile.user_id: profile for profile in UserProfile.objects.filter(user_id__in=profile_ids)}
    for record in open_targets:
        profile = open_profiles.get(record.student_id)
        state = getattr(profile, "access_state", "—")
        name = (record.student.get_full_name() or record.student.username).strip()
        print(f"  {record.student.username:26s} {name[:28]:28s} {record.status:14s} giriş={state}")

    if not APPLY:
        print("-" * 78)
        print("DRY-RUN — heç nə yazılmadı. Yazmaq üçün: REPAIR_APPLY=yes")
        return

    expelled, archived, failed = 0, 0, []
    for record in open_targets:
        try:
            movements.create_movement(
                record=record,
                kind=MovementKind.EXPULSION,
                order_number=ORDER_NUMBER,
                order_date=timezone.localdate(),
                reason=REASON,
                actor=actor,
            )
            expelled += 1
        except Exception as exc:  # noqa: BLE001 — sətir-sətir davam edirik, səbəb çap olunur
            failed.append((record.student.username, f"{type(exc).__name__}: {exc}"))
            continue
        profile = open_profiles.get(record.student_id)
        if profile is not None and profile.access_state != UserProfile.AccessState.ARCHIVED:
            profile.access_state = UserProfile.AccessState.ARCHIVED
            profile.save(update_fields=["access_state"])
            archived += 1

    print("-" * 78)
    print(f"✓ Xaric edildi: {expelled} · girişi bağlandı: {archived} · uğursuz: {len(failed)}")
    for username, error in failed:
        print(f"   ✗ {username}: {error}")


main()
