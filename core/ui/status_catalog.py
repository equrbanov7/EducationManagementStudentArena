"""Status kataloqu — dizayn handoff-undakı bütün status enum-larının TƏK mənbəyi.

Niyə tək fayl?
--------------
22 ekranın dizaynı ~12 ayrı status ailəsi işlədir (sillabus 7, yük təsdiqi 3,
yük bandı 4, kafedra yükü 4, açılış 3, jurnal qeydi 3, ...). Hər ekranın öz
`{% if %}` zəncirini yazması halında etiket və rəng cütləri sürüşür. Burada
`key → (etiket, ton)` cütü bir dəfə təyin olunur; şablon qatı
`{% ems_status_badge %}` tag-i ilə oxuyur, rəngi isə CSS `ems-badge--<ton>`
class-ından götürür.

RƏNG BURADA YOXDUR. `static/css/ems_ui/badge.css` tonları `--ems-*` tokenlərinə
bağlayır — CLAUDE.md inline-stil qadağası buna görə pozulmur.

Kontrast (handoff §2.3 ziddiyyəti WCAG AA lehinə həll olunub):
  * yaşıl MƏTN  → `--ems-success-700` #15803d (dcfce7 üzərində 4.57 = AA)
  * `--ems-success` #10b981 mətn kimi İŞLƏNMİR (2.31 = keçmir) — yalnız accent
  * `muted` tonu neutral-500 yerinə `--ems-neutral-600` işlədir (4.34 → 6.92)

`core` paketi `apps.*` import ETMİR (module_deps ratchet-i).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.utils.translation import pgettext_lazy

#: Tonlar — CSS `ems-badge--<ton>` class-ları ilə birbaşa uyğun gəlir.
#: Hər ton fon / mətn / kontur üçlüyüdür (bax `static/css/ems_ui/badge.css`).
TONES: tuple[str, ...] = (
    "neutral",  # neutral-100 / neutral-700 / neutral-300
    "muted",  # neutral-100 / neutral-600 / neutral-300  (arxiv, kilid)
    "info",  # primary-50  / primary-800 / primary-200
    "primary",  # primary-100 / primary-800 / primary-600
    "success",  # success-bg  / success-700 / success-bd
    "warning",  # warning-bg  / warning-800 / warning-bd
    "danger",  # danger-bg   / danger-strong / danger-bd
)

_CTX = "ui.status"


@dataclass(frozen=True, slots=True)
class Status:
    """Bir status yazısı.

    `key`      — DB/JSON-da saxlanılan sabit açar (heç vaxt tərcümə olunmur).
    `label`    — istifadəçiyə görünən AZ etiketi (lazy, 4 kataloqda tərcümə).
    `tone`     — `TONES`-dan biri; rəngi CSS verir.
    `strong`   — konturu 2px edir (handoff: «Düzəliş tələb olunur» kartı).
    `order`    — siyahı sıralaması üçün prioritet (kiçik = yuxarı).
    `next_step`— sətir altında göstərilən «növbəti addım» mətni (opsional).
    """

    key: str
    label: object
    tone: str = "neutral"
    strong: bool = False
    order: int = 0
    next_step: object | None = None

    @property
    def css_class(self) -> str:
        base = f"ems-badge ems-badge--{self.tone}"
        return f"{base} is-strong" if self.strong else base


def _s(key, label, tone="neutral", *, strong=False, order=0, next_step=None) -> Status:
    return Status(key=key, label=label, tone=tone, strong=strong, order=order, next_step=next_step)


def _t(text: str):
    return pgettext_lazy(_CTX, text)


# --------------------------------------------------------------------------- #
# 1. Ümumi status şkalası — «00 Dizayn konstantları» faylındakı STATUSES
# --------------------------------------------------------------------------- #
GENERIC: tuple[Status, ...] = (
    _s("draft", _t("Qaralama"), "neutral", order=0),
    _s("pending", _t("Təsdiq gözləyir"), "info", order=1),
    _s("approved", _t("Təsdiqlənib"), "success", order=2),
    _s("returned", _t("Düzəliş gözləyir"), "warning", order=3),
    _s("rejected", _t("Rədd edilib"), "danger", order=4),
    _s("locked", _t("Kilidlənib"), "muted", order=5),
)

# --------------------------------------------------------------------------- #
# 2. Sillabus — ekran 18/19/20 · 7 status, dəqiq enum + «növbəti addım» mətni
#    Sıralama (handoff): revision → rejected → draft → submitted → review →
#    approved → archived
# --------------------------------------------------------------------------- #
SYLLABUS: tuple[Status, ...] = (
    _s(
        "revision",
        _t("Düzəliş tələb olunur"),
        "warning",
        strong=True,
        order=0,
        next_step=_t("Kafedra qeydlərini nəzərə alıb yenidən göndər"),
    ),
    _s(
        "rejected",
        _t("Rədd edilib"),
        "danger",
        order=1,
        next_step=_t("Rədd səbəbini oxuyub yeni versiya yarat"),
    ),
    _s(
        "draft",
        _t("Qaralama"),
        "neutral",
        order=2,
        next_step=_t("Qaralamanı tamamlayıb təsdiqə göndər"),
    ),
    _s(
        "submitted",
        _t("Təqdim edilib"),
        "primary",
        order=3,
        next_step=_t("Kafedra müdirinin baxışı gözlənilir"),
    ),
    _s(
        "review",
        _t("Baxışdadır"),
        "info",
        order=4,
        next_step=_t("Baxış nəticəsi gözlənilir"),
    ),
    _s(
        "approved",
        _t("Təsdiqlənib"),
        "success",
        order=5,
        next_step=_t("Əməl tələb olunmur — versiya kilidlidir"),
    ),
    _s(
        "archived",
        _t("Arxivlənib"),
        "muted",
        order=6,
        next_step=_t("Arxiv qeydi — yalnız baxış"),
    ),
)

# --------------------------------------------------------------------------- #
# 3. Dərs yükü zənciri
# --------------------------------------------------------------------------- #

#: Ekran 15 — dekanlıq növbəsindəki sətir pill-i.
WORKLOAD_LINE: tuple[Status, ...] = (
    _s("sent", _t("Göndərilib"), "primary", order=0),
    _s("returned", _t("Qaytarılıb"), "danger", order=1),
    _s("approved", _t("Təsdiqlənib"), "success", order=2),
)

#: Ekran 13 — koordinator vizası.
WORKLOAD_VISA: tuple[Status, ...] = (
    _s("pending", _t("Gözləyir"), "neutral", order=0),
    _s("reviewed", _t("Baxılıb"), "success", order=1),
    _s("remarked", _t("İradlı"), "warning", order=2),
)

#: Ekran 17 — universitet üzrə yük bandı (rəng şkalası).
LOAD_BAND: tuple[Status, ...] = (
    _s("under", _t("Normadan az (< 90%)"), "info", order=0),
    _s("normal", _t("Normada (90–105%)"), "success", order=1),
    _s("over", _t("Norma üstü (105–125%)"), "warning", order=2),
    _s("critical", _t("Kritik yüklü (> 125%)"), "danger", order=3),
)

#: Ekran 14 — müəllimin norma ilə müqayisəsi.
TEACHER_NORM: tuple[Status, ...] = (
    _s("under", _t("normadan az"), "info", order=0),
    _s("normal", _t("normada"), "success", order=1),
    _s("over", _t("normadan artıq"), "danger", order=2),
)

#: Ekran 02 — kafedranın yük statusu (4 vəziyyət).
DEPT_LOAD: tuple[Status, ...] = (
    _s("free", _t("boş tutum"), "info", order=0),
    _s("normal", _t("normada"), "success", order=1),
    _s("loaded", _t("yüklü"), "warning", order=2),
    _s("risk", _t("risk"), "danger", order=3),
)

#: Ekran 16 — müəllimin yükə münasibəti.
LOAD_OBJECTION_REASONS: tuple[Status, ...] = (
    _s("hours", _t("Saat sayı düz deyil"), "neutral", order=0),
    _s("students", _t("Qrup/tələbə sayı səhvdir"), "neutral", order=1),
    _s("subject", _t("Fənn ixtisasım deyil"), "neutral", order=2),
    _s("norm", _t("Norma həddindən artıqdır"), "neutral", order=3),
)

# --------------------------------------------------------------------------- #
# 4. Tədris planı və semestr açılışı
# --------------------------------------------------------------------------- #

#: Ekran 05 — tədris planının təsdiq zənciri.
PLAN: tuple[Status, ...] = (
    _s("draft", _t("Qaralama"), "neutral", order=0),
    _s("chair_review", _t("Kafedra baxışı"), "info", order=1),
    _s("faculty_council", _t("Fakültə şurası"), "info", order=2),
    _s("teaching_office", _t("Tədris şöbəsi"), "primary", order=3),
    _s("approved", _t("Təsdiqlənib"), "success", order=4),
    # `returned` zəncirin İÇİNDƏ deyil: hər hansı baxış mərhələsindən SƏBƏBLƏ
    # geri qaytarılan plan bura düşür və yalnız qaralamaya qayıdıb yenidən
    # göndərilə bilər (handoff §6.1 «+ returned with reason»).
    _s("returned", _t("Qaytarılıb"), "danger", strong=True, order=5),
)

#: Ekran 07 — açılış sətrinin vəziyyəti.
OFFERING: tuple[Status, ...] = (
    _s("awaiting_teacher", _t("Müəllim gözləyir"), "warning", order=0),
    _s("teacher_assigned", _t("Müəllim təyin olunub"), "primary", order=1),
    _s("journal_open", _t("Jurnalı açılıb"), "success", order=2),
    # Açılış SİLİNMİR — ləğv olunur (handoff §8 qayda 5): sətir qalır, jurnal
    # və qiymət tarixçəsi toxunulmur, yalnız `is_active=False` olur.
    _s("cancelled", _t("Ləğv edilib"), "muted", order=3),
)

#: Ekran 07 — 5 addımlı mərhələ zolağı (stepper) etiketləri.
SEMESTER_STEPS: tuple[Status, ...] = (
    _s("created", _t("Plandan açılış yaradıldı"), "primary", order=0),
    _s("sent", _t("Kafedraya göndərildi"), "primary", order=1),
    _s("assigned", _t("Müəllim təyin olundu"), "primary", order=2),
    _s("journal", _t("Jurnal açıldı"), "primary", order=3),
    _s("locked", _t("Semestr kilidləndi"), "primary", order=4),
)

#: Ekran 03/04 — kataloq yazısının (ixtisas / fənn) vəziyyəti.
#: «Plan yoxdur» və «Ad dublikatı» SAXLANILMIR — hər sorğuda hesablanır
#: (handoff §8/13); burada yalnız onların ETİKET və TONU var.
CATALOG_ENTRY: tuple[Status, ...] = (
    _s("active", _t("Aktiv"), "success", order=0),
    _s("no_plan", _t("Plan yoxdur"), "warning", strong=True, order=1),
    _s("duplicate", _t("Ad dublikatı"), "warning", order=2),
    _s("unused", _t("Planda istifadə olunmur"), "neutral", order=3),
    _s("archived", _t("Arxivdə"), "muted", order=4),
)

# --------------------------------------------------------------------------- #
# 5. Tələbə qəbulu və reyestr
# --------------------------------------------------------------------------- #

#: Ekran 08 — ATİS sətrinin validasiya nəticəsi (copy hərfidir).
INTAKE_ROW: tuple[Status, ...] = (
    _s("ok", _t("Uyğundur"), "success", order=0),
    _s("dup_fin", _t("FİN təkrarlanır — eyni şəxs iki sətirdə"), "danger", order=1),
    _s("unknown_program", _t("İxtisas kodu universitetdə tapılmadı"), "danger", order=2),
    _s("missing_doc", _t("Attestatın surəti yüklənməyib"), "warning", order=3),
)

#: Ekran 08 — 4 addımlı stepper.
INTAKE_STEPS: tuple[Status, ...] = (
    _s("uploaded", _t("ATİS siyahısı yükləndi"), "primary", order=0),
    _s("checked", _t("Tədris şöbəsi yoxladı"), "primary", order=1),
    _s("distributed", _t("Fakültələrə paylandı"), "primary", order=2),
    _s("assigned", _t("Qruplara təyin edildi"), "primary", order=3),
)

#: Ekran 09 — tələbənin AKADEMİK statusu (reyestr sətrinin badge-i).
#: Açarlar ``registrar.AcademicStatus`` ilə eynidir — etiket isə burada TƏK
#: mənbədədir (dizayn 09-un STATUS xəritəsi: Aktiv / Akademik məzuniyyət /
#: Xaric edilib / Məzun). Prototipdəki «Təhsil haqqı borcu» statusu BURAYA
#: DAXİL DEYİL: o, maliyyə modulundan törəyir, akademik status deyil.
STUDENT_STATUS: tuple[Status, ...] = (
    _s("enrolled", _t("Aktiv"), "success", order=0),
    _s("academic_leave", _t("Akademik məzuniyyət"), "warning", order=1),
    _s("expelled", _t("Xaric edilib"), "danger", order=2),
    _s("graduated", _t("Məzun"), "info", order=3),
)

#: Ekran 09 — 6 hərəkət növü (enum kimi saxlanılır).
STUDENT_MOVEMENT: tuple[Status, ...] = (
    _s("group_transfer", _t("Qrupdan qrupa köçürmə"), "info", order=0),
    _s("program_transfer", _t("İxtisasdan ixtisasa köçürmə"), "info", order=1),
    _s("form_change", _t("Əyanidən qiyabiyə (və ya tərsi)"), "info", order=2),
    _s("academic_leave", _t("Akademik məzuniyyət"), "warning", order=3),
    _s("reinstatement", _t("Bərpa"), "success", order=4),
    _s("expulsion", _t("Xaric etmə"), "danger", order=5),
)

# --------------------------------------------------------------------------- #
# 6. Jurnal izi — ekran 21
# --------------------------------------------------------------------------- #
JOURNAL_NOTE: tuple[Status, ...] = (
    _s("on_time", _t("Vaxtında yazılıb"), "success", order=0),
    _s("late", _t("Gec yazılıb"), "warning", order=1),
    _s("empty", _t("Jurnal boşdur"), "danger", order=2),
)

# --------------------------------------------------------------------------- #
# 7. Redaktor autosave vəziyyəti — ekran 19 (`saveState`, 6 vəziyyət)
# --------------------------------------------------------------------------- #
SAVE_STATE: tuple[Status, ...] = (
    _s("saved", _t("Saxlanıldı"), "success", order=0),
    _s("saving", _t("Saxlanılır…"), "info", order=1),
    _s("failed", _t("Son dəyişiklik saxlanılmadı"), "danger", order=2),
    _s("offline", _t("İnternet bağlantısı yoxdur"), "warning", order=3),
    _s("conflict", _t("Başqa versiya ilə konflikt yarandı"), "danger", order=4),
    _s("stale", _t("Səhifədəki məlumat köhnəlmişdir"), "warning", order=5),
)

# --------------------------------------------------------------------------- #
# 8. Arxiv / yalnız-oxunuş rejimi (handoff §4 — bütün ekranlar üçün ortaq)
# --------------------------------------------------------------------------- #
ARCHIVE_MODE: tuple[Status, ...] = (
    _s("open", _t("mərhələ açıqdır"), "info", order=0),
    _s("archived", _t("arxiv — yalnız oxunuş"), "warning", order=1),
)


#: Ailə adı → statuslar. Şablon tag-i yalnız bu xəritədən oxuyur.
FAMILIES: dict[str, tuple[Status, ...]] = {
    "generic": GENERIC,
    "syllabus": SYLLABUS,
    "workload_line": WORKLOAD_LINE,
    "workload_visa": WORKLOAD_VISA,
    "load_band": LOAD_BAND,
    "teacher_norm": TEACHER_NORM,
    "dept_load": DEPT_LOAD,
    "load_objection": LOAD_OBJECTION_REASONS,
    "plan": PLAN,
    "offering": OFFERING,
    "catalog_entry": CATALOG_ENTRY,
    "semester_steps": SEMESTER_STEPS,
    "intake_row": INTAKE_ROW,
    "intake_steps": INTAKE_STEPS,
    "student_movement": STUDENT_MOVEMENT,
    "student_status": STUDENT_STATUS,
    "journal_note": JOURNAL_NOTE,
    "save_state": SAVE_STATE,
    "archive_mode": ARCHIVE_MODE,
}


class UnknownStatusFamily(KeyError):
    """Kataloqda olmayan ailə adı — şablonda səssiz keçmir, dərhal görünür."""


def family(name: str) -> tuple[Status, ...]:
    """Ailəni qaytarır; ad yoxdursa açıq xəta atır (səssiz boş siyahı YOX)."""
    try:
        return FAMILIES[name]
    except KeyError as exc:  # pragma: no cover — yalnız yanlış çağırışda
        raise UnknownStatusFamily(f"Naməlum status ailəsi: {name!r}") from exc


def get(name: str, key: str) -> Status | None:
    """`key` üçün statusu qaytarır; tapılmasa `None` (çağıran fallback verir)."""
    for status in family(name):
        if status.key == key:
            return status
    return None


def label(name: str, key: str) -> object:
    """Etiket; naməlum açarda açarın özü qaytarılır (heç vaxt boş sətir)."""
    status = get(name, key)
    return status.label if status is not None else key


def keys(name: str) -> tuple[str, ...]:
    return tuple(status.key for status in family(name))


def choices(name: str) -> list[tuple[str, object]]:
    """Django `choices` formatı — model/form sahələri üçün."""
    return [(status.key, status.label) for status in family(name)]


def order_index(name: str, key: str) -> int:
    """Siyahı sıralaması üçün prioritet; naməlum açar sona düşür."""
    status = get(name, key)
    return status.order if status is not None else 10_000


def sort_key(name: str, key: str) -> tuple[int, str]:
    return (order_index(name, key), key)


def sorted_by_status(name: str, rows: Iterable, attr: str = "status") -> list:
    """Sətirləri handoff-dakı status prioriteti ilə sıralayır."""
    return sorted(rows, key=lambda row: sort_key(name, getattr(row, attr, "")))
