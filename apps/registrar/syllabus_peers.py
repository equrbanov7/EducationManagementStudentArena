"""Jurnal bannerinin «Bu fənn üzrə mövcud sillabuslar» siyahısı + «eyni sillabusu bu jurnala tətbiq et» təklifi.

Sahib 2026-11-08: «bir neçə müəllimin jurnalına baxa bilən (kafedra müdiri, baxış rolları) jurnalda
«Sillabus yarat» / «Qaralamanı tamamla» görəndə bütün sillabuslar görünsün və sillabusa keçmək olsun; müəllim
o sillabusu başqa qrup üçün artıq yazıbsa əvvəlcə dəyişmədən tətbiq etmək təsdiqi soruşulsun — bu təklif burada da
çıxsın; sillabusun hansı qrup üçün və kim tərəfindən yaradıldığı görünsün».

Burada YENİ qayda yoxdur — hamısı mövcud köməkçilərdir:

* SİYAHI — ``services.sibling_queryset`` (siyahı ekranının «Mövcud sillabusdan istifadə et» dialoqu ilə eyni
  oxu qapısı: baxanın sillabus əhatəsi, müəllimdə cari tədris ili); qrup adları dosyenin öz açılışı + qüvvədə olan
  paylaşımlar (``services.sharing.effective_shares``);
* TƏKLİF — ``services.sharing.share_code`` (yalnız öz sillabusu, eyni fənn + semestr, hədəf jurnal boşdur, aktor
  jurnalın müəllimidir).  Yazı mövcud ``accounts:syllabus_reuse_action`` (``action=share``) ucundan keçir, burada
  yazı YOXDUR.

Jurnal səhifəsinin sorğu büdcəsi dəyişmir: məlumat banner göstəriləndə JS ilə ayrıca GET-lə gəlir.
Giriş qapısı «Sillabusa bax» panelinin qapısıdır (``syllabus_views._viewer_mode``) — tələbəyə və kənar
istifadəçiyə 404.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.urls import reverse
from django.utils.translation import pgettext_lazy
from django.views.decorators.http import require_GET

from apps.syllabus import public as syllabus_services
from apps.syllabus.public import SyllabusStatus, services

from . import journal_access
from .syllabus_notice import profile_link

_CTX = "registrar.syllabus"

#: Bir jurnalda ən çox bu qədər sətir — fənnin bir semestrdəki qrupları üçün kifayətdir.
MAX_ROWS = 30

_NO_GROUP = pgettext_lazy(_CTX, "Semestr dosyesi")
_NO_AUTHOR = pgettext_lazy(_CTX, "Müəllif məlum deyil")
_APPROVED_IN_FORCE = pgettext_lazy(_CTX, "təsdiqlənmiş versiya qüvvədədir")
_QUESTION = pgettext_lazy(
    _CTX,
    "Bu fənn üçün %(group)s qrupuna hazırladığınız sillabus var — dəyişmədən bu jurnala da tətbiq edilsin?",
)


def _person(user) -> str:
    if user is None:
        return ""
    full = (user.get_full_name() or "").strip() if hasattr(user, "get_full_name") else ""
    return full or getattr(user, "username", "") or ""


def _author(row) -> str:
    """Dosyenin müəllifi; köçürmədə müəllif boşdursa açılışın müəllimi."""
    name = _person(row.author) if row.author_id else ""
    if not name and row.offering_id and row.offering.instructor_id:
        name = _person(row.offering.instructor)
    return name or str(_NO_AUTHOR)


def _shared_groups(syllabus_ids) -> dict:
    """``{syllabus_id: [qrup adı, …]}`` — sillabusu öz yerində istifadə edən digər jurnallar (TƏK sorğu)."""
    if not syllabus_ids:
        return {}
    groups: dict = {}
    for syllabus_id, name in (
        services.sharing.effective_shares()
        .filter(syllabus_id__in=list(syllabus_ids))
        .order_by("offering__group__name")
        .values_list("syllabus_id", "offering__group__name")
    ):
        groups.setdefault(syllabus_id, []).append(name or str(_NO_GROUP))
    return groups


def _status(row) -> tuple[str, str]:
    version = row.current_version if row.current_version_id else None
    key = version.status if version is not None else SyllabusStatus.DRAFT.value
    return key, str(SyllabusStatus(key).label)


def _row(row, *, shared: list, offering) -> dict:
    own_group = row.offering.group.name if row.offering_id and row.offering.group_id else str(_NO_GROUP)
    groups = [own_group, *shared]
    key, label = _status(row)
    approved = bool(row.approved_version_id) and key != SyllabusStatus.APPROVED.value
    return {
        "id": str(row.pk),
        "groups": groups,
        "group_text": ", ".join(groups),
        "author": _author(row),
        # Jurnalın müəllimi bu sillabusun müəllifidirmi (baxan rəhbər üçün «bu müəllimin» qeydi).
        "by_instructor": bool(
            offering.instructor_id
            and offering.instructor_id in {row.author_id, row.offering.instructor_id if row.offering_id else None}
        ),
        "status_key": key,
        "status_label": label,
        "approved_note": str(_APPROVED_IN_FORCE) if approved else "",
        "url": profile_link("syllabus-editor", syllabus=row.pk),
    }


def _reuse_sources(rows, *, actor, offering, notice_state) -> list:
    """Jurnalın müəllimi üçün «dəyişmədən tətbiq et» mənbələri — ``share_code`` qapısı (yoxsa boş)."""
    if notice_state != syllabus_services.STATE_MISSING or actor.user_id != offering.instructor_id:
        return []
    own = [(row, data) for row, data in rows if getattr(row, "_own", 0)]
    if not own:
        return []
    sharing = services.sharing
    state_code = sharing.target_code(offering)  # hədəfin vəziyyəti BİR dəfə (mənbə başına sorğu yox)
    if state_code:
        return []
    return [
        {
            "id": data["id"],
            "group": data["group_text"],
            "author": data["author"],
            "status_label": data["status_label"],
            "question": str(_QUESTION) % {"group": data["group_text"]},
        }
        for row, data in own
        if not sharing.share_code(row, actor=actor, offering=offering, state_code=state_code)
    ]


def build_peers(request, offering) -> dict:
    """``{"rows": […], "reuse": [...], "can_create": bool, "state": str}`` — bax modul docstring-i."""
    syllabus = syllabus_services.syllabus_for_offering_obj(offering)
    state = syllabus_services.offering_syllabus_state(syllabus)["state"]
    actor = syllabus_services.resolve_actor(request.user, offering.organization, request=request)
    queryset = services.sibling_queryset(
        organization=offering.organization,
        actor=actor,
        subject_id=offering.subject_id,
        period_id=offering.period_id,
        exclude_syllabus_id=getattr(syllabus, "pk", None),
        exclude_offering_id=offering.pk,
    ).select_related("offering__instructor")
    found = list(queryset[:MAX_ROWS])
    shared = _shared_groups([row.pk for row in found])
    rows = [(row, _row(row, shared=shared.get(row.pk, []), offering=offering)) for row in found]
    return {
        "state": state,
        "rows": [data for _row_obj, data in rows],
        "reuse": _reuse_sources(rows, actor=actor, offering=offering, notice_state=state),
        # Sillabusu yalnız jurnalın müəllimi yaradır (``accounts`` «create» əməli ilə eyni qayda).
        "can_create": bool(offering.instructor_id) and offering.instructor_id == request.user.pk,
        "create_url": profile_link("syllabus-list"),
        "action_url": reverse("accounts:syllabus_reuse_action"),
        "offering": str(offering.pk),
    }


@login_required
@require_GET
def journal_syllabus_peers(request, offering_id):
    """JSON: jurnal bannerinin sillabus siyahısı + təklif. Jurnalı aça bilməyənə (tələbə daxil) 404."""
    from .syllabus_views import MODE_STUDENT, _viewer_mode

    offering = journal_access.offering_or_404(request, offering_id)
    mode = _viewer_mode(request, offering)
    if mode is None or mode == MODE_STUDENT:
        raise Http404
    return JsonResponse({"ok": True, **build_peers(request, offering)})


__all__ = ["MAX_ROWS", "build_peers", "journal_syllabus_peers"]
