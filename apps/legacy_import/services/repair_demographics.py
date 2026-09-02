"""P1 təmiri: doğum tarixi, cins və profil qrup nömrəsi.

Qüsur (2026-09-02 auditi).  Klonda ``UserProfile.birth_date`` 8 440/8 440 NULL,
``gender`` 8 440/8 440 ``unspecified``, ``student_group_number`` isə 8 440/8 440
boşdur — halbuki mənbədə 2 168 tələbə + 84 işçi doğum tarixi, 1 639 sətir isə
``sex`` daşıyır və qrup hədəfdə ``StudentAcademicRecord.group``-dadır.

İki fərqli kök səbəb, iki fərqli yol
------------------------------------
1. **Doğum tarixi / cins.**  Kod QÜSURLU DEYİL: ``legacy_demographics`` modulu
   və ``student_placement``-dəki çağırışı 2026-08-30-da əlavə olunub, klondakı
   run isə 2026-08-27-dədir — yəni bu nüsxə sadəcə KÖHNƏ koda görə boşdur.
   Növbəti tam repetisiya onu özü doldurur.  Artıq köçürülmüş hədəf üçün isə
   dəyər YALNIZ mənbədən oxunur (``--from-source``): uydurulmur, təxmin edilmir
   və mövcud dəyərin üzərinə YAZILMIR (``write_demographics`` §4.5 müqaviləsi).
2. **``student_group_number``.**  Bu, tamamilə HƏDƏF daxilində həll olunur:
   profil paneli bu sahəni oxuyur, əsl qrup isə ``SAR.group.name``-dədir.
   Mənbə bağlantısı tələb OLUNMUR.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.apps import apps as django_apps
from django.utils import timezone

from apps.legacy_import.models import LegacyEntityMap

from .field_contracts import STUDENT_IDENTITY_FIELDS, WORKER_IDENTITY_FIELDS
from .legacy_demographics import STATE_WRITTEN, demographics_from_row, write_demographics
from .rehearsal_authorizer import USER_MODEL_LABEL
from .source_extraction import open_audited_identity_stream

AUDIT_REASON = "legacy_repair:demographics"
_COHORTS = (("student", STUDENT_IDENTITY_FIELDS), ("worker", WORKER_IDENTITY_FIELDS))

TABLE_HEADERS = ("sahə", "hədəfdə dolu (əvvəl)", "namizəd", "yazıldı")


@dataclass(frozen=True)
class _Context:
    """``write_demographics`` yalnız ``organization``-a baxır."""

    organization: object


def entity_user_map(organization, entity_type: str) -> dict[str, int]:
    """``legacy_pk`` → ``auth_user`` pk (yalnız bu tenant, yalnız migrated)."""

    return {
        str(legacy_pk): int(target_pk)
        for legacy_pk, target_pk in LegacyEntityMap.objects.filter(
            organization=organization,
            entity_type=entity_type,
            state=LegacyEntityMap.State.MIGRATED,
            target_model_label=USER_MODEL_LABEL,
        ).values_list("legacy_pk", "target_pk")
    }


def group_number_candidates(organization, *, limit: int = 0):
    """``student_group_number`` boş olan profillər üçün (user_pk, qrup adı)."""

    record_model = django_apps.get_model("registrar", "StudentAcademicRecord")
    profile_model = django_apps.get_model("accounts", "UserProfile")
    blank = set(
        profile_model.objects.filter(organization=organization, student_group_number="").values_list(
            "user_id", flat=True
        )
    )
    rows = (
        record_model.objects.filter(organization=organization, student_id__in=sorted(blank))
        .exclude(group__isnull=True)
        .order_by("student_id")
        .values_list("student_id", "group__name")
    )
    seen: dict[int, str] = {}
    for student_id, group_name in rows:
        name = str(group_name or "").strip()
        if name and int(student_id) not in seen:
            seen[int(student_id)] = name[:50]
    items = sorted(seen.items())
    return items[:limit] if limit else items


def write_group_numbers(organization, candidates) -> int:
    """Yalnız BOŞ sahəni doldur — mövcud dəyər heç vaxt üzərinə yazılmır."""

    profile_model = django_apps.get_model("accounts", "UserProfile")
    written = 0
    for user_pk, group_name in candidates:
        written += profile_model.objects.filter(
            organization=organization, user_id=user_pk, student_group_number=""
        ).update(student_group_number=group_name, updated_at=timezone.now())
    return written


def apply_source_demographics(organization, *, connection_factory, chunk_size: int = 1000, limit: int = 0):
    """Mənbədən ``sex``/``birthday`` oxu və YALNIZ boş hədəf sahələrini doldur."""

    context = _Context(organization=organization)
    written = 0
    seen = 0
    for entity_type, contract in _COHORTS:
        users = entity_user_map(organization, entity_type)
        if not users:
            continue
        with open_audited_identity_stream(
            connection_factory=connection_factory, contract=contract, chunk_size=chunk_size
        ) as stream:
            for projected_row in stream:
                user_pk = users.get(str(projected_row["id"]))
                if user_pk is None:
                    continue
                demographics = demographics_from_row(projected_row)
                if demographics.is_blank:
                    continue
                seen += 1
                if limit and seen > limit:
                    break
                if write_demographics(context, user_pk=str(user_pk), demographics=demographics) == STATE_WRITTEN:
                    written += 1
    return seen, written


def target_coverage(organization) -> dict[str, int]:
    """Hədəfin hazırkı doluluğu — dry-run hesabatının «əvvəl» sütunu."""

    profile_model = django_apps.get_model("accounts", "UserProfile")
    base = profile_model.objects.filter(organization=organization)
    return {
        "profil": base.count(),
        "birth_date": base.exclude(birth_date__isnull=True).count(),
        "gender": base.exclude(gender="unspecified").count(),
        "student_group_number": base.exclude(student_group_number="").count(),
    }


__all__ = [
    "AUDIT_REASON",
    "TABLE_HEADERS",
    "apply_source_demographics",
    "entity_user_map",
    "group_number_candidates",
    "target_coverage",
    "write_group_numbers",
]
