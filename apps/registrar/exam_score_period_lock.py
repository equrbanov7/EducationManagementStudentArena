"""İmtahan balının daxil edilməsi — KEÇMİŞ DÖVR KİLİDİ və RİM rəhbərinin düzəliş rejimi.

SAHİBİN QƏRARI (2026-09-26, hərfi): «burda köhnə ilin balını dəyişmək
olmamalıdır, ancaq RİM rəhbəri tərəfindən təqdimat əsasında ola bilər. O da
jurnalda necə «düzəliş aktivləşdir» düyməsi var, burada da elə olsun gərək.
Burda file yükləmə yeri də olsun gərək, məcburi həm də.»

Qaydalar (hamısı SERVER tərəfdə — UI yalnız əks etdirir):

* **Kilid** — :func:`period_is_locked`: semestr bitib (``end_date`` < bugün),
  CARİ kimi işarələnməyib (``is_current`` üstündür — universitet semestri
  rəsmən uzadıbsa kilid yoxdur, ``handover.period_is_past`` ilə eyni qayda) və
  imtahan sessiyası pəncərəsi (varsa) artıq bağlanıb. Sonuncu şərt QƏSDƏNDİR:
  imtahan semestrin son günündən SONRA keçir — sessiya açıq olduqca İmtahan
  Mərkəzi yazmağa davam etməlidir. Kilidli dövrdə HEÇ KİM (İmtahan Mərkəzi
  daxil) nə ilk bal, nə dəyişiklik, nə də fayl idxalı yaza bilər.
* **Kim aça bilər** — :func:`can_unlock_past_period`: YALNIZ superadmin və
  həmin təşkilatda AKTİV ``ikt_rehber`` (RİM rəhbəri) üzvlüyü. Jurnalın
  ``corrections.can_correct_journal`` köməkçisi QƏSDƏN təkrar istifadə
  OLUNMUR: o, ``journal.correct`` icazəsinə baxır, həmin açar isə ``*``
  daşıyan HƏR rola (rektor, prorektor, sahib…) düşür — sahib isə «ancaq RİM
  rəhbəri» dedi. Rol adı ilə yoxlama ``accounts`` ``_is_rim_head`` ilə eyni
  normallaşdırmadan keçir.
* **Düzəliş rejimi** — jurnalın ``?correct=1`` açarının güzgüsü: səhifə
  ``?ese_correct=1`` ilə açılanda (yalnız icazəli aktor üçün) forma və idxal
  sorğusu ``correction_mode=1`` daşıyır. Rejim SORĞU səviyyəsindədir (sessiya
  vəziyyəti yoxdur): kilidli dövrə yazı ``correction_mode=1`` olmadan icazəli
  aktordan da RƏDD olunur (:func:`assert_write_allowed`) — «düzəliş rejimi
  aktiv olmadan heç nə dəyişmir» (jurnalla eyni prinsip).
* **Təqdimat** — düzəliş rejimində HƏR yazı (ilk daxiletmə də) səbəb + qeyd
  + YÜKLƏNMİŞ skan tələb edir (:func:`require_submission`); sətirlər
  ``ExamScoreEntry`` audit jurnalına düzəliş növü ilə düşür və «Dəyişən
  nəticələr» görünüşündə izlənir.
"""

from __future__ import annotations

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

#: Skan faylının qəbul olunan tipləri / ölçü limiti — model validatoru ilə EYNİ
#: (``ExamScoreSheet.evidence``: PDF/şəkil, 10 MB); şablonun ``accept`` atributu üçün.
EVIDENCE_ACCEPT = ",".join(sorted(EVIDENCE_EXTENSIONS))
EVIDENCE_MAX_MB = _MAX_EVIDENCE_MB

_CTX = "registrar.exam_score_entry"


def period_is_locked(period, today=None) -> bool:
    """Bu dövrün imtahan balları kilidlidirmi (yuxarıdakı qayda; sorğusuz)."""
    if period is None:
        return False
    today = today or timezone.localdate()
    if not period_is_past(period, today):
        return False
    session_end = getattr(period, "exam_session_end", None)
    return not (session_end and session_end >= today)


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


def assert_write_allowed(*, user, offering, correction_mode, organization=None, today=None) -> bool:
    """Yazı qapısı — kilidli dövrdə icazəsiz aktor və ya aktivləşdirilməmiş rejim ``PermissionDenied``.

    Nəticə: dövr kilidlidirsə ``True`` (çağıran təqdimatı məcburi etməlidir),
    əks halda ``False`` (cari dövr — köhnə qayda dəyişmir, əlavə sorğu da yoxdur:
    təşkilat yalnız kilidli dövrdə oxunur, sorğu büdcələri qorunur).
    """
    if not offering_is_locked(offering, today):
        return False
    if not can_unlock_past_period(user, organization or offering.organization):
        raise PermissionDenied(
            pgettext(
                _CTX,
                "Bitmiş dövrün imtahan balları kilidlidir — yalnız RİM rəhbəri təqdimat əsasında düzəliş edə bilər.",
            )
        )
    if not correction_mode:
        raise PermissionDenied(
            pgettext(_CTX, "Bitmiş dövrün balını yazmaq üçün əvvəlcə «Düzəliş rejimini aktivləşdir» düyməsini basın.")
        )
    return True


def require_submission(*, reason, note, evidence) -> None:
    """Düzəliş rejimində təqdimat: səbəb + qeyd + yüklənmiş skan — üçü də məcburi."""
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
    "EVIDENCE_ACCEPT",
    "EVIDENCE_MAX_MB",
    "JUSTIFICATION_FILE_FIELD",
    "assert_write_allowed",
    "can_unlock_past_period",
    "correction_mode_requested",
    "offering_is_locked",
    "period_is_locked",
    "require_submission",
    "submission_evidence",
]
