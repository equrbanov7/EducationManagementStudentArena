"""Tutuşdurmanın PLANI — nə dəyişəcək, kim bloklanacaq, kim qorunur (yazmadan) (sahib 2026-10-11).

``build_plan`` heç nə yazmır: dry-run hesabatı və ``--apply`` eyni planı işlədir (ikisi ayrışa bilməz).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from apps.organizations.models import OrgUnit

from .matching import (
    CHAIR_UNIT_TYPES,
    MATCHED_STATUSES,
    STATUS_NOT_FOUND,
    STATUS_REVIEW,
    AccountIndex,
    match_chairs,
    match_row,
)
from .parsing import DEGREE_RANK, RATE_HOURLY, RATE_UNKNOWN, TITLE_RANK
from .protection import is_student, is_teaching, load_accounts, protection_reasons

#: Profil elmi adı → yük profilinin vəzifəsi (``workload.constants.TeacherPosition``).
TITLE_TO_POSITION = {
    "professor": "professor",
    "docent": "dosent",
    "senior_teacher": "bas_muellim",
    "teacher": "muellim",
    "assistant": "assistent",
}


@dataclass
class UserPlan:
    account: object
    rows: list = field(default_factory=list)
    statuses: set = field(default_factory=set)
    title: str | None = None
    degree: str | None = None
    profile_changes: dict = field(default_factory=dict)  # sahə → (köhnə, yeni)
    position: str | None = None
    staff_fraction: Decimal | None = None
    is_external: bool | None = None
    workload: dict | None = None  # sync_roster_profile(dry_run=True) nəticəsi
    flags: list = field(default_factory=list)
    rate_error: str = ""  # ştat payı «Sistem tənzimləmələri» həddindən kənardır — profilə yazılmır


@dataclass
class Plan:
    organization: object
    academic_year: str
    roster: object
    chair_map: dict
    matches: list
    users: dict  # user_id → UserPlan
    block: list  # [Account]
    protected: list  # [(Account, [səbəb])]
    already_blocked: list  # siyahıda olmayan, onsuz da bloklu müəllim hesabları
    candidate_ids: set
    new_accounts: list | None = None  # ``--create-missing``: «hesab yoxdur» sətirlərindən yaradılacaqlar


def aggregate_rate(rows):
    rates = [row.rate for row in rows if row.rate.kind != RATE_UNKNOWN]
    if not rates:
        return None, None
    if all(rate.kind == RATE_HOURLY for rate in rates):
        return Decimal("0"), True
    total = sum((rate.fraction or Decimal("0")) for rate in rates if rate.kind != RATE_HOURLY)
    return total, False


def checked_rate(rows):
    """(pay, kənar, xəta). Pay «Sistem tənzimləmələri»ndəki ştat həddindən (defolt 0,25–1,5) kənardırsa
    profilə YAZILMIR (``None``) və səbəb qaytarılır — əvvəlki səssiz «1,5-ə kəsmə» yoxdur (sahib 2026-10-14)."""
    from apps.workload.public import staff_rate_error

    fraction, is_external = aggregate_rate(rows)
    if fraction is None:
        return None, None, ""
    error = staff_rate_error(fraction)
    return (None, is_external, error) if error else (fraction, is_external, "")


def best_value(values, rank):
    present = [value for value in values if value]
    return max(present, key=lambda value: rank.get(value, 0)) if present else None


def _user_plan(user_plan: UserPlan, chair_ids_by_row) -> None:
    account = user_plan.account
    user_plan.title = best_value([row.title for row in user_plan.rows], TITLE_RANK)
    user_plan.degree = best_value([row.degree for row in user_plan.rows], DEGREE_RANK)
    if user_plan.title and user_plan.title != account.title:
        user_plan.profile_changes["academic_title"] = (account.title, user_plan.title)
    if user_plan.degree and user_plan.degree != account.degree:
        user_plan.profile_changes["academic_degree"] = (account.degree, user_plan.degree)
    user_plan.position = TITLE_TO_POSITION.get(user_plan.title or "")
    user_plan.staff_fraction, user_plan.is_external, user_plan.rate_error = checked_rate(user_plan.rows)
    if user_plan.rate_error:
        user_plan.flags.append("staff_rate_out_of_range")

    file_chairs = {chair_ids_by_row[row.row_no] for row in user_plan.rows if chair_ids_by_row.get(row.row_no)}
    if not account.chairs:
        user_plan.flags.append("no_chair")
    elif file_chairs and not (file_chairs & account.chairs):
        user_plan.flags.append("chair_mismatch")
    if not account.is_active or account.is_deleted:
        user_plan.flags.append("account_blocked")
    if not is_teaching(account):
        user_plan.flags.append("no_teacher_role")
    if len(user_plan.rows) > 1:
        user_plan.flags.append("multi_row")


def _guard_partial_names(matches, accounts, candidate_ids) -> None:
    """Adı natamam hesab (soyad və ya ad boş) tapılmamış sətrin adına/soyadına uyğundursa — bloklanmır.

    Belə hesab tam adla tutuşdurula bilmir; siyahıdakı müəllimin özü ola bilər. Sətir ``review`` olur.
    """
    partial = [account for account in accounts if not (account.last_key and account.first_key)]
    if not partial:
        return
    for match in matches:
        if match.status != STATUS_NOT_FOUND:
            continue
        keys = {match.row.name.last_key, match.row.name.first_key}
        hits = [account for account in partial if (account.last_key or account.first_key) in keys]
        if hits:
            match.status = STATUS_REVIEW
            match.candidates = hits
            candidate_ids.update(account.user_id for account in hits)


def build_plan(organization, roster, *, academic_year: str, chair_overrides=None, protect_ids=(), workload=True):
    """Faylı (``RosterFile``) təşkilatın hesabları ilə tutuşdurur — YAZMIR."""
    from django.contrib.auth import get_user_model

    accounts = load_accounts(organization)
    index = AccountIndex(accounts, is_student=is_student)
    units = list(
        OrgUnit.objects.filter(organization=organization, is_active=True, unit_type__in=CHAIR_UNIT_TYPES)
        .order_by("name")
        .values_list("id", "name")
    )
    chair_map = match_chairs(roster.chairs, units, chair_overrides)

    matches, users, candidate_ids, chair_ids_by_row = [], {}, set(), {}
    for row in roster.rows:
        unit = chair_map.get(row.chair, {}).get("unit")
        chair_ids_by_row[row.row_no] = unit[0] if unit else None
        result = match_row(row, index, unit[0] if unit else None)
        matches.append(result)
        candidate_ids.update(account.user_id for account in result.candidates)
        if result.account is not None:
            candidate_ids.add(result.account.user_id)
        if result.status in MATCHED_STATUSES:
            bucket = users.setdefault(result.account.user_id, UserPlan(account=result.account))
            bucket.rows.append(row)
            bucket.statuses.add(result.status)
            bucket.flags.extend(flag for flag in result.flags if flag not in bucket.flags)
    _guard_partial_names(matches, accounts, candidate_ids)
    for user_plan in users.values():
        _user_plan(user_plan, chair_ids_by_row)

    if workload and users:
        from apps.workload.public import sync_roster_profile

        teachers = get_user_model().objects.in_bulk(list(users))
        for user_id, user_plan in users.items():
            if user_plan.position is None and user_plan.staff_fraction is None:
                continue
            user_plan.workload = sync_roster_profile(
                organization=organization,
                teacher=teachers[user_id],
                academic_year=academic_year,
                position=user_plan.position,
                staff_fraction=user_plan.staff_fraction,
                is_external=user_plan.is_external,
                dry_run=True,
            )

    owner_ids = {organization.owner_id} if organization.owner_id else set()
    block, protected, already_blocked = [], [], []
    for account in accounts:
        if not is_teaching(account) or account.user_id in candidate_ids:
            continue
        reasons = protection_reasons(account, owner_ids=owner_ids, explicit_ids=set(protect_ids))
        if reasons:
            protected.append((account, reasons))
        elif not account.is_active or account.is_deleted:
            already_blocked.append(account)
        else:
            block.append(account)
    block.sort(key=lambda account: (account.last_key, account.first_key, account.user_id))
    return Plan(
        organization=organization,
        academic_year=academic_year,
        roster=roster,
        chair_map=chair_map,
        matches=matches,
        users=users,
        block=block,
        protected=protected,
        already_blocked=already_blocked,
        candidate_ids=candidate_ids,
    )


__all__ = ["TITLE_TO_POSITION", "Plan", "UserPlan", "aggregate_rate", "best_value", "build_plan", "checked_rate"]
