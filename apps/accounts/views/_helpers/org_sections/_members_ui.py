"""«Heyət idarəetməsi» — UI qatı: etiketlər, KPI kartları, filtr sahələri.

Bölmə 2026-09-09-da sahibin tapşırığı ilə yenidən quruldu: DƏVƏT/MÜRACİƏT
panelləri (təsdiq gözləyən tələbələr, təşkilata bağlı olmayan hesablar,
göndərilmiş dəvətlər — tələbə · müəllim · heyət) BURADAN ÇIXARILDI. Bu ekran
artıq YALNIZ təşkilatın mövcud üzvlərini idarə edir; yeni şəxs «Tələbə/Müəllim
əlavəsi» (intake) bölmələrindən əlavə olunur.

Bu modul yalnız MƏTN və KOMPONENT MÜQAVİLƏSİ qurur — sorğular
`_members_registry.py`-dədir (modul ölçü büdcəsi, `scripts/check_module_size.py`).
"""

from django.utils.translation import pgettext

CTX = "accounts.staff_management"

#: Filtr parametrlərinin ad fəzası (`ems_ui/_filter_bar.html` prefiksi).
PREFIX = "hm_"

#: `hm_kind` filtrinin dəyərləri — KPI kartları da bunları göndərir.
KIND_STUDENTS = "students"
KIND_TEACHERS = "teachers"
KIND_STAFF = "staff"
KIND_LEADERS = "leaders"
KINDS = (KIND_STUDENTS, KIND_TEACHERS, KIND_STAFF, KIND_LEADERS)

#: Sıralama açarı → User sorğusunun `order_by` sütunları.
SORTS = {
    "name": ("first_name", "last_name", "username"),
    "-name": ("-first_name", "-last_name", "-username"),
    "newest": ("-joined_at", "username"),
    "oldest": ("joined_at", "username"),
}
DEFAULT_SORT = "name"


def kind_label(kind: str) -> str:
    return {
        KIND_STUDENTS: pgettext(CTX, "Tələbə"),
        KIND_TEACHERS: pgettext(CTX, "Müəllim"),
        KIND_STAFF: pgettext(CTX, "Heyət"),
    }.get(kind, pgettext(CTX, "Heyət"))


def kind_options():
    return [
        {"value": "", "label": pgettext(CTX, "Hamısı")},
        {"value": KIND_STUDENTS, "label": pgettext(CTX, "Tələbələr")},
        {"value": KIND_TEACHERS, "label": pgettext(CTX, "Müəllimlər")},
        {"value": KIND_STAFF, "label": pgettext(CTX, "Heyət")},
        {"value": KIND_LEADERS, "label": pgettext(CTX, "Rəhbərlik")},
    ]


def sort_options():
    return [
        {"value": "name", "label": pgettext(CTX, "Ad (A→Z)")},
        {"value": "-name", "label": pgettext(CTX, "Ad (Z→A)")},
        {"value": "newest", "label": pgettext(CTX, "Ən son qoşulan")},
        {"value": "oldest", "label": pgettext(CTX, "Ən əvvəl qoşulan")},
    ]


def columns():
    return [
        {"key": "member", "label": pgettext(CTX, "Üzv")},
        {"key": "roles", "label": pgettext(CTX, "Rollar")},
        {"key": "position", "label": pgettext(CTX, "Vəzifə")},
        {"key": "unit", "label": pgettext(CTX, "Bölmə")},
        {"key": "joined", "label": pgettext(CTX, "Qoşulma")},
        {"key": "actions", "label": ""},
    ]


def kpi_tiles(*, totals, kind):
    """KPI sırası — kartlar KLİK EDİLƏ BİLƏN `hm_kind` filtridir.

    «Üzv» kartı filtr DEYİL (bütün siyahı «Sıfırla» ilə qayıdır); qalan dördü
    seçilmiş filtri `aria-pressed` ilə göstərir.
    """
    return [
        {
            "label": pgettext(CTX, "Üzv"),
            "value": totals["members"],
            "tone": "primary",
            "note": pgettext(CTX, "fərqli şəxs (bir neçə rolu olan bir dəfə sayılır)"),
        },
        {
            "label": pgettext(CTX, "Tələbə"),
            "value": totals["students"],
            "filter": KIND_STUDENTS,
            "pressed": kind == KIND_STUDENTS,
        },
        {
            "label": pgettext(CTX, "Müəllim"),
            "value": totals["teachers"],
            "filter": KIND_TEACHERS,
            "pressed": kind == KIND_TEACHERS,
        },
        {
            "label": pgettext(CTX, "Heyət"),
            "value": totals["staff"],
            "filter": KIND_STAFF,
            "pressed": kind == KIND_STAFF,
            "note": pgettext(CTX, "tələbə və müəllim olmayan rollar"),
        },
        {
            "label": pgettext(CTX, "Rəhbərlik"),
            "value": totals["leaders"],
            "filter": KIND_LEADERS,
            "pressed": kind == KIND_LEADERS,
            "tone": "accent-primary",
            "note": pgettext(CTX, "dekan, müdir, koordinator, idarəetmə rolları"),
        },
    ]


def filter_fields(*, search, kind, role, unit_id, sort, role_options, unit_options):
    return [
        {
            "name": f"{PREFIX}q",
            "label": pgettext(CTX, "Axtarış"),
            "kind": "search",
            "value": search,
            "wide": True,
            "placeholder": pgettext(CTX, "Ad, istifadəçi adı, e-poçt və ya vəzifə"),
        },
        {
            "name": f"{PREFIX}kind",
            "label": pgettext(CTX, "Növ"),
            "kind": "select",
            "options": kind_options(),
            "value": kind,
        },
        {
            "name": f"{PREFIX}role",
            "label": pgettext(CTX, "Təşkilat rolu"),
            "kind": "select",
            "options": [{"value": "", "label": pgettext(CTX, "Bütün rollar")}] + role_options,
            "value": role,
            "searchable": True,
        },
        {
            "name": f"{PREFIX}unit",
            "label": pgettext(CTX, "Bölmə"),
            "kind": "select",
            "options": [{"value": "", "label": pgettext(CTX, "Bütün bölmələr")}] + unit_options,
            "value": unit_id,
            "searchable": True,
        },
        {
            "name": f"{PREFIX}sort",
            "label": pgettext(CTX, "Sıralama"),
            "kind": "select",
            "options": sort_options(),
            "value": sort,
            "default": DEFAULT_SORT,
        },
    ]


def count_label(total: int) -> str:
    return pgettext(CTX, "Nəticə: %(n)d üzv") % {"n": total}


def empty_state(*, filtered: bool, scope_active: bool):
    """Boş vəziyyət mətni — filtrli, əhatəli və «heç kim yoxdur» halları ayrıdır."""
    if filtered:
        return (
            pgettext(CTX, "Filtrə uyğun üzv yoxdur"),
            pgettext(CTX, "Axtarışı dəyişin və ya «Sıfırla» ilə bütün siyahıya qayıdın."),
        )
    if scope_active:
        return (
            pgettext(CTX, "Əhatənizdə üzv yoxdur"),
            pgettext(CTX, "Yalnız sizə təyin edilmiş bölmənin (fakültə/kafedra) üzvləri görünür."),
        )
    return (
        pgettext(CTX, "Hələ üzv yoxdur"),
        pgettext(CTX, "Yeni şəxslər «Tələbə əlavəsi» və «Müəllim əlavəsi» bölmələrindən əlavə olunur."),
    )


def subtitle(*, scope_active: bool) -> str:
    base = pgettext(
        CTX,
        "Təşkilatın mövcud üzvləri — tələbə, müəllim və heyət bir siyahıda. "
        "«Kart» şəxsin bütün rollarını açır; «Çıxar» üzvlüyü səbəblə deaktiv edir "
        "(hesab SİLİNMİR, audit jurnalına yazılır).",
    )
    if scope_active:
        return base + " " + pgettext(CTX, "Siyahı sizə təyin edilmiş bölmənin alt-ağacı ilə məhdudlaşır.")
    return base
