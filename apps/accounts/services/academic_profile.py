"""Akademik fəaliyyət qeydləri (AcademicProfileItem) üçün servis qatı.

Profil «Akademik fəaliyyət» bölməsinin CRUD məntiqi: sahiblik, rol-əsaslı növ
icazəsi, sahə validasiyası və say limitləri BURADA yoxlanılır — view qatı
yalnız HTTP giriş nöqtəsidir (SoC). Bax: docs/frontend/AJAX_SAFE_JS_PATTERN.md
(fetchJSON istehlakçısı: accounts/js/profile/academic_items.js).
"""

from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext, pgettext_lazy

from apps.accounts.models import AcademicProfileItem
from core.roles import ProfileRole

from . import academic_attachments as attachments

#: Hər növ üzrə istifadəçi başına maksimum qeyd — UI-nin oxunaqlı qalması və
#: sadə anti-abuse tavanı üçün.
MAX_ITEMS_PER_KIND = 30

TITLE_MAX_LENGTH = 200
DETAIL_MAX_LENGTH = 255
LINK_MAX_LENGTH = 300
YEAR_MIN = 1950

_Kind = AcademicProfileItem.Kind

#: Yalnız tədris heyəti üçün mənalı növlər: «Tədris etdiyi fənn», «Kitab /
#: dərslik» (dərslik müəllifliyi) və «Patent». Qalanları bütün rollara açıqdır —
#: tələbə də təhsil, təcrübə (staj), məqalə, konfrans, layihə/qrant, sertifikat
#: və mükafat (olimpiada və s.) əlavə edə bilir. 2026-10-01: 6 yeni növ.
TEACHING_ONLY_KINDS = {_Kind.SUBJECT, _Kind.BOOK, _Kind.PATENT}

#: «Qeyd tapılmadı.» — view qatı 404 statusunu bu mesajla tanıyır.
NOT_FOUND_ERROR = pgettext_lazy("accounts.academic_items.error", "Qeyd tapılmadı.")

#: Növ üzrə Font Awesome ikonları (idarəetmə + görünüş kartları).
KIND_ICONS = {
    _Kind.SUBJECT: "fa-book-open",
    _Kind.EDUCATION: "fa-graduation-cap",
    _Kind.EXPERIENCE: "fa-briefcase",
    _Kind.PUBLICATION: "fa-file-lines",
    _Kind.BOOK: "fa-book",
    _Kind.CONFERENCE: "fa-people-group",
    _Kind.PROJECT: "fa-flask",
    _Kind.PATENT: "fa-lightbulb",
    _Kind.CERTIFICATE: "fa-certificate",
    _Kind.AWARD: "fa-trophy",
}

_HINT_CTX = "accounts.academic_item_hint"

#: Növ üzrə modal placeholder-ləri: (Başlıq, Ətraflı).
KIND_HINTS = {
    _Kind.SUBJECT: (
        pgettext_lazy(_HINT_CTX, "Məs.: Verilənlər bazası sistemləri"),
        pgettext_lazy(_HINT_CTX, "Kafedra, səviyyə (bakalavr / magistr)"),
    ),
    _Kind.EDUCATION: (
        pgettext_lazy(_HINT_CTX, "Məs.: Kompüter elmləri üzrə magistr"),
        pgettext_lazy(_HINT_CTX, "Universitet, fakültə, şəhər"),
    ),
    _Kind.EXPERIENCE: (
        pgettext_lazy(_HINT_CTX, "Məs.: Proqram mühəndisi"),
        pgettext_lazy(_HINT_CTX, "Təşkilat, dövr (2019–2023)"),
    ),
    _Kind.PUBLICATION: (
        pgettext_lazy(_HINT_CTX, "Məqalənin adı"),
        pgettext_lazy(_HINT_CTX, "Jurnal, cild / nömrə, həmmüəlliflər"),
    ),
    _Kind.BOOK: (
        pgettext_lazy(_HINT_CTX, "Kitabın / dərsliyin adı"),
        pgettext_lazy(_HINT_CTX, "Nəşriyyat, ISBN, həmmüəlliflər"),
    ),
    _Kind.CONFERENCE: (
        pgettext_lazy(_HINT_CTX, "Məruzənin adı"),
        pgettext_lazy(_HINT_CTX, "Konfransın adı, şəhər"),
    ),
    _Kind.PROJECT: (
        pgettext_lazy(_HINT_CTX, "Layihənin adı"),
        pgettext_lazy(_HINT_CTX, "Maliyyələşdirən qurum, rolunuz (rəhbər / icraçı)"),
    ),
    _Kind.PATENT: (
        pgettext_lazy(_HINT_CTX, "İxtiranın adı"),
        pgettext_lazy(_HINT_CTX, "Patent nömrəsi, verən qurum"),
    ),
    _Kind.CERTIFICATE: (
        pgettext_lazy(_HINT_CTX, "Məs.: Cisco CCNA"),
        pgettext_lazy(_HINT_CTX, "Verən qurum, sertifikat nömrəsi"),
    ),
    _Kind.AWARD: (
        pgettext_lazy(_HINT_CTX, "Mükafatın adı"),
        pgettext_lazy(_HINT_CTX, "Verən qurum, səbəb"),
    ),
}


def _group(kind, items):
    """Template qrupu: növ metadata-sı + qeydlər (idarəetmə və görünüş üçün eyni)."""
    title_hint, detail_hint = KIND_HINTS.get(kind, ("", ""))
    return {
        "kind": str(kind.value),
        "label": kind.label,
        "icon": KIND_ICONS.get(kind, "fa-star"),
        "items": items,
        "is_empty": not items,
        "title_hint": title_hint,
        "detail_hint": detail_hint,
        "allows_attachment": attachments.kind_allows_attachment(kind),
    }


def allowed_kinds_for(capabilities, user=None):
    """Rol imkanlarına görə icazəli növ dəyərlərinin siyahısı (sıralı).

    ``capabilities.is_teacher`` aktiv üzvlük kontekstindən gəlir
    ([[project_role_resolution_needs_active_membership]]); təşkilatsız (fərdi)
    müəllim üçün profil rolu fallback kimi yoxlanılır — rbac-dakı ``is_student``
    fallback-ının güzgüsü.
    """
    caps = capabilities or {}
    is_teaching_staff = bool(
        caps.get("is_teacher") or caps.get("is_unit_manager") or caps.get("is_org_admin") or caps.get("is_superadmin")
    )
    if not is_teaching_staff and user is not None:
        profile_role = getattr(getattr(user, "profile", None), "role", None)
        is_teaching_staff = profile_role in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}
    kinds = []
    for kind in AcademicProfileItem.Kind:
        if kind in TEACHING_ONLY_KINDS and not is_teaching_staff:
            continue
        kinds.append(kind)
    return kinds


def items_grouped_for(user, capabilities):
    """İstifadəçinin qeydlərini template üçün növ üzrə qruplaşdırır.

    Qaytarır: [{"kind", "label", "icon", "items": [...]}, ...] — yalnız
    icazəli növlər (boş qruplar da daxil, «Əlavə et» düyməsi görünsün deyə).
    """
    allowed = allowed_kinds_for(capabilities, user=user)
    items_by_kind = {kind: [] for kind in allowed}
    for item in user.academic_items.all():
        if item.kind in items_by_kind:
            items_by_kind[item.kind].append(item)
    return [_group(kind, items_by_kind[kind]) for kind in allowed]


def display_groups_for(user):
    """Yalnız-oxu görünüş üçün DOLU qruplar (profil məlumatı + açıq profil).

    Rol icazəsi süzgəci yoxdur: qeyd mövcuddursa, yaradılarkən icazə yoxlanıb —
    kənar baxan da sahibin dərc etdiyi siyahını görür.
    """
    items_by_kind = {kind: [] for kind in AcademicProfileItem.Kind}
    for item in user.academic_items.all():
        if item.kind in items_by_kind:
            items_by_kind[item.kind].append(item)
    return [_group(kind, items_by_kind[kind]) for kind in AcademicProfileItem.Kind if items_by_kind[kind]]


def _clean_year(raw_year):
    """İl sahəsini yoxlayır; (ok, dəyər|None, xəta) qaytarır."""
    text = str(raw_year or "").strip()
    if not text:
        return True, None, ""
    if not text.isdigit():
        return False, None, pgettext("accounts.academic_items.error", "İl rəqəmlə yazılmalıdır.")
    year = int(text)
    current_year = timezone.now().year
    if year < YEAR_MIN or year > current_year + 1:
        return (
            False,
            None,
            pgettext("accounts.academic_items.error", "İl %(low)s–%(high)s aralığında olmalıdır.")
            % {"low": YEAR_MIN, "high": current_year + 1},
        )
    return True, year, ""


def _clean_fields(*, kind, title, detail, year, link, capabilities, user=None):
    """Ümumi sahə validasiyası; (ok, cleaned|None, xəta) qaytarır."""
    valid_kinds = {str(k.value) for k in allowed_kinds_for(capabilities, user=user)}
    kind = str(kind or "").strip()
    if kind not in valid_kinds:
        return False, None, pgettext("accounts.academic_items.error", "Bu qeyd növü sizin rolunuz üçün mövcud deyil.")

    title = " ".join(str(title or "").split())
    if not title:
        return False, None, pgettext("accounts.academic_items.error", "Başlıq boş ola bilməz.")
    if len(title) > TITLE_MAX_LENGTH:
        return (
            False,
            None,
            pgettext("accounts.academic_items.error", "Başlıq %(limit)s simvoldan uzun ola bilməz.")
            % {"limit": TITLE_MAX_LENGTH},
        )

    detail = " ".join(str(detail or "").split())
    if len(detail) > DETAIL_MAX_LENGTH:
        return (
            False,
            None,
            pgettext("accounts.academic_items.error", "Ətraflı sahəsi %(limit)s simvoldan uzun ola bilməz.")
            % {"limit": DETAIL_MAX_LENGTH},
        )

    ok, year_value, error = _clean_year(year)
    if not ok:
        return False, None, error

    link = str(link or "").strip()
    if link:
        if len(link) > LINK_MAX_LENGTH:
            return (
                False,
                None,
                pgettext("accounts.academic_items.error", "Keçid %(limit)s simvoldan uzun ola bilməz.")
                % {"limit": LINK_MAX_LENGTH},
            )
        if not (link.startswith("https://") or link.startswith("http://")):
            return (
                False,
                None,
                pgettext("accounts.academic_items.error", "Keçid http:// və ya https:// ilə başlamalıdır."),
            )

    cleaned = {"kind": kind, "title": title, "detail": detail, "year": year_value, "link": link}
    return True, cleaned, ""


def _prepare_upload(kind, attachment):
    """Fayl verilibsə növ icazəsini və məzmunu yoxlayır; (ok, payload|None, xəta)."""
    if attachment is None:
        return True, None, ""
    if not attachments.kind_allows_attachment(kind):
        return False, None, pgettext("accounts.academic_items.error", "Bu qeyd növünə fayl əlavə etmək olmur.")
    return attachments.prepare_attachment(attachment)


def _limit_error():
    return pgettext("accounts.academic_items.error", "Bu növ üzrə maksimum %(limit)s qeyd əlavə etmək olar.") % {
        "limit": MAX_ITEMS_PER_KIND
    }


def create_item(user, capabilities, *, kind, title, detail="", year=None, link="", attachment=None):
    """Yeni qeyd yaradır; (ok, item|None, xəta) qaytarır.

    ``attachment`` — ixtiyari yüklənən fayl (bax services/academic_attachments).
    Uğurda ``item.attachment_event`` = "uploaded" | "" (audit üçün).
    """
    ok, cleaned, error = _clean_fields(
        kind=kind, title=title, detail=detail, year=year, link=link, capabilities=capabilities, user=user
    )
    if not ok:
        return False, None, error

    existing_count = user.academic_items.filter(kind=cleaned["kind"]).count()
    if existing_count >= MAX_ITEMS_PER_KIND:
        return False, None, _limit_error()

    ok, payload, error = _prepare_upload(cleaned["kind"], attachment)
    if not ok:
        return False, None, error

    item = AcademicProfileItem(user=user, **cleaned)
    if payload is None:
        item.save()
        item.attachment_event = ""
        return True, item, ""
    attachments.apply_attachment(item, payload)
    try:
        with transaction.atomic():
            item.save()
    except Exception:
        attachments.discard_new_files(item, [])
        raise
    item.attachment_event = "uploaded"
    return True, item, ""


def update_item(
    user, capabilities, item_id, *, kind, title, detail="", year=None, link="", attachment=None, remove_attachment=False
):
    """Mövcud qeydi yeniləyir; yalnız sahibi üçün. (ok, item|None, xəta).

    Fayl: yeni ``attachment`` köhnəni ƏVƏZ edir; ``remove_attachment`` onu silir;
    növ qoşmasız növə dəyişirsə fayl da silinir. Köhnə fayl saxlanmadan
    tranzaksiya uğurla bitəndən SONRA silinir. ``item.attachment_event`` —
    "uploaded" | "replaced" | "removed" | "".
    """
    item = user.academic_items.filter(pk=item_id).first()
    if item is None:
        return False, None, str(NOT_FOUND_ERROR)

    ok, cleaned, error = _clean_fields(
        kind=kind, title=title, detail=detail, year=year, link=link, capabilities=capabilities, user=user
    )
    if not ok:
        return False, None, error

    # Növ dəyişirsə hədəf növün tavanı da qorunmalıdır — əks halda update ilə
    # per-kind limit keçilə bilərdi (2026-08-15 review tapıntısı).
    if cleaned["kind"] != item.kind:
        target_count = user.academic_items.filter(kind=cleaned["kind"]).exclude(pk=item.pk).count()
        if target_count >= MAX_ITEMS_PER_KIND:
            return False, None, _limit_error()

    ok, payload, error = _prepare_upload(cleaned["kind"], attachment)
    if not ok:
        return False, None, error

    had_attachment = bool(item.attachment)
    old_names = []
    event = ""
    if payload is not None:
        old_names = attachments.apply_attachment(item, payload)
        event = "replaced" if had_attachment else "uploaded"
    elif had_attachment and (remove_attachment or not attachments.kind_allows_attachment(cleaned["kind"])):
        old_names = attachments.clear_attachment(item)
        event = "removed"

    for field, value in cleaned.items():
        setattr(item, field, value)
    update_fields = [*cleaned.keys(), "updated_at"]
    if event:
        update_fields += attachments.ATTACHMENT_FIELDS
    try:
        with transaction.atomic():
            item.save(update_fields=update_fields)
            attachments.delete_files_on_commit(item.attachment.storage, old_names)
    except Exception:
        if payload is not None:
            attachments.discard_new_files(item, old_names)
        raise
    item.attachment_event = event
    return True, item, ""


def delete_item(user, item_id):
    """Qeydi silir; yalnız sahibi üçün. (ok, xəta) qaytarır.

    Qoşma faylları ``post_delete`` siqnalı silir (istifadəçi kaskadında da).
    """
    item = user.academic_items.filter(pk=item_id).first()
    if item is None:
        return False, str(NOT_FOUND_ERROR)
    item.delete()
    return True, ""
