"""``restore_intensive_results_20261112 --create-missing-offerings`` — köhnə intensiv jurnalının ARXİV açılışı (MR-000288).

Səbəb: köhnə sistemin intensiv / təkrar jurnalı (``fake = 1``) heç vaxt köçməyib və heç bir bacı tələbəsi də yeni
sistemdə olmayıbsa, həmin dövrdə fənnin uyğun açılışı yoxdur (``skip_offering_no_sibling`` /
``skip_offering_unresolved``) — tələbənin keçdiyi fənn kabinetdə «F» qalır (məs. «Ardıcıl tərcümə və qeydgötürmə
texnikası», 2025/2026 Yaz). Bu rejimdə belə sətir üçün açılış YARADILIR:

* bir köhnə jurnal ailəsi (``journals``, sıralanmış ilk uniqid) = bir açılış; ``format_note`` =
  ``«<NOTE> · <uniqid>»`` — təkrar qaçış eyni açılışı tapır (yenisini yaratmır);
* ``course_format = intensive``, qrupsuz, ``starts_on`` / ``ends_on`` = dövrün tarixləri; müəllim — köhnə jurnalın
  müəllimi (plan sətrinin ``teacher`` legacy id-si → cutover ledger-i ``worker``), tapılmasa boş;
* yalnız BİTMİŞ dövrdə (``end_date`` keçib, ``is_current`` deyil) — cari jurnal siyahılarına düşmür; sxem dərhal
  BAĞLI (``approved`` + ``is_published``) — RİM-in semestr sonu bağlaması kimi;
* komponentlər köhnə köçürmə ilə eyni: «Davamiyyət və sərbəst iş (arxiv)» (generic, 50) + ailənin plan sətirlərində
  olan kollokviumlar («Kollokvium N», 10);
* ``ambiguous`` sətirlərə toxunulmur (mövcud açılışlardan biri seçilməlidir — RİM).

Yaradılan açılışlar audit ``changes.offerings_created``-dədir; ``undo`` onları (yazılışı qalmayıbsa) silir.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.utils import timezone

NOTE = "Köhnə sistemin intensiv jurnalı (arxiv, MR-000288)"
CREATABLE = ("offering_no_sibling", "offering_unresolved")
ARCHIVE_MAX = 50
KOLLOKVIUM_MAX = 10


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def family_key(item) -> str:
    return sorted(str(uq) for uq in item["journals"])[0]


def note_for(key: str) -> str:
    return f"{NOTE} · {key}"[:255]


def family_kollokvium(items) -> dict:
    """Ailə → plan sətirlərində rast gəlinən kollokvium nömrələri (``k1`` → 1)."""
    out: dict = {}
    for item in items:
        digits = {int(key[1:]) for key in (item.get("k") or {}) if key[1:].isdigit()}
        out.setdefault(family_key(item), set()).update(digits)
    return out


def period_is_closed_past(period) -> bool:
    return bool(period.end_date and period.end_date < timezone.localdate() and not period.is_current)


class ArchiveOfferings:
    """Ailə üzrə arxiv açılışını tap / yarat (çağıranın savepoint-ində)."""

    def __init__(self, *, organization, items, teachers: dict):
        self.organization = organization
        self.kollokvium = family_kollokvium(items)
        self.teachers = teachers  # legacy worker id → aktiv istifadəçi pk
        self.cache: dict = {}

    def find(self, item, period, subject):
        key = (family_key(item), period.pk, subject.pk)
        if key in self.cache:
            return self.cache[key]
        found = (
            _model("CourseOffering")
            .objects.filter(
                organization=self.organization,
                period=period,
                subject=subject,
                course_format="intensive",
                format_note=note_for(key[0]),
                is_active=True,
            )
            .first()
        )
        if found is not None:
            self.cache[key] = found
        return found

    def create(self, item, period, subject, counts):
        """Yeni bağlı arxiv açılışı (``RuntimeError`` — savepoint geri alınır)."""
        if not period_is_closed_past(period):
            raise RuntimeError("offering_period_not_past")
        Offering, Scheme, Component = (
            _model("CourseOffering"),
            _model("AssessmentScheme"),
            _model("AssessmentComponent"),
        )
        key = family_key(item)
        teacher = self.teachers.get(str(item.get("teacher") or ""))
        if teacher is None:
            counts["created_offering_without_teacher"] += 1
        offering = Offering.objects.create(
            organization=self.organization,
            subject=subject,
            period=period,
            group=None,
            instructor_id=teacher,
            course_format="intensive",
            starts_on=period.start_date,
            ends_on=period.end_date,
            format_note=note_for(key),
        )
        Scheme.objects.create(
            organization=self.organization, offering=offering, is_published=True, approval_status="approved"
        )
        Component.objects.create(
            organization=self.organization,
            offering=offering,
            name="Davamiyyət və sərbəst iş (arxiv)",
            kind="generic",
            max_score=ARCHIVE_MAX,
            order=0,
        )
        for number in sorted(self.kollokvium.get(key) or ()):
            Component.objects.create(
                organization=self.organization,
                offering=offering,
                name=f"Kollokvium {number}",
                kind="kollokvium",
                max_score=KOLLOKVIUM_MAX,
                order=number,
            )
        self.cache[(key, period.pk, subject.pk)] = offering
        return offering

    def forget(self, offering) -> None:
        """Savepoint geri alındı — yaradılmış açılış artıq yoxdur."""
        self.cache = {key: row for key, row in self.cache.items() if row.pk != offering.pk}


def resolve_teachers(ledger, organization, items) -> dict:
    """Plan sətirlərinin ``teacher`` legacy id-ləri → qiymət yazmaq səlahiyyətli aktiv müəllim pk (cutover ledger-i).

    Səlahiyyəti olmayan (məs. işdən çıxmış) müəllim — açılış müəllimsiz yaradılır (DB qoruyucusu onu qəbul etmir)."""
    from django.contrib.auth import get_user_model

    from .integrity import is_authorized_instructor

    wanted = {str(item.get("teacher")) for item in items if str(item.get("teacher") or "").isdigit()}
    if not wanted:
        return {}
    mapped = {key: int(value) for key, value in ledger._rows("worker", wanted).items() if str(value).isdigit()}
    users = get_user_model().objects.filter(pk__in=set(mapped.values()), is_active=True).in_bulk()
    allowed = {pk for pk, user in users.items() if is_authorized_instructor(organization=organization, instructor=user)}
    return {str(key): value for key, value in mapped.items() if value in allowed}


def drop_created(organization, offering_ids, counts) -> None:
    """``undo``: yaradılmış arxiv açılışı — yazılışı qalmayıbsa silinir."""
    from core.rls import journal_unlock

    Offering, Enrollment = _model("CourseOffering"), _model("Enrollment")
    for pk in offering_ids:
        offering = Offering.objects.filter(organization=organization, pk=pk, format_note__startswith=NOTE).first()
        if offering is None:
            counts["undo_offering_missing"] += 1
            continue
        if Enrollment.objects.filter(offering=offering).exists():
            counts["undo_offering_kept_in_use"] += 1
            continue
        with journal_unlock(local=True):
            offering.delete()
        counts["undo_offering_deleted"] += 1


__all__ = ["ArchiveOfferings", "CREATABLE", "NOTE", "drop_created", "resolve_teachers"]
