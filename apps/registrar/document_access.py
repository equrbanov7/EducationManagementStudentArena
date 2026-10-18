"""Kim tələbəyə RƏSMİ sənəd (transkript, arayış) verə bilər — FAIL-CLOSED (sahib 2026-10-19).

İki yol, ikisi də işləyir:

* **köhnə yol** — təşkilat üzrə ``course.edit`` (rektor, prorektor, RİM: ``catalog_console.can_manage``) →
  istənilən tələbə;
* **yeni açar** ``transcript.issue`` (kataloq: ``organizations/permissions_transcript.py``):
  ORGANIZATION rolu (Tədris şöbəsinin müdiri, Tələbə xidmətləri, RİM rəhbəri) → istənilən tələbə;
  UNIT rolu (dekan, dekan müavini) → yalnız qrupu öz alt-ağacında olan tələbə. Qrupsuz qeyd vahid
  aktoruna görünmür (fail-closed).

Əhatədən kənar qeyd **404** alır (mövcudluq sızmır). Buraxılış möhür sətri YAZDIĞI üçün «başqasının
adından» (view-as) rejimində bağlıdır (:func:`blocked_by_view_as`) — görünüş 403 qaytarır, düymələr gizlənir.
"""

from __future__ import annotations

from apps.organizations.public import EMPTY_SCOPE, ORG_WIDE_SCOPE, get_permission_scope
from apps.registrar import catalog_console
from apps.registrar.models import StudentAcademicRecord

PERM_TRANSCRIPT_ISSUE = "transcript.issue"


def issue_scope(user, organization, request=None):
    """Aktorun sənəd verə bildiyi struktur əhatəsi (``UnitScope``)."""
    if organization is None or user is None or not getattr(user, "is_authenticated", False):
        return EMPTY_SCOPE
    if catalog_console.can_manage(user, organization):
        return ORG_WIDE_SCOPE
    return get_permission_scope(user, organization, PERM_TRANSCRIPT_ISSUE, request=request)


def can_issue(user, organization, request=None) -> bool:
    """Aktor ən azı bir tələbəyə sənəd verə bilərmi (düymə / bölmə görünüşü üçün)."""
    return issue_scope(user, organization, request=request).has_structure_access


def blocked_by_view_as(request) -> bool:
    """Möhürlü sənəd buraxılışı yazıdır — view-as rejimində qadağandır."""
    return bool(getattr(request, "is_view_as", False))


def issuable_records(user, organization, request=None):
    """Aktorun sənəd verə bildiyi akademik qeydlər (təşkilat süzgəci + struktur əhatəsi)."""
    if organization is None:
        return StudentAcademicRecord.objects.none()
    scope = issue_scope(user, organization, request=request)
    if not scope.has_structure_access:
        return StudentAcademicRecord.objects.none()
    records = StudentAcademicRecord.objects.filter(organization=organization)
    if scope.is_org_wide:
        return records
    return records.filter(scope.unit_subtree_q(path_field="group__path", id_field="group_id"))


def can_issue_for_record(user, organization, record, request=None) -> bool:
    if record is None or getattr(record, "organization_id", None) != getattr(organization, "pk", None):
        return False
    return issuable_records(user, organization, request=request).filter(pk=record.pk).exists()


__all__ = [
    "PERM_TRANSCRIPT_ISSUE",
    "blocked_by_view_as",
    "can_issue",
    "can_issue_for_record",
    "issuable_records",
    "issue_scope",
]
