"""Jurnal SİYASƏTİ — «təsdiqlənmiş sillabus olmadan jurnal açılmaz» açarı.

Dizayn təhvili (`docs/design/handoff_full/README.md` §8/2) tələb edir:

    «Jurnal yaradılması təsdiqlənmiş sillabus olmadan **bloklanır** (403 +
    səbəb kodu); icazə varsa yalnız read-only görünüş qaytarılır.»

Mövcud davranış isə (2026-08, `apps/registrar/syllabus_notice.py`) YALNIZ
XƏBƏRDARLIQDIR: sillabusu olmayan müəllim dərs açır, mövzunu sərbəst mətn kimi
yazır. Köçürülmüş bazada açılışların BÖYÜK ƏKSƏRİYYƏTİNİN sillabusu YOXDUR —
qaydanı qeyd-şərtsiz qoşsaq universitet cari semestrdə jurnal yaza bilməz.

Ona görə qayda **siyasət açarıdır**:

* **DEFAULT = SÖNDÜRÜLÜ** — köçürülmüş data qorunur, davranış dəyişmir
  (yalnız mövcud xəbərdarlıq banneri qalır);
* **AÇIQ** olduqda §8/2 hərfi tətbiq olunur: dərs yaratma servisi
  ``SyllabusGateError`` atır (səbəb kodu ilə), jurnal POST-u **403 + səbəb
  kodu** qaytarır, jurnal görünüşü isə **read-only** olur (`can_edit=False`)
  və müəllim sillabus redaktoruna CTA görür.

Saxlama yeri mövcud ``Organization.settings`` JSON sahəsidir — YENİ CƏDVƏL
YOX, migration YOX (``apps/syllabus/policy.py`` ilə eyni naxış)::

    organization.settings = {"journal": {"require_approved_syllabus": true}}

Modul sərhədi: ``apps.organizations`` İMPORT EDİLMİR (registrar → organizations
statik asılılığı ``scripts/module_deps.py`` qapısındadır) — yalnız ötürülən
obyektin ``settings`` atributu oxunur (ördək tipi).
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext_lazy

_CTX = "registrar.journal_policy"

#: ``Organization.settings`` içindəki bölmə açarı.
POLICY_SECTION = "journal"

#: Siyasət açarının adı.
REQUIRE_APPROVED_SYLLABUS = "require_approved_syllabus"

#: Sahib qərarı (2026-09-03): köçürülmüş datanı qorumaq üçün DEFAULT SÖNDÜRÜLÜ.
DEFAULT_REQUIRE_APPROVED_SYLLABUS = False

#: 403 cavabının səbəb kodu (README §8/2 — «403 + səbəb kodu»).
REASON_NO_APPROVED_SYLLABUS = "no_approved_syllabus"


class SyllabusGateError(Exception):
    """Təsdiqlənmiş sillabus olmadan jurnal əməli — səbəb kodu daşıyır.

    ``args`` TAM ötürülür (``super().__init__(*args)``) ki, istisna ``pickle`` /
    ``copy`` ilə itməsin (flake8-bugbear B042). Səbəb kodu ikinci arqumentdir və
    ``.reason_code`` kimi də oxunur.
    """

    def __init__(self, message="", reason_code=REASON_NO_APPROVED_SYLLABUS):
        super().__init__(message, reason_code)

    @property
    def reason_code(self) -> str:
        return self.args[1] if len(self.args) > 1 else REASON_NO_APPROVED_SYLLABUS

    def __str__(self) -> str:
        return str(self.args[0] or LOCK_TITLE)


LOCK_TITLE = pgettext_lazy(_CTX, "Jurnal təsdiqlənmiş sillabus olmadan açılmır")
LOCK_MESSAGE = pgettext_lazy(
    _CTX,
    "Universitet siyasətinə görə dərs sətri yalnız təsdiqlənmiş sillabusdan yaradılır: mövzu, "
    "saat bölgüsü və qiymətləndirmə strukturu oradan gəlir. Jurnal yalnız oxunuş rejimindədir — "
    "sillabusu tamamlayıb kafedra müdirinin təsdiqinə göndərin.",
)
LOCK_ACTION_LABEL = pgettext_lazy(_CTX, "Sillabusa keç")


def _raw(organization) -> dict:
    settings = getattr(organization, "settings", None)
    if not isinstance(settings, dict):
        return {}
    section = settings.get(POLICY_SECTION)
    return section if isinstance(section, dict) else {}


def require_approved_syllabus(organization=None) -> bool:
    """Siyasət AÇIQDIRMI (default: söndürülü)."""
    value = _raw(organization).get(REQUIRE_APPROVED_SYLLABUS)
    return bool(value) if isinstance(value, bool) else DEFAULT_REQUIRE_APPROVED_SYLLABUS


def offering_has_approved_syllabus(offering) -> bool:
    """Bu açılışın TƏSDİQLƏNMİŞ sillabus versiyası varmı.

    Tələbənin gördüyü qayda ilə eynidir (README §8/9): baxışdakı yeni versiya
    SAYILMIR, yalnız ``approved_version`` — yəni müəllim yeni versiya
    göndərəndə cari semestrin jurnalı bağlanmır.
    """
    from apps.syllabus import services as syllabus_services

    syllabus = syllabus_services.syllabus_for_offering(
        organization=offering.organization,
        offering_id=offering.id,
        subject_id=offering.subject_id,
        period_id=offering.period_id,
        instructor_id=offering.instructor_id,
    )
    if syllabus is None:
        return False
    return syllabus_services.approved_version_for(syllabus) is not None


def syllabus_gate(offering) -> dict:
    """Bir açılış üçün qapı vəziyyəti — şablon və servis qatının TƏK mənbəyi.

    Qaytarır::

        {"enforced": bool,    # siyasət açıqdırmı
         "allowed": bool,     # dərs yaratmaq olarmı
         "locked": bool,      # kilid göstərilməlidirmi (enforced və allowed deyil)
         "reason_code": str,  # 403 gövdəsinə düşən kod ("" — kilid yoxdur)
         "title"/"message"/"action_label"/"action_url"}
    """
    enforced = require_approved_syllabus(getattr(offering, "organization", None))
    if not enforced:
        return {
            "enforced": False,
            "allowed": True,
            "locked": False,
            "reason_code": "",
            "title": "",
            "message": "",
            "action_label": "",
            "action_url": "",
        }
    approved = offering_has_approved_syllabus(offering)
    return {
        "enforced": True,
        "allowed": approved,
        "locked": not approved,
        "reason_code": "" if approved else REASON_NO_APPROVED_SYLLABUS,
        "title": "" if approved else LOCK_TITLE,
        "message": "" if approved else LOCK_MESSAGE,
        "action_label": "" if approved else LOCK_ACTION_LABEL,
        "action_url": "" if approved else f"{reverse('accounts:profile')}?section=syllabus-list",
    }


def ensure_lesson_allowed(offering) -> None:
    """Servis qapısı — icazə yoxdursa :class:`SyllabusGateError` atır."""
    gate = syllabus_gate(offering)
    if gate["locked"]:
        raise SyllabusGateError(str(LOCK_TITLE), gate["reason_code"])


__all__ = [
    "DEFAULT_REQUIRE_APPROVED_SYLLABUS",
    "LOCK_ACTION_LABEL",
    "LOCK_MESSAGE",
    "LOCK_TITLE",
    "POLICY_SECTION",
    "REASON_NO_APPROVED_SYLLABUS",
    "REQUIRE_APPROVED_SYLLABUS",
    "SyllabusGateError",
    "ensure_lesson_allowed",
    "offering_has_approved_syllabus",
    "require_approved_syllabus",
    "syllabus_gate",
]
