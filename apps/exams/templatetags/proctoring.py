"""Proktorinq şablon tag-ları (2026-10-01, PROC).

View-lara toxunmadan şablonlara lazım olan kiçik, oxu-yalnız kontekst:

* ``{% proctor_identity attempt as ident %}`` — imtahan başlığında tələbənin ÖZ
  şəkli/adı/qrupu (nəzarətçi yanından keçəndə üzü yoxlasın);
* ``{% proctoring_options_for exam as popts %}`` — imtahan formasında qabaqcıl
  aşkarlama seçimləri (yeni imtahanda defoltlar);
* ``{% proctoring_summary attempt as ps %}`` — müəllimin cəhd səhifəsində risk
  xalı + vahid hadisə xronologiyası (kimliyi göstərmir — anonim yoxlama pozulmur).
"""

from django import template

from apps.exams.services.supervision.proctoring_options import default_proctoring_options, proctoring_options

register = template.Library()


@register.simple_tag
def proctor_identity(attempt):
    if attempt is None or getattr(attempt, "user", None) is None:
        return {}
    from apps.exams.services.supervision.identity import student_identity

    exam = getattr(attempt, "exam", None)
    organization_id = getattr(exam, "organization_id", None)
    try:
        return student_identity(organization_id, attempt.user)
    except Exception:  # noqa: BLE001 — başlıq heç vaxt imtahan səhifəsini sındırmamalıdır
        user = attempt.user
        return {"name": user.get_full_name() or user.username, "username": user.username, "initials": ""}


@register.simple_tag
def proctoring_options_for(exam):
    if exam is None or not getattr(exam, "pk", None):
        return default_proctoring_options()
    return proctoring_options(exam)


@register.simple_tag
def proctoring_summary(attempt, limit=100):
    """Risk + xronologiya; heç bir qeyd yoxdursa və nəzarət sönülüdürsə boş lüğət."""
    if attempt is None or not getattr(attempt, "pk", None):
        return {}
    from apps.exams.services.supervision import get_supervision_config
    from apps.exams.services.supervision.risk import attempt_risk, attempt_timeline

    exam = attempt.exam
    options = proctoring_options(exam)
    risk = attempt_risk(attempt, options["flag_threshold"])
    timeline = attempt_timeline(attempt, limit=int(limit))
    supervised = get_supervision_config(exam) is not None
    if not supervised and not timeline:
        return {}
    return {
        "supervised": supervised,
        "violation_count": attempt.supervision_violation_count,
        "risk": risk,
        "timeline": timeline,
    }


@register.simple_tag
def proctoring_ui_labels():
    """İM monitoru JS-i üçün tərcümə olunmuş etiketlər (``#fxc-proctor-i18n``)."""
    from django.utils.translation import pgettext

    ctx = "exams.proctoring.monitor"
    return {
        "identityTitle": pgettext(ctx, "Kimlik yoxlaması"),
        "noPhoto": pgettext(ctx, "Şəkil yüklənməyib"),
        "group": pgettext(ctx, "Qrup"),
        "studentNumber": pgettext(ctx, "Tələbə №"),
        "risk": pgettext(ctx, "Risk xalı"),
        "riskHint": pgettext(ctx, "Risk xalı / şübhə həddi — qayda pozuntuları və siqnalların ciddiliyinin cəmi"),
        "flagged": pgettext(ctx, "Şübhəli"),
        "signals": pgettext(ctx, "siqnal"),
        "hbStale": pgettext(ctx, "Nəzarət siqnalı kəsilib"),
        "hbMissing": pgettext(ctx, "Nəzarət siqnalı yoxdur"),
        "timeline": pgettext(ctx, "Hadisə xronologiyası"),
        "sourceRule": pgettext(ctx, "Qayda"),
        "sourceSignal": pgettext(ctx, "Siqnal"),
        "counts": pgettext(ctx, "pozuntu sayılır"),
        "noEvents": pgettext(ctx, "Hadisə qeydə alınmayıb."),
        "severity": {
            "critical": pgettext(ctx, "Kritik"),
            "high": pgettext(ctx, "Yüksək"),
            "medium": pgettext(ctx, "Orta"),
            "low": pgettext(ctx, "Aşağı"),
            "info": pgettext(ctx, "Məlumat"),
        },
    }


@register.simple_tag
def proctoring_heartbeat_seconds():
    from apps.exams.services.supervision.heartbeat import HEARTBEAT_INTERVAL_SECONDS

    return HEARTBEAT_INTERVAL_SECONDS


@register.simple_tag
def proctor_severity_label(severity):
    from django.utils.translation import pgettext

    labels = proctoring_ui_labels().get("severity", {})
    return labels.get(severity) or pgettext("exams.proctoring.monitor", "Aşağı")
