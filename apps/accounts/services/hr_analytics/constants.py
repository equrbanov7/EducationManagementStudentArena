"""«Kadr analitikası» sabitləri — açarlar, etiketlər, səbət sərhədləri (sahib 2026-10-11).

Etiketlər ``pgettext_lazy`` ilə — modul import vaxtında dil seçilməyib; şablona və ixraca
``str()`` ilə düşür.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

from ..people.constants import TEACHER_ROLE_NAMES

CTX = "accounts.hr_analytics"
#: İcazə açarı — kataloqdakı tərif: ``apps/organizations/permissions_hr.py`` (eyni literal).
PERM_HR_ANALYTICS = "people.hr_analytics"
SECTION = "hr-analytics"
PARAM_PREFIX = "hr_"
PAGE_SIZE = 25
#: Excel ixracında sətir tavanı — bütün universitet heyəti (~800) rahat sığır.
EXPORT_LIMIT = 5000
#: Məlumat keyfiyyəti kartında hər problem üçün göstərilən nümunə ad sayı.
QUALITY_SAMPLE = 8

#: Akademik heyət sayılan rollar: kataloqun müəllim rolları + kafedra müdiri (Forma 7-də
#: kafedra müdiri öz kafedrasının siyahısındadır; dərs deyir, ştat vahidi var).
ACADEMIC_ROLE_NAMES = (*TEACHER_ROLE_NAMES, "chair_head", "department_head")

# ── Tablar ──────────────────────────────────────────────────────────────────
TAB_OVERVIEW = "overview"
TAB_STAFF = "staff"
TAB_COMPOSITION = "composition"
TAB_WORKLOAD = "workload"
TAB_ACTIVITY = "activity"
TAB_QUALITY = "quality"
TAB_PEOPLE = "people"
TABS = (
    (TAB_OVERVIEW, pgettext_lazy(CTX, "Ümumi baxış")),
    (TAB_STAFF, pgettext_lazy(CTX, "Ştat vahidləri")),
    (TAB_COMPOSITION, pgettext_lazy(CTX, "Tərkib")),
    (TAB_WORKLOAD, pgettext_lazy(CTX, "Dərs yükü")),
    (TAB_ACTIVITY, pgettext_lazy(CTX, "Tədris fəaliyyəti")),
    (TAB_QUALITY, pgettext_lazy(CTX, "Məlumat keyfiyyəti")),
    (TAB_PEOPLE, pgettext_lazy(CTX, "Müəllimlər")),
)
TAB_KEYS = tuple(key for key, _label in TABS)

# ── Ştat növü (TeacherWorkloadProfile: staff_fraction + is_external) ────────
STAFF_FULL = "full"
STAFF_HALF = "half"
STAFF_PARTIAL = "partial"
STAFF_HOURLY = "hourly"
STAFF_NONE = "none"
STAFF_TYPES = (
    (STAFF_FULL, pgettext_lazy(CTX, "Tam ştat")),
    (STAFF_HALF, pgettext_lazy(CTX, "0,5 ştat")),
    (STAFF_PARTIAL, pgettext_lazy(CTX, "Digər pay")),
    (STAFF_HOURLY, pgettext_lazy(CTX, "Saathesabı")),
    (STAFF_NONE, pgettext_lazy(CTX, "Təyin edilməyib")),
)
STAFF_KEYS = tuple(key for key, _label in STAFF_TYPES)

# ── Elmi ad / vəzifə (UserProfile.AcademicTitle) ────────────────────────────
#: Yük profilinin vəzifə açarı → profil elmi adı (eyni 5 pillə, fərqli kodlar).
POSITION_TO_TITLE = {
    "assistent": "assistant",
    "muellim": "teacher",
    "bas_muellim": "senior_teacher",
    "dosent": "docent",
    "professor": "professor",
}
TITLE_ORDER = ("assistant", "teacher", "senior_teacher", "docent", "professor")
TITLE_NONE = "none"
DEGREE_ORDER = ("phd", "dsc")
DEGREE_NONE = "none"

# ── Hesab statusu ──────────────────────────────────────────────────────────
STATUS_ACTIVE = "active"
STATUS_BLOCKED = "blocked"
STATUS_ARCHIVED = "archived"
STATUS_DELETED = "deleted"
STATUS_LABELS = {
    STATUS_ACTIVE: pgettext_lazy(CTX, "Aktiv"),
    STATUS_BLOCKED: pgettext_lazy(CTX, "Dayandırılıb"),
    STATUS_ARCHIVED: pgettext_lazy(CTX, "Arxiv"),
    STATUS_DELETED: pgettext_lazy(CTX, "Silinib"),
}
STATUS_ORDER = (STATUS_ACTIVE, STATUS_BLOCKED, STATUS_ARCHIVED, STATUS_DELETED)

# ── Hesab vəziyyəti filtri (``hr_status``) — KPI kartları ilə EYNİ dəstlər ─
#: «Dayandırılıb» KPI-si blok + arxivdir; filtrdə hər ikisi ayrıca da seçilir.
ACCOUNT_ACTIVE = "active"
ACCOUNT_STOPPED = "stopped"
ACCOUNT_BLOCKED = "blocked"
ACCOUNT_ARCHIVED = "archived"
ACCOUNT_NEVER = "never"
ACCOUNT_INITIAL = "initial"
ACCOUNT_NEW = "new"
ACCOUNT_FILTERS = (
    (ACCOUNT_ACTIVE, pgettext_lazy(CTX, "Aktiv hesab")),
    (ACCOUNT_STOPPED, pgettext_lazy(CTX, "Dayandırılıb (blok + arxiv)")),
    (ACCOUNT_BLOCKED, pgettext_lazy(CTX, "Bloklanıb")),
    (ACCOUNT_ARCHIVED, pgettext_lazy(CTX, "Arxivdə")),
    (ACCOUNT_NEVER, pgettext_lazy(CTX, "Heç daxil olmayıb")),
    (ACCOUNT_INITIAL, pgettext_lazy(CTX, "Aktivləşdirilməyib (ilkin parolda)")),
    (ACCOUNT_NEW, pgettext_lazy(CTX, "Bu il yeni hesab")),
)
ACCOUNT_KEYS = tuple(key for key, _label in ACCOUNT_FILTERS)
#: KPI kartı → ``hr_status`` dəyəri (kart klik ediləndə filtr; ``""`` — filtri götür).
KPI_TO_ACCOUNT = {
    "total": "",
    "active": ACCOUNT_ACTIVE,
    "blocked": ACCOUNT_STOPPED,
    "never": ACCOUNT_NEVER,
    "initial": ACCOUNT_INITIAL,
    "new": ACCOUNT_NEW,
}

# ── İnzibati vəzifə (``hr_admin``) ─────────────────────────────────────────
#: Müəllimin akademik rolundan BAŞQA aktiv üzvlüyü (rektor, prorektor, dekan, kafedra müdiri, HR …)
#: inzibati vəzifə sayılır; rol adı kataloqdan (``Role.display_name``), vahid ``scope_unit``-dən.
#: Rol olmayanda profilin sərbəst «Vəzifə» mətni (``UserProfile.staff_position``) göstərilir.
ADMIN_ANY = "any"
ADMIN_NONE = "none"
ADMIN_FIXED = (
    (ADMIN_ANY, pgettext_lazy(CTX, "İnzibati vəzifəsi var")),
    (ADMIN_NONE, pgettext_lazy(CTX, "İnzibati vəzifəsi yoxdur")),
)
#: Rol kataloqunda akademik sayılan, amma inzibati vəzifə KİMİ DƏ göstərilən rollar.
ADMIN_ROLE_NAMES_ALSO = ("chair_head", "department_head")

# ── Dərs yükü bandı filtri (``hr_band``) ``LOAD_BANDS`` açarları ilə ───────

# ── Sıralama (``hr_sort``; «-» prefiksi azalan) ────────────────────────────
SORT_NAME = "name"
SORT_CHAIR = "chair"
SORT_TITLE = "title"
SORT_STAFF = "staff"
SORT_ADMIN = "admin"
SORT_LOAD = "load"
SORT_ACTIVITY = "activity"
SORT_STATUS = "status"
SORT_JOINED = "joined"
SORT_KEYS = (
    SORT_NAME,
    SORT_CHAIR,
    SORT_TITLE,
    SORT_STAFF,
    SORT_ADMIN,
    SORT_LOAD,
    SORT_ACTIVITY,
    SORT_STATUS,
    SORT_JOINED,
)
SORT_DEFAULT = SORT_NAME

# ── Dərs yükü bantları (workload.public.chair_staff_load ilə EYNİ sərhədlər) ─
LOAD_BANDS = (
    ("free", pgettext_lazy(CTX, "Az yüklü (<70%)")),
    ("normal", pgettext_lazy(CTX, "Normal (70–100%)")),
    ("loaded", pgettext_lazy(CTX, "Yüklü (100–120%)")),
    ("risk", pgettext_lazy(CTX, "Həddən artıq (>120%)")),
    ("none", pgettext_lazy(CTX, "Yük yoxdur")),
)
LOAD_BAND_LABELS = dict(LOAD_BANDS)

# ── Məlumat keyfiyyəti problemləri ─────────────────────────────────────────
ISSUE_NO_TITLE = "no_title"
ISSUE_NO_DEGREE = "no_degree"
ISSUE_NO_STAFF = "no_staff_unit"
ISSUE_NO_CHAIR = "no_chair"
ISSUE_DUPLICATE = "duplicate_name"
ISSUE_NO_MEMBERSHIP = "no_membership"
ISSUE_NEVER_LOGGED = "never_logged_in"
ISSUES = (
    (ISSUE_NO_TITLE, pgettext_lazy(CTX, "Elmi adı / vəzifəsi yoxdur")),
    (ISSUE_NO_DEGREE, pgettext_lazy(CTX, "Elmi dərəcəsi qeyd olunmayıb")),
    (ISSUE_NO_STAFF, pgettext_lazy(CTX, "Seçilmiş il üçün ştat vahidi yoxdur")),
    (ISSUE_NO_CHAIR, pgettext_lazy(CTX, "Kafedraya bağlı deyil")),
    (ISSUE_DUPLICATE, pgettext_lazy(CTX, "Eyni ad-soyadlı hesablar")),
    (ISSUE_NO_MEMBERSHIP, pgettext_lazy(CTX, "Ştatı var, amma aktiv üzvlüyü yoxdur")),
    (ISSUE_NEVER_LOGGED, pgettext_lazy(CTX, "Sistemə heç daxil olmayıb")),
)
ISSUE_KEYS = tuple(key for key, _label in ISSUES)
#: «Kritik» (qırmızı) sayılan problemlər — qalanı xəbərdarlıqdır.
CRITICAL_ISSUES = frozenset({ISSUE_NO_STAFF, ISSUE_NO_CHAIR, ISSUE_NO_MEMBERSHIP, ISSUE_DUPLICATE})

UNSET_LABEL = pgettext_lazy(CTX, "Təyin edilməyib")
NO_FACULTY_LABEL = pgettext_lazy(CTX, "Fakültəsiz")
NO_CHAIR_LABEL = pgettext_lazy(CTX, "Kafedrasız")

__all__ = [name for name in dir() if name.isupper()]
