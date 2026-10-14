"""Müəllimin illik dərs yükü NORMASI — YEGANƏ hesablama nöqtəsi (sahib 2026-10-14).

Sahib: «Normanı dəyişmək sistem settings-dən olsun: ştat nömrəsi max/min limit, 0.5 ştat üçün ayrı saat hesabı,
1 ştat üçün ayrı, inzibati işləyən üçün ayrı». Dəyərlər «Sistem tənzimləmələri»ndədir (RİM rəhbəri,
``core.runtime_settings``, ``workload.*`` açarları; keşli — dəyişiklik 10–15 saniyəyə hər yerdə görünür).

NORMA QAYDASI (yuxarıdan aşağı, ilk uyğun gələn):

1. müəllimin inzibati vəzifəsi var → ``workload.norm_hours_admin`` (ştat payından asılı deyil);
2. yük profili yoxdur → ``workload.norm_hours_full`` (NK №215: 500);
3. ştat payı 0 (saathesabı / kənar, ştatsız) → ``workload.norm_hours_full`` (əvvəlki davranış: ştatsız
   müəllimin müqayisə bazası 1 ştatdır, doluluq faizi sıfıra bölünmür);
4. ştat payı 0,5 → ``workload.norm_hours_half`` (ayrıca dəyər, 1 ştatdan törəmir);
5. ştat payı 1 → ``workload.norm_hours_full``;
6. digər paylar (0,25 / 0,75 / 1,25 / 1,5 …) → ``round(norm_hours_full × pay)``.

İNZİBATİ VƏZİFƏ = təşkilatda müəllimlikdən BAŞQA aktiv rol üzvlüyü (rektor, prorektor, dekan, dekan müavini,
kafedra müdiri, şöbə müdiri, tyutor, HR …) — «Kadr analitikası»ndakı «İnzibati vəzifə» sütunu ilə eyni qayda;
tələbə / məzun / «member» rolları sayılmır.

``TeacherWorkloadProfile.annual_norm_hours`` artıq OXUNMUR (tarixi sahə; heç bir forma onu dəyişmirdi, bütün
sətirlər 500 idi) — norma həmişə bu modulun qaydası ilə hesablanır.

ŞTAT HƏDDİ: ``workload.staff_rate_min`` … ``workload.staff_rate_max`` (defolt 0,25 … 1,5; KQ-12). Ştat payı
yazılan hər yol (``roster_profile.sync_roster_profile`` — Forma 7 tutuşdurması, ``--create-missing``) bu hədlə
yoxlanır; 0 (saathesabı) həddən azad.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.apps import apps as django_apps
from django.utils.translation import pgettext

from core import runtime_settings as rs

_CTX = "workload.norms"

KEY_FULL = "workload.norm_hours_full"
KEY_HALF = "workload.norm_hours_half"
KEY_ADMIN = "workload.norm_hours_admin"
KEY_RATE_MIN = "workload.staff_rate_min"
KEY_RATE_MAX = "workload.staff_rate_max"

_HALF = Decimal("0.5")
_ONE = Decimal("1")
_ZERO = Decimal("0")

#: İnzibati vəzifə SAYILMAYAN rollar: sırf dərs deyən rollar + tələbə ailəsi + ümumi «member».
#: (``apps.accounts.services.people.constants.TEACHER_ROLE_NAMES``-in güzgüsü — modul sərhədi: import yox.)
NON_ADMIN_ROLE_NAMES = frozenset(
    {
        "teacher",
        "assistant",
        "assistant_teacher",
        "instructor",
        "collaborator",
        "lab_assistant",
        "professor",
        "associate_professor",
        "student",
        "lead_student",
        "alumni",
        "parent",
        "applicant",
        "member",
    }
)


def _fraction(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


@dataclass(frozen=True)
class NormRule:
    full: int
    half: int
    admin: int
    rate_min: Decimal
    rate_max: Decimal

    def base(self, fraction=None, *, has_profile: bool = True) -> int:
        """İnzibati vəzifə nəzərə alınmadan norma (qayda 2–6)."""
        value = _fraction(fraction) if has_profile else None
        if value is None or value <= _ZERO:
            return self.full
        if value == _HALF:
            return self.half
        if value == _ONE:
            return self.full
        return int((Decimal(self.full) * value).quantize(_ONE, rounding=ROUND_HALF_UP))

    def norm(self, fraction=None, *, has_profile: bool = True, is_admin: bool = False) -> int:
        return self.admin if is_admin else self.base(fraction, has_profile=has_profile)


def current_rule() -> NormRule:
    """Cari qayda — «Sistem tənzimləmələri»ndən (keşli), sətir yoxdursa kod defoltları."""
    return NormRule(
        full=rs.get_int(KEY_FULL),
        half=rs.get_int(KEY_HALF),
        admin=rs.get_int(KEY_ADMIN),
        rate_min=rs.get_decimal(KEY_RATE_MIN),
        rate_max=rs.get_decimal(KEY_RATE_MAX),
    )


def admin_teacher_ids(organization, teacher_ids) -> set:
    """Verilən müəllimlərdən inzibati vəzifəsi olanlar (1 sorğu; boş siyahıda 0)."""
    ids = [pk for pk in teacher_ids if pk]
    if organization is None or not ids:
        return set()
    Membership = django_apps.get_model("organizations", "Membership")
    return set(
        Membership.objects.filter(organization=organization, is_active=True, role__is_active=True, user_id__in=ids)
        .exclude(role__name__in=NON_ADMIN_ROLE_NAMES)
        .values_list("user_id", flat=True)
        .distinct()
    )


def norms_for(organization, teacher_ids, profiles: dict, *, rule: NormRule | None = None) -> dict:
    """Müəllim id → illik norma. ``profiles``: id → profil (obyekt və ya ``staff_fraction``-lı dict).

    Üzvlük sorğusu YALNIZ inzibati norma əsas normadan fərqli olan müəllimlər üçün gedir (defoltda: 1 ştatdan
    fərqli payı olanlar) — sorğu büdcəsi defolt halda dəyişmir.
    """
    rule = rule or current_rule()
    ids = [pk for pk in teacher_ids if pk]
    base = {}
    for teacher_id in ids:
        profile = profiles.get(teacher_id)
        base[teacher_id] = rule.base(_profile_fraction(profile), has_profile=profile is not None)
    candidates = [teacher_id for teacher_id, norm in base.items() if norm != rule.admin]
    admins = admin_teacher_ids(organization, candidates) if candidates else set()
    return {teacher_id: (rule.admin if teacher_id in admins else norm) for teacher_id, norm in base.items()}


def norm_hours_for(organization, teacher_id, profile, *, rule: NormRule | None = None) -> int:
    """Bir müəllimin illik norması (``norms_for``-un tək variantı)."""
    if not teacher_id:
        return 0
    return norms_for(organization, [teacher_id], {teacher_id: profile} if profile is not None else {}, rule=rule)[
        teacher_id
    ]


def _profile_fraction(profile):
    if profile is None:
        return None
    if isinstance(profile, dict):
        return profile.get("staff_fraction")
    return getattr(profile, "staff_fraction", None)


# ── Ştat həddi ──────────────────────────────────────────────────────────────


class StaffRateError(ValueError):
    """Ştat payı «Sistem tənzimləmələri»ndəki hədd xaricindədir."""

    code = "workload.staff_rate_out_of_range"

    @property
    def message(self) -> str:
        return str(self.args[0]) if self.args else ""


def staff_rate_error(fraction, *, rule: NormRule | None = None) -> str:
    """Ştat payı yararsızdırsa insan oxunan səbəb, yararlıdırsa ``""``. 0 (saathesabı) həmişə yararlıdır."""
    value = _fraction(fraction)
    if value is None:
        return pgettext(_CTX, "Ştat payı rəqəm olmalıdır.")
    if value == _ZERO:
        return ""
    rule = rule or current_rule()
    if value < _ZERO or not (rule.rate_min <= value <= rule.rate_max):
        return pgettext(
            _CTX,
            "Ştat payı %(value)s icazə verilən %(min)s–%(max)s aralığından kənardır (Sistem tənzimləmələri).",
        ) % {
            "value": rs.decimal_text(value),
            "min": rs.decimal_text(rule.rate_min),
            "max": rs.decimal_text(rule.rate_max),
        }
    return ""


def ensure_staff_rate(fraction, *, rule: NormRule | None = None) -> None:
    message = staff_rate_error(fraction, rule=rule)
    if message:
        raise StaffRateError(message)


def norm_rule_note(rule: NormRule | None = None) -> str:
    """Ekran qeydi: «Norma: 1 ştat — 500 saat, 0,5 ştat — 250 saat, inzibati — 500 saat …»."""
    rule = rule or current_rule()
    return pgettext(
        _CTX,
        "Norma: 1 ştat — %(full)s saat, 0,5 ştat — %(half)s saat, inzibati vəzifəli — %(admin)s saat; digər ştat "
        "payları 1 ştat normasına mütənasibdir. Ştat həddi %(min)s–%(max)s (Sistem tənzimləmələri).",
    ) % {
        "full": rule.full,
        "half": rule.half,
        "admin": rule.admin,
        "min": rs.decimal_text(rule.rate_min),
        "max": rs.decimal_text(rule.rate_max),
    }


__all__ = [
    "NON_ADMIN_ROLE_NAMES",
    "NormRule",
    "StaffRateError",
    "admin_teacher_ids",
    "current_rule",
    "ensure_staff_rate",
    "norm_hours_for",
    "norm_rule_note",
    "norms_for",
    "staff_rate_error",
]
