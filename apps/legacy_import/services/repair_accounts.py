"""P0-2 təmiri: e-poçt qüsuruna görə HEÇ BİR hesabı olmayan insanlar.

Qüsur (2026-09-02 auditi).  ``account_cutover`` e-poçtu sınıq (85), boş (1) və ya
İKİ legacy sətrində təkrarlanan (28 = 14 cüt) sətri staging-ə buraxmır.  Nəticə:
**100 tələbə + 14 işçi hədəfdə ümumiyyətlə yoxdur.**  14 cütdə «qalib» seçilmədiyi
üçün ``Xəyalə Balayeva`` kimi real insanlar tam yoxa çıxıb; 12 belə işçiyə bağlı
62 legacy jurnal müəllimsiz qalıb.

Kök səbəb faza qaydasında düzəldilib (``rehearsal_identity_placeholder``): e-poçt
kimlik açarı deyil, ona görə qüsurlu sətir artıq deterministik yer-tutucu
e-poçtla staged olunur.  Bu modul isə ARTIQ KÖÇÜRÜLMÜŞ hədəf üçündür.

Niyə fazanı hədəflənmiş şəkildə təkrar icra etmirik.  Ledger sətirləri ``run_id``
ilə möhürlənib və ``upsert_entity_map`` eyni legacy açar üçün FƏRQLİ derivation
hash-ı ``legacy_entity_identity_conflict`` ilə rədd edir; ``transform_version``
də policy-dən törəyir.  Yəni faza təkrarı ya rədd olunur, ya da sübut zəncirini
yenidən yazır — hər ikisi qadağandır.  Ona görə burada MİNİMAL, auditli yol
seçilib: hesab + üzvlük **mövcud accounts servisləri ilə** (eyni qapılar) qurulur.

Nə YARADILIR
------------
* ``stage_imported_account`` → kilidli staged hesab (username ``myedu.{tip}.{id}``,
  e-poçt yer-tutucu, ``email_verified=False``, parol istifadəsiz);
* ``activate_staged_account`` → hesab aktiv, üzvlük aktiv (student / teacher rolu);
* müəllimlər üçün: mənbədəki ``journals.teacher_id`` uyğunluğuna görə
  **müəllimsiz** ``CourseOffering`` sətirlərinə ``instructor`` yazılır.

Nə YARADILMIR (açıq şəkildə qalıq iş)
-------------------------------------
* ``StudentAcademicRecord`` / ``Enrollment`` / jurnal xanaları — onlar faza
  zəncirinin (placement → sar → J1..J9) məhsuludur və yalnız TAM repetisiya ilə
  düzgün qurula bilər.  Yəni bu 100 tələbənin akademik tarixçəsi hədəfə ancaq
  növbəti tam repetisiyada düşür; bu əmr onların GİRİŞİNİ və kimliyini bərpa edir.
* Ledger sətirləri: mövcud (quarantined) ``LegacyEntityMap`` sətri OLDUĞU KİMİ
  qalır — sübut yenidən yazılmır.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from django.apps import apps as django_apps
from django.db import transaction

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue

from .field_contracts import JOURNAL_FIELDS, STUDENT_IDENTITY_FIELDS, WORKER_IDENTITY_FIELDS
from .legacy_text import clean_text
from .rehearsal_identity_placeholder import placeholder_email
from .rehearsal_placement_phase import _legacy_fin
from .rehearsal_journal_offerings_targets import COURSE_OFFERING_ENTITY_TYPE
from .repair_archive import evidence_digest
from .source_extraction import open_audited_identity_stream, open_audited_source_stream

AUDIT_REASON = "legacy_repair:missing_accounts"
EVIDENCE_REASON_CODE = "institution_registry_match"
NAME_MAX_LENGTH = 150
PATRONYMIC_MAX_LENGTH = 100

_COHORTS = (("student", STUDENT_IDENTITY_FIELDS), ("worker", WORKER_IDENTITY_FIELDS))
TABLE_HEADERS = ("tip", "legacy", "username", "ad soyad", "ledger vəziyyəti", "səbəb", "qərar")


@dataclass(frozen=True)
class MissingAccount:
    entity_type: str
    legacy_pk: int
    username: str
    first_name: str
    last_name: str
    patronymic: str
    ledger_state: str
    rule_codes: tuple[str, ...]
    action: str
    #: R-9: SAR mərhələsi üçün lazım olan proyeksiya sətri (qrup/il/FİN).
    projected_row: object = None

    def as_row(self):
        return (
            self.entity_type,
            self.legacy_pk,
            self.username,
            f"{self.first_name} {self.last_name}".strip()[:28],
            self.ledger_state,
            ",".join(self.rule_codes)[:46],
            self.action,
        )


def _blocked_maps(organization) -> dict[tuple[str, str], str]:
    """``(entity_type, legacy_pk)`` → ledger vəziyyəti (migrated OLMAYANLAR)."""

    return {
        (str(entity_type), str(legacy_pk)): str(state)
        for entity_type, legacy_pk, state in LegacyEntityMap.objects.filter(
            organization=organization, entity_type__in=("student", "worker")
        )
        .exclude(state=LegacyEntityMap.State.MIGRATED)
        .values_list("entity_type", "legacy_pk", "state")
    }


def _issue_codes(organization) -> dict[tuple[str, str], tuple[str, ...]]:
    index: dict[tuple[str, str], set[str]] = {}
    for entity_type, legacy_pk, rule_code in LegacyMigrationIssue.objects.filter(
        organization=organization, entity_type__in=("student", "worker")
    ).values_list("entity_type", "legacy_pk", "rule_code"):
        index.setdefault((str(entity_type), str(legacy_pk)), set()).add(str(rule_code))
    return {key: tuple(sorted(value)) for key, value in index.items()}


def plan_missing(organization, *, connection_factory, limit: int = 0) -> list[MissingAccount]:
    """Hesabı olmayan legacy sətirləri mənbədən adları ilə birlikdə çıxar."""

    blocked = _blocked_maps(organization)
    codes = _issue_codes(organization)
    user_model = django_apps.get_model("auth", "User")
    plan: list[MissingAccount] = []
    for entity_type, contract in _COHORTS:
        wanted = {legacy_pk for (kind, legacy_pk) in blocked if kind == entity_type}
        if not wanted:
            continue
        with open_audited_identity_stream(connection_factory=connection_factory, contract=contract) as stream:
            for row in stream:
                legacy_pk = row["id"]
                if str(legacy_pk) not in wanted:
                    continue
                username = f"myedu.{entity_type}.{legacy_pk}"
                first_name, _t = clean_text(row["first_name"], max_length=NAME_MAX_LENGTH)
                last_name, _t = clean_text(row["last_name"], max_length=NAME_MAX_LENGTH)
                patronymic, _t = clean_text(row["father_name"], max_length=PATRONYMIC_MAX_LENGTH)
                exists = user_model._default_manager.filter(username=username).exists()
                plan.append(
                    MissingAccount(
                        projected_row=row,
                        entity_type=entity_type,
                        legacy_pk=int(legacy_pk),
                        username=username,
                        first_name=first_name,
                        last_name=last_name,
                        patronymic=patronymic,
                        ledger_state=blocked[(entity_type, str(legacy_pk))],
                        rule_codes=codes.get((entity_type, str(legacy_pk)), ()),
                        action="already_present" if exists else "create",
                    )
                )
    plan.sort(key=lambda item: (item.entity_type, item.legacy_pk))
    return plan[:limit] if limit else plan


def resolve_student_user_pks(organization, items, *, known=None) -> dict[int, int]:
    """``legacy_pk`` → ``auth_user`` pk (bu icrada yaradılanlar + mövcudlar).

    R-9: təmir ikinci dəfə işləyəndə hesablar ARTIQ var, ona görə istifadəçi
    açarı username konvensiyasından (``myedu.student.<id>``) həll olunur —
    yalnız BU tenant-ın profili olan sətirlər qəbul edilir.
    """

    resolved = dict(known or {})
    wanted = {item.username: item.legacy_pk for item in items if item.legacy_pk not in resolved}
    if not wanted:
        return resolved
    profile_model = django_apps.get_model("accounts", "UserProfile")
    rows = (
        django_apps.get_model("auth", "User")
        ._default_manager.filter(username__in=sorted(wanted))
        .values_list("username", "pk")
    )
    candidates = {str(username): int(pk) for username, pk in rows}
    tenant_users = set(
        profile_model.objects.filter(organization=organization, user_id__in=sorted(candidates.values())).values_list(
            "user_id", flat=True
        )
    )
    for username, legacy_pk in wanted.items():
        user_pk = candidates.get(username)
        if user_pk is not None and user_pk in tenant_users:
            resolved[legacy_pk] = user_pk
    return resolved


def student_fin_occurrences(connection_factory) -> Counter:
    """R-9: BÜTÜN kohortun FİN histoqramı — dublikat FİN yazılmasın deyə.

    ``rehearsal_placement_phase._apply_fin`` məhz bu histoqramı gözləyir; qayda
    iki yerdə təkrarlanmır, sadəcə eyni funksiyaya lazım olan giriş qurulur.
    """

    counts: Counter = Counter()
    with open_audited_identity_stream(
        connection_factory=connection_factory, contract=STUDENT_IDENTITY_FIELDS
    ) as stream:
        for row in stream:
            fin = _legacy_fin(row["fincode"])
            if fin:
                counts[fin] += 1
    return counts


def role_for(organization, entity_type: str):
    name = "student" if entity_type == "student" else "teacher"
    role = (
        django_apps.get_model("organizations", "Role")
        .objects.filter(organization=organization, name=name, is_active=True)
        .first()
    )
    if role is None:
        raise RuntimeError(f"legacy_repair_role_unavailable:{name}")
    return role


def create_account(*, organization, actor, item: MissingAccount):
    """Staged → active: mövcud accounts qapılarından keçən yeganə yol."""

    from apps.accounts.public import activate_staged_account, stage_imported_account

    role = role_for(organization, item.entity_type)
    with transaction.atomic():
        staged = stage_imported_account(
            organization=organization,
            role=role,
            actor=actor,
            username=item.username,
            email=placeholder_email(item.entity_type, item.legacy_pk),
            student_identifier=f"myedu-student-{item.legacy_pk}" if item.entity_type == "student" else "",
        )
        user = staged.user
        updates = {}
        if item.first_name and not user.first_name:
            updates["first_name"] = item.first_name
        if item.last_name and not user.last_name:
            updates["last_name"] = item.last_name
        if updates:
            django_apps.get_model("auth", "User")._default_manager.filter(pk=user.pk).update(**updates)
        profile_model = django_apps.get_model("accounts", "UserProfile")
        if item.patronymic:
            profile_model.objects.filter(user_id=user.pk, organization=organization, patronymic="").update(
                patronymic=item.patronymic
            )
        profile_model.objects.filter(user_id=user.pk, organization=organization).update(email_verified=False)
        activate_staged_account(
            user=user,
            organization=organization,
            expected_role=role,
            actor=actor,
            email_authoritative=True,
            email_authority_evidence_digest=evidence_digest(
                organization_pk=organization.pk, user_pk=user.pk, legacy_pk=str(item.legacy_pk)
            ),
            email_authority_reason_code=EVIDENCE_REASON_CODE,
        )
    return user


def _offering_index(organization) -> dict[str, list]:
    """``uniqid`` (ledger legacy açarı) → müəllimsiz açılış pk-ları."""

    offering_model = django_apps.get_model("registrar", "CourseOffering")
    without_instructor = set(
        str(pk)
        for pk in offering_model.objects.filter(organization=organization, instructor__isnull=True).values_list(
            "id", flat=True
        )
    )
    index: dict[str, list] = {}
    for legacy_pk, target_pk in LegacyEntityMap.objects.filter(
        organization=organization,
        entity_type=COURSE_OFFERING_ENTITY_TYPE,
        state=LegacyEntityMap.State.MIGRATED,
    ).values_list("legacy_pk", "target_pk"):
        if str(target_pk) in without_instructor:
            index.setdefault(str(legacy_pk).split(":")[0], []).append(target_pk)
    return index


def reattach_journals(organization, *, connection_factory, teacher_users: dict[int, int]) -> int:
    """Mənbədəki ``journals.teacher_id`` uyğunluğuna görə müəllimsiz açılışı bağla."""

    if not teacher_users:
        return 0
    offering_model = django_apps.get_model("registrar", "CourseOffering")
    index = _offering_index(organization)
    attached = 0
    with open_audited_source_stream(connection_factory=connection_factory, contract=JOURNAL_FIELDS) as stream:
        for row in stream:
            teacher_id = row["teacher_id"]
            user_pk = teacher_users.get(int(teacher_id) if type(teacher_id) is int else -1)
            if user_pk is None:
                continue
            for target_pk in index.get(str(row["uniqid"]), ()):
                attached += offering_model.objects.filter(pk=target_pk, instructor__isnull=True).update(
                    instructor_id=user_pk
                )
    return attached


__all__ = [
    "AUDIT_REASON",
    "EVIDENCE_REASON_CODE",
    "MissingAccount",
    "TABLE_HEADERS",
    "create_account",
    "plan_missing",
    "reattach_journals",
    "role_for",
]
