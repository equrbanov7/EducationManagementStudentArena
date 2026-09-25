"""İmtahan balının daxil edilməsi — BİTMİŞ DÖVR QAYDALARI və RİM rəhbərinin düzəliş rejimi.

SAHİBİN QƏRARLARI (2026-09-26, hərfi):

1. «burda köhnə ilin balını dəyişmək olmamalıdır, ancaq RİM rəhbəri tərəfindən
   təqdimat əsasında ola bilər. O da jurnalda necə «düzəliş aktivləşdir» düyməsi
   var, burada da elə olsun gərək. Burda file yükləmə yeri də olsun gərək,
   məcburi həm də.»
2. (eyni gün, dəqiqləşdirmə) «İM də edə bilsin, lakin nəticə çox köhnənindirsə
   köçürüləndə sənədlə olsun gərək.»

Qaydalar (hamısı SERVER tərəfdə — UI yalnız əks etdirir):

* **Bitmiş dövr** — :func:`period_is_locked`: semestr bitib (``end_date`` <
  bugün), CARİ kimi işarələnməyib (``is_current`` üstündür —
  ``handover.period_is_past`` ilə eyni qayda) və imtahan sessiyası pəncərəsi
  (varsa) artıq bağlanıb (imtahan semestrin son günündən SONRA keçir).
* **İlk daxiletmə (boş bal → dəyər)** bitmiş dövrdə də İmtahan Mərkəzinə AÇIQDIR.
  Dövr :data:`PAST_FIRST_ENTRY_DOCUMENT_AFTER_DAYS` gündən ÇOX əvvəl bağlanıbsa
  («çox köhnə nəticə») ilk daxiletmə də təqdimatlıdır: səbəb + qeyd + yüklənmiş
  skan. Bağlanma tarixi = ``max(end_date, exam_session_end)``.
* **Yazılmış balın dəyişdirilməsi** bitmiş dövrdə YALNIZ superadmin və həmin
  təşkilatda AKTİV ``ikt_rehber`` (RİM rəhbəri) üçündür
  (:func:`can_unlock_past_period`), YALNIZ «Düzəliş rejimi»ndə və təqdimatla.
  Jurnalın ``corrections.can_correct_journal`` köməkçisi QƏSDƏN təkrar istifadə
  OLUNMUR: o, ``journal.correct``-ə baxır, həmin açar isə ``*`` daşıyan HƏR rola
  (rektor, prorektor, sahib…) düşür — sahib isə «ancaq RİM rəhbəri» dedi.
* **Düzəliş rejimi** — jurnalın ``?correct=1`` açarının güzgüsü: səhifə
  ``?ese_correct=1`` ilə açılanda (yalnız icazəli aktor üçün) forma və idxal
  sorğusu ``correction_mode=1`` daşıyır. Rejim SORĞU səviyyəsindədir (sessiya
  vəziyyəti yoxdur). İcazəsiz aktorun göndərdiyi ``correction_mode=1`` bütün
  sorğunu ``PermissionDenied`` ilə dayandırır. Rejimdə HƏR yazı (ilk daxiletmə
  də) təqdimatlıdır; sətirlər düzəliş növü ilə audit olunur.

Sətir-sətir tətbiq ``exam_score_entry.record_exam_score``-dadır
(:class:`PeriodWritePolicy` ötürülür); toplu qapı ``save_roster_scores``-dadır.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from django.utils.translation import pgettext

from core.roles import ProfileRole

from .handover import period_is_past
from .models.exam_score_entry import _MAX_EVIDENCE_MB, EVIDENCE_EXTENSIONS

#: POST/FormData sahəsi və GET açarı (jurnaldakı ``correct=1`` güzgüsü).
CORRECTION_MODE_FIELD = "correction_mode"
CORRECTION_MODE_QUERY = "ese_correct"

#: Təqdimat skanının təsdiq dialoqundakı fayl sahəsi (vərəq kartındakı
#: ``sheet_evidence``-in alternativi — hər ikisi partiyanın skanı olur).
JUSTIFICATION_FILE_FIELD = "justification_evidence"

#: «Çox köhnə nəticə» həddi (sahib 2026-09-26): dövr bu qədər gündən ÇOX əvvəl
#: bağlanıbsa bitmiş dövrə İLK daxiletmə də sənədlə olur. Hədd daxilində ilk
#: daxiletmə cari dövrdəki kimi sərbəstdir (skan opsional).
PAST_FIRST_ENTRY_DOCUMENT_AFTER_DAYS = 60

#: Skan faylının qəbul olunan tipləri / ölçü limiti — model validatoru ilə EYNİ
#: (``ExamScoreSheet.evidence``: PDF/şəkil, 10 MB); şablonun ``accept`` atributu üçün.
EVIDENCE_ACCEPT = ",".join(sorted(EVIDENCE_EXTENSIONS))
EVIDENCE_MAX_MB = _MAX_EVIDENCE_MB

_CTX = "registrar.exam_score_entry"


@dataclass(frozen=True)
class PeriodWritePolicy:
    """Bir sorğunun (açılış × aktor × rejim) yazı qaydası — sətir-sətir tətbiq olunur.

    * ``locked`` — dövr bitib;
    * ``correction_mode`` — RİM rəhbərinin düzəliş rejimi (icazə yoxlanıb);
    * ``first_entry_needs_document`` — «çox köhnə» dövr: ilk daxiletmə də təqdimatlı.
    """

    locked: bool = False
    correction_mode: bool = False
    first_entry_needs_document: bool = False

    @property
    def changes_blocked(self) -> bool:
        """Yazılmış balın dəyişdirilməsi bağlıdır (bitmiş dövr, rejim aktiv deyil)."""
        return self.locked and not self.correction_mode

    @property
    def every_write_needs_submission(self) -> bool:
        """Bu sorğuda yazılan HƏR sətir təqdimat tələb edir (rejim və ya çox köhnə dövr)."""
        return self.correction_mode or (self.locked and self.first_entry_needs_document)


CURRENT_PERIOD = PeriodWritePolicy()


def _as_date(value):
    if value is None or isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])


def period_closed_on(period):
    """Dövrün faktiki bağlanma tarixi — ``end_date`` və imtahan sessiyasının sonundan GEC olanı."""
    dates = [_as_date(getattr(period, name, None)) for name in ("end_date", "exam_session_end")]
    dates = [value for value in dates if value is not None]
    return max(dates) if dates else None


def period_is_locked(period, today=None) -> bool:
    """Bu dövr BİTİBMİ (yuxarıdakı qayda; sorğusuz)."""
    if period is None:
        return False
    today = today or timezone.localdate()
    if not period_is_past(period, today):
        return False
    session_end = _as_date(getattr(period, "exam_session_end", None))
    return not (session_end and session_end >= today)


def first_entry_needs_document(period, today=None) -> bool:
    """Bitmiş dövr :data:`PAST_FIRST_ENTRY_DOCUMENT_AFTER_DAYS` gündən çox əvvəl bağlanıbmı."""
    today = today or timezone.localdate()
    if not period_is_locked(period, today):
        return False
    closed_on = period_closed_on(period)
    return bool(closed_on and (today - closed_on).days > PAST_FIRST_ENTRY_DOCUMENT_AFTER_DAYS)


def offering_is_locked(offering, today=None) -> bool:
    return period_is_locked(getattr(offering, "period", None), today)


def _is_superadmin(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def can_unlock_past_period(user, organization) -> bool:
    """Superadmin və ya ``organization``-da AKTİV ``ikt_rehber`` üzvlüyü (BİR sorğu)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if _is_superadmin(user):
        return True
    if organization is None:
        return False
    from django.apps import apps as django_apps

    membership_model = django_apps.get_model("organizations", "Membership")
    role_names = membership_model.objects.filter(
        user=user, organization=organization, is_active=True, role__is_active=True
    ).values_list("role__name", flat=True)
    return any(ProfileRole.normalize_membership_role_name(name) == ProfileRole.IKT_REHBER for name in role_names)


def correction_mode_requested(data) -> bool:
    """``correction_mode=1`` (POST / FormData) və ya ``ese_correct=1`` (GET) varmı."""
    if data is None:
        return False
    return (data.get(CORRECTION_MODE_FIELD) or data.get(CORRECTION_MODE_QUERY) or "").strip() == "1"


def write_policy(*, user, offering, correction_mode, organization=None, today=None) -> PeriodWritePolicy:
    """Sorğunun yazı qaydası; icazəsiz aktorun ``correction_mode``-u ``PermissionDenied``.

    Cari dövrdə :data:`CURRENT_PERIOD` (köhnə qayda, əlavə sorğu yoxdur — təşkilat
    və üzvlük yalnız bitmiş dövrdə düzəliş rejimi istənəndə oxunur).
    """
    period = getattr(offering, "period", None)
    today = today or timezone.localdate()
    if not period_is_locked(period, today):
        return CURRENT_PERIOD
    if correction_mode and not can_unlock_past_period(user, organization or offering.organization):
        raise PermissionDenied(
            pgettext(
                _CTX,
                "Bitmiş dövrün imtahan balları kilidlidir — yalnız RİM rəhbəri təqdimat əsasında düzəliş edə bilər.",
            )
        )
    return PeriodWritePolicy(
        locked=True,
        correction_mode=bool(correction_mode),
        first_entry_needs_document=first_entry_needs_document(period, today),
    )


def change_blocked_error() -> ValidationError:
    """Bitmiş dövrdə yazılmış balı rejimsiz dəyişmə cəhdi (sətir xətası)."""
    return ValidationError(
        pgettext(
            _CTX,
            "Bitmiş dövrdə yazılmış balı dəyişmək yalnız RİM rəhbəri tərəfindən düzəliş rejimində mümkündür.",
        )
    )


def require_submission(*, reason, note, evidence) -> None:
    """Təqdimat: səbəb + qeyd + yüklənmiş skan — üçü də məcburi."""
    from .models import CorrectionReason

    if reason not in CorrectionReason.values or not (note or "").strip() or not evidence:
        raise ValidationError(
            pgettext(_CTX, "Bitmiş dövrdə hər yazı təqdimat tələb edir — səbəb, qeyd və skan edilmiş sənəd məcburidir.")
        )


def submission_evidence(files):
    """Təqdimat skanı: dialoqdakı fayl (üstündür) və ya vərəq kartındakı ``sheet_evidence``."""
    if files is None:
        return None
    return files.get(JUSTIFICATION_FILE_FIELD) or files.get("sheet_evidence")


__all__ = [
    "CORRECTION_MODE_FIELD",
    "CORRECTION_MODE_QUERY",
    "CURRENT_PERIOD",
    "EVIDENCE_ACCEPT",
    "EVIDENCE_MAX_MB",
    "JUSTIFICATION_FILE_FIELD",
    "PAST_FIRST_ENTRY_DOCUMENT_AFTER_DAYS",
    "PeriodWritePolicy",
    "can_unlock_past_period",
    "change_blocked_error",
    "correction_mode_requested",
    "first_entry_needs_document",
    "offering_is_locked",
    "period_closed_on",
    "period_is_locked",
    "require_submission",
    "submission_evidence",
    "write_policy",
]
