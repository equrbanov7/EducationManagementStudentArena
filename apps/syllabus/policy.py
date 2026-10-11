"""Sillabus SİYASƏT dəyərləri — kodda hardcode YOX, təşkilat səviyyəsində oxunur.

Dizayn təhvili (`docs/design/handoff_full/README.md` §10) dörd product qərarını
«policy dəyəri» kimi saxlamağı tələb edir: qərar veriləndə YALNIZ dəyər dəyişir,
yeni UI və ya migration lazım gəlmir.  Bu modul həmin dəyərlərin YEGANƏ oxu
nöqtəsidir.

Saxlama yeri: mövcud ``Organization.settings`` JSON sahəsi (``syllabus`` açarı) —
yeni cədvəl YARADILMIR::

    organization.settings = {"syllabus": {"sla_days": 5, "escalation_days": 10,
                                          "second_approval_enabled": false,
                                          "assessment": {"attendance": 10, …}}}

Sahib qərarları (`HANDOFF_FULL_PLAN.md` §2/18–20):

* **§10.2** dekanın ikinci sillabus təsdiqi **SÖNDÜRÜLÜ** (`second_approval_enabled=False`);
* **§10.3** versiya təsnifatı müəllimin seçimidir, LAKİN mövzu/çəki/struktur
  dəyişikliyi avtomatik MAJOR-a qaldırır (bax :mod:`apps.syllabus.services.versioning`);
* **§10.4** təsdiq SLA-sı **5 iş günü**, «10 gündən çox gözləyir» isə
  ESKALASİYA həddidir.

Modul sərhədi: burada ``apps.*`` importu YOXDUR — yalnız ötürülən obyektin
``settings`` atributu oxunur (ördək tipi), ona görə ``module_deps`` qrafında yeni
kənar yaranmır. Sərbəst iş bayrağı ``core.academic_rules``-dan gəlir (sahib 2026-10-10).
"""

from __future__ import annotations

from core import academic_rules

from .constants import SELFWORK_TOTAL_SCORE

#: Qiymətləndirmə çəkilərinin BAZA cədvəli (sərbəst işli forma): davamiyyət 10 · midterm 20 ·
#: sərbəst iş 10 · seminar/lab ədədi ortası (``activity``) 10 → semestr 50; yekun imtahan 50.
#: Müəllim HEÇ NƏ bölmür — ``flex`` (100 − kilidli cəm) hesablanır və standartda 0-dır;
#: saxlanır ki, siyasət sonradan yumşaldılsa köhnə «sərbəst pay» yolu işləsin.
#: Cari universitet STANDARTI (sahib 2026-10-10) sərbəst işSİZdir — davamiyyət 10 · midterm 30 ·
#: seminar/lab 10 · yekun 50: :func:`assessment_weights` ``selfwork=False`` ilə sərbəst işin balını
#: midterm-ə keçirir. RİM ``academic.selfwork_enabled`` açarı yandırılanda baza cədvəl geri qayıdır.
#: Ədədlər dəyişdirilmir — ``core.academic_rules`` sabitlərinin güzgüsüdür.
DEFAULT_ASSESSMENT = {
    "attendance": academic_rules.ATTENDANCE_MAX,
    "midterm": academic_rules.MIDTERM_MAX_WITH_SELFWORK,
    "selfwork": SELFWORK_TOTAL_SCORE,
    "activity": academic_rules.ACTIVITY_MAX,
    "final": 50,
}

#: Qiymətləndirmənin ÜMUMİ balı — dəyişməz (universitet normativi).
ASSESSMENT_TOTAL = 100

DEFAULTS = {
    #: Kafedra baxışının hədəf müddəti (iş günü) — README §10.4.
    "sla_days": 5,
    #: Eskalasiya həddi — bu qədər gündən sonra dekana bildiriş / qırmızı KPI.
    "escalation_days": 10,
    #: Dekanın ikinci təsdiqi — README §10.2 default-u SÖNDÜRÜLÜ.
    "second_approval_enabled": False,
    "assessment": dict(DEFAULT_ASSESSMENT),
}


def _raw(organization) -> dict:
    """``organization.settings["syllabus"]`` — hər hansı problemdə boş dict."""
    settings = getattr(organization, "settings", None)
    if not isinstance(settings, dict):
        return {}
    section = settings.get("syllabus")
    return section if isinstance(section, dict) else {}


def _positive_int(value, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def assessment_weights(organization=None, *, selfwork=None) -> dict:
    """Kilidli çəkilər + hesablanmış ``flex`` (standartda 0).

    ``flex`` SAXLANILMIR, hər dəfə ``100 − kilidli cəm`` kimi hesablanır ki,
    siyasət dəyişəndə iki mənbə bir-birindən ayrılmasın.  ``assess`` bölməsinin
    saxlanan açarları köhnə adlarla qalır: ``midterm`` = midterm (aralıq imtahan) payı,
    ``project`` = seminar/lab ədədi ortası payı (``activity``).

    ``selfwork`` — bu qiymətləndirmədə sərbəst iş varmı (sahib 2026-10-10): ``False`` (standart)
    olanda onun balı midterm-ə keçir (20 + 10 = 30), ``selfwork`` çəkisi 0 olur — cəm dəyişmir.
    ``None`` — CARİ qayda (``core.academic_rules.selfwork_enabled``); çağıran adətən
    ``SyllabusRule.selfwork`` ötürür (sahib 2026-10-11: semestrdən asılı deyil, RİM açarıdır).
    """
    if selfwork is None:
        selfwork = academic_rules.selfwork_enabled()
    override = _raw(organization).get("assessment")
    weights = dict(DEFAULT_ASSESSMENT)
    if isinstance(override, dict):
        for key in DEFAULT_ASSESSMENT:
            if key in override:
                try:
                    weights[key] = max(0, int(override[key]))
                except (TypeError, ValueError):
                    continue
    if not selfwork:
        weights["midterm"] += weights["selfwork"]
        weights["selfwork"] = 0
    locked = sum(weights.values())
    weights["flex"] = max(0, ASSESSMENT_TOTAL - locked)
    return weights


def standard_splits(organization=None) -> frozenset:
    """Hər iki qaydanın (sərbəst işli / sərbəst işsiz) STANDART bölgüsü — ``{(midterm, project), …}``.

    RİM tənzimləməsi dəyişəndə əvvəlki standartla saxlanmış ``assess`` bölgüsü «natamam»
    sayılmasın deyə tamamlanma yoxlaması ikisini də qəbul edir (təsdiqlənmiş versiya dəyişməzdir);
    redaktə yolu (``save_section``) isə həmişə versiyanın CARİ standartını yazır."""
    splits = set()
    for flag in (True, False):
        weights = assessment_weights(organization, selfwork=flag)
        splits.add((standard_midterm(weights), standard_project(weights)))
    return frozenset(splits)


def standard_midterm(weights) -> int:
    """Midterm (aralıq imtahan) payı — standart 30 (sərbəst işli formada 20; siyasət ``midterm``);
    köhnə siyasətdə flex-in yarısı."""
    if "midterm" in weights:
        return int(weights["midterm"])
    return int(weights.get("flex", 0)) // 2


def standard_project(weights) -> int:
    """Seminar/lab ədədi ortası payı — standart 10 (siyasət ``activity``)."""
    if "activity" in weights:
        return int(weights["activity"])
    return int(weights.get("flex", 0)) - standard_midterm(weights)


def sla_days(organization=None) -> int:
    """Kafedra baxışının hədəf müddəti (gün)."""
    return _positive_int(_raw(organization).get("sla_days"), DEFAULTS["sla_days"])


def escalation_days(organization=None) -> int:
    """Eskalasiya həddi — SLA-dan KİÇİK ola bilməz (fail-safe normallaşdırma)."""
    target = sla_days(organization)
    value = _positive_int(_raw(organization).get("escalation_days"), DEFAULTS["escalation_days"])
    return max(value, target)


def second_approval_enabled(organization=None) -> bool:
    """Dekanın ikinci təsdiqi açıqdırmı (README §10.2 — default SÖNDÜRÜLÜ)."""
    value = _raw(organization).get("second_approval_enabled")
    return bool(value) if isinstance(value, bool) else DEFAULTS["second_approval_enabled"]


def policy_for(organization=None) -> dict:
    """Bir çağırışda bütün dəyərlər — context qurucuları üçün."""
    return {
        "sla_days": sla_days(organization),
        "escalation_days": escalation_days(organization),
        "second_approval_enabled": second_approval_enabled(organization),
        "assessment": assessment_weights(organization),
    }


__all__ = [
    "ASSESSMENT_TOTAL",
    "DEFAULTS",
    "DEFAULT_ASSESSMENT",
    "assessment_weights",
    "escalation_days",
    "policy_for",
    "second_approval_enabled",
    "sla_days",
    "standard_midterm",
    "standard_project",
    "standard_splits",
]
