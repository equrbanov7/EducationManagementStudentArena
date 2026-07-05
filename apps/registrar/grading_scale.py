"""Hərf qiyməti şkalası (U17) — tenant-konfiqurasiyalı bantlar.

0..100 ümumi bal → hərf + GPA nöqtəsi xəritəsi əvvəllər ``finals._LETTER_BANDS``
sabitində idi. İndi hər təşkilat öz şkalasını ``Organization.settings`` JSON-unda
``letter_bands`` açarı altında saxlaya bilir (cabinet_modules pattern-i ilə eyni);
tənzimləmə yoxdursa və ya format pozulubsa AZ Boloniya default-u işləyir —
mövcud qiymətlər heç vaxt "itmiş" şkala ilə qalmır.

Saxlama formatı: ``[[91, "A", "4.00"], [81, "B", "3.50"], ...]`` — hədlər ciddi
azalan, sonuncu hədd 0 (hər bal bir hərfə düşür), GPA string kimi (JSON float
yuvarlaqlaşdırmasından qaçmaq üçün).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

LETTER_BANDS_SETTINGS_KEY = "letter_bands"

# AZ Boloniya default: (min ümumi bal, hərf, GPA nöqtəsi).
DEFAULT_LETTER_BANDS: tuple[tuple[int, str, Decimal], ...] = (
    (91, "A", Decimal("4.00")),
    (81, "B", Decimal("3.50")),
    (71, "C", Decimal("3.00")),
    (61, "D", Decimal("2.50")),
    (51, "E", Decimal("2.00")),
    (0, "F", Decimal("0.00")),
)

_MAX_BANDS = 12


def _validate(bands: list) -> tuple[tuple[int, str, Decimal], ...]:
    """Normalize + validate raw band rows; raises ``ValueError`` (AZ mesajla)."""
    if not 2 <= len(bands) <= _MAX_BANDS:
        raise ValueError(f"Bant sayı 2–{_MAX_BANDS} aralığında olmalıdır.")
    cleaned: list[tuple[int, str, Decimal]] = []
    letters: set[str] = set()
    for row in bands:
        try:
            threshold_raw, letter_raw, gpa_raw = row
        except (TypeError, ValueError):
            raise ValueError("Hər bant 'hədd:hərf:gpa' formasında olmalıdır.")
        try:
            threshold = int(threshold_raw)
        except (TypeError, ValueError):
            raise ValueError(f"Hədd tam ədəd olmalıdır: {threshold_raw!r}")
        if not 0 <= threshold <= 100:
            raise ValueError(f"Hədd 0–100 aralığında olmalıdır: {threshold}")
        letter = str(letter_raw or "").strip()
        if not letter or len(letter) > 3:
            raise ValueError(f"Hərf 1–3 simvol olmalıdır: {letter_raw!r}")
        if letter in letters:
            raise ValueError(f"Hərf təkrarlanır: {letter}")
        letters.add(letter)
        try:
            gpa = Decimal(str(gpa_raw))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError(f"GPA ədəd olmalıdır: {gpa_raw!r}")
        if not Decimal("0") <= gpa <= Decimal("10"):
            raise ValueError(f"GPA 0–10 aralığında olmalıdır: {gpa}")
        cleaned.append((threshold, letter, gpa))
    thresholds = [t for t, _letter, _gpa in cleaned]
    if thresholds != sorted(thresholds, reverse=True) or len(set(thresholds)) != len(thresholds):
        raise ValueError("Hədlər ciddi azalan sırada olmalıdır (məs. 91, 81, …, 0).")
    if thresholds[-1] != 0:
        raise ValueError("Sonuncu bantın həddi 0 olmalıdır ki, hər bal bir hərfə düşsün.")
    return tuple(cleaned)


def bands_for(organization) -> tuple[tuple[int, str, Decimal], ...]:
    """Təşkilatın şkalası; tənzimləmə yoxdursa/pozulubsa default (heç vaxt raise etmir)."""
    if organization is None:
        return DEFAULT_LETTER_BANDS
    raw = organization.settings if isinstance(organization.settings, dict) else {}
    stored = raw.get(LETTER_BANDS_SETTINGS_KEY)
    if not stored:
        return DEFAULT_LETTER_BANDS
    try:
        return _validate(list(stored))
    except (ValueError, TypeError):
        return DEFAULT_LETTER_BANDS


def score_to_letter(total, organization=None) -> tuple[str, Decimal]:
    """Ümumi bal → (hərf, GPA nöqtəsi) — org şkalası, yoxdursa default."""
    try:
        value = Decimal(str(total or 0))
    except (InvalidOperation, ValueError):
        value = Decimal("0")
    bands = bands_for(organization)
    for threshold, letter, gpa in bands:
        if value >= threshold:
            return letter, gpa
    return bands[-1][1], bands[-1][2]


def set_bands(organization, bands) -> None:
    """Şkalanı yaz (settings JSON-da qalıcı); pozuq giriş ``ValueError`` atır."""
    cleaned = _validate(list(bands))
    if not isinstance(organization.settings, dict):
        organization.settings = {}
    organization.settings[LETTER_BANDS_SETTINGS_KEY] = [
        [threshold, letter, str(gpa)] for threshold, letter, gpa in cleaned
    ]
    organization.save(update_fields=["settings", "updated_at"])


def reset_bands(organization) -> None:
    """Şkalanı default-a qaytar (açarı silir)."""
    if isinstance(organization.settings, dict) and LETTER_BANDS_SETTINGS_KEY in organization.settings:
        organization.settings.pop(LETTER_BANDS_SETTINGS_KEY)
        organization.save(update_fields=["settings", "updated_at"])


def parse_bands_text(text: str) -> tuple[tuple[int, str, Decimal], ...]:
    """Panel mətn formatı: ``"91:A:4.00, 81:B:3.50, …, 0:F:0.00"`` → bantlar.

    Vergüllə ayrılmış sətirlər; hər sətir ``hədd:hərf:gpa``. ``ValueError``
    istifadəçiyə göstərilə bilən AZ mesajla atılır."""
    rows = []
    for chunk in (text or "").replace("\n", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(":")]
        if len(parts) != 3:
            raise ValueError(f"Format 'hədd:hərf:gpa' olmalıdır: {chunk!r}")
        rows.append(parts)
    return _validate(rows)


def bands_text(organization) -> str:
    """Şkalanın panel mətn təsviri (``parse_bands_text``-in tərsi)."""
    return ", ".join(f"{threshold}:{letter}:{gpa}" for threshold, letter, gpa in bands_for(organization))


def is_custom(organization) -> bool:
    """Təşkilat default-dan fərqli şkala saxlayırmı (panel badge-i üçün)."""
    return bands_for(organization) != DEFAULT_LETTER_BANDS
