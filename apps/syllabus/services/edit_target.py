"""«Sillabusu redaktə et» — müəllimin redaktəyə HARADAN keçəcəyi (sahib 2026-11-15).

Jurnalın «Sillabusa bax» paneli və redaktorun kilid banneri bu funksiyadan soruşur: «bu aktor bu dosyeni
redaktə edə bilərmi, edə bilərsə hansı yolla?». Cavab servislərin özünün yazı qapılarının güzgüsüdür:

* bölmə yazısı (``drafts.save_section``) — ``syllabus.edit`` açarı + ``is_editor`` (dosyenin müəllifi VƏ YA
  bağlı açılışın CARİ müəllimi — təhvildən sonra yeni müəllim, bölünmüş jurnalın pay sahibi, yük bölgüsü);
* yeni versiya (``drafts.create_next_version``) — eyni açar; bağlı (``reused_from``) dosyedə qadağandır;
* yaratma (``syllabus_action`` → ``create``) — jurnalın cari müəllimi, açılışın ÖZ dosyesi yoxdursa.

Rejimlər:

``open``         açıq versiya (qaralama / düzəliş / baxışda) və ya avtomatik təsdiq rejimində təsdiqlənmiş versiya
                 — redaktor birbaşa HƏMİN versiyada açılır; bağlı dosye də burada (redaktorda «Ayır» var);
``new_version``  qüvvədə olan nüsxə təsdiqlənib / rədd edilib / arxivdədir — əvvəl yeni QARALAMA versiya açılır
                 (``syllabus_action`` → ``new_version``), təsdiqlənmiş versiyanın üstündən YAZILMIR;
``create``       jurnal BAŞQA qrupun / semestrin ortaq dosyesini göstərir (onu bu müəllim redaktə etmir — bütün
                 qruplar üçün ortaqdır), açılışın öz sillabusu isə yoxdur → «Öz sillabusunu yarat».
"""

from __future__ import annotations

from django.apps import apps
from django.db.models import Q

from ..constants import PERM_EDIT
from ..editing import approved_edits_enabled
from ..models import Syllabus
from .drafts import open_version_for
from .offerings import approved_version_for
from .scoping import is_editor, is_journal_teacher

EDIT_MODE_OPEN = "open"
EDIT_MODE_NEW_VERSION = "new_version"
EDIT_MODE_CREATE = "create"


def can_edit_content(actor, syllabus) -> bool:
    """Bölmə yazısının qapısı (``save_section``) — redaktorun «normal» rejimi və düymələr bununla açılır."""
    return bool(syllabus is not None and actor.has(PERM_EDIT) and is_editor(actor, syllabus))


def can_create_for(actor, offering) -> bool:
    """«Sillabus yarat» qapısı: jurnalın cari müəllimi + açar + aktiv açılışın ÖZ dosyesi hələ yoxdur."""
    if offering is None or not getattr(offering, "is_active", True) or not actor.has(PERM_EDIT):
        return False
    if not is_journal_teacher(actor, offering):
        return False
    return not Syllabus.objects.filter(organization_id=offering.organization_id, offering_id=offering.pk).exists()


def _open_or_new(syllabus) -> dict | None:
    open_version = open_version_for(syllabus)
    if open_version is not None:
        return {"mode": EDIT_MODE_OPEN, "version": open_version.pk}
    approved = approved_version_for(syllabus, metadata_only=True)
    if approved is not None and approved_edits_enabled(approved):
        return {"mode": EDIT_MODE_OPEN, "version": approved.pk}
    if syllabus.reused_from_id:
        # Bağlı dosyenin məzmunu mənbədən gəlir — yeni versiya yox, redaktorun «Ayır» banneri.
        target = approved or syllabus.current_version
        return {"mode": EDIT_MODE_OPEN, "version": target.pk} if target is not None else None
    if not syllabus.versions.exists():
        return None
    return {"mode": EDIT_MODE_NEW_VERSION, "version": None}


def edit_target(actor, syllabus, offering=None) -> dict | None:
    """``{"mode", "version", "offering"}`` və ya ``None`` (redaktə hüququ / versiya yoxdur).

    ``offering`` — panelin açıldığı jurnal: dosyeni redaktə edə bilməyən cari müəllimə ``create`` təklif olunur.
    """
    if can_edit_content(actor, syllabus):
        target = _open_or_new(syllabus)
        return {**target, "offering": None} if target is not None else None
    if can_create_for(actor, offering):
        return {"mode": EDIT_MODE_CREATE, "version": None, "offering": offering.pk}
    return None


def own_offering_without_syllabus(actor, syllabus):
    """Redaktorun oxu-rejimi: aktorun eyni fənn (+ semestr) üzrə sillabussuz jurnalı (müəllim / pay sahibi) — və ya None."""
    if syllabus is None or actor.user_id is None or not actor.has(PERM_EDIT):
        return None
    offering_model = apps.get_model("registrar", "CourseOffering")
    shares = apps.get_model("registrar", "JournalShare").objects.filter(
        organization_id=syllabus.organization_id, teacher_id=actor.user_id, is_active=True
    )
    queryset = offering_model.objects.filter(
        Q(instructor_id=actor.user_id) | Q(pk__in=shares.values("offering_id")),
        organization_id=syllabus.organization_id,
        subject_id=syllabus.subject_id,
        is_active=True,
    ).exclude(
        # ⚠️ NULL-suz alt sorğu: «NOT IN (…, NULL)» heç bir sətir qaytarmırdı (semestr / baza dosyelərinin offering-i boşdur).
        pk__in=Syllabus.objects.filter(organization_id=syllabus.organization_id, offering__isnull=False).values(
            "offering_id"
        )
    )
    if syllabus.period_id:
        queryset = queryset.filter(period_id=syllabus.period_id)
    return queryset.order_by("pk").first()


__all__ = [
    "EDIT_MODE_CREATE",
    "EDIT_MODE_NEW_VERSION",
    "EDIT_MODE_OPEN",
    "can_create_for",
    "can_edit_content",
    "edit_target",
    "own_offering_without_syllabus",
]
