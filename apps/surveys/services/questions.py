"""Sorğu qurucusu (2026-09-30) — sual redaktoru: bölmələr, suallar, seçimlər, sıra.

KİLİD (nəticə bütövlüyü): sorğuya cavab gələndən sonra (``survey_builder.has_answers``) struktur
dəyişmir — sual əlavə/silmək, növ, məcburilik, bölmə, seçim sayı, sıra, çox seçimin min/max-ı
BAĞLIDIR. Yalnız «yazı səhvi» səviyyəsində mətn düzəlişi olur (sual, izah, seçim etiketləri,
Likert/NPS etiketləri): hər sahə köhnə mətnə ``difflib`` nisbəti ≥ ``TYPO_EDIT_MIN_RATIO`` ilə
yaxın olmalıdır; köhnə mətn ``SurveyQuestion.history``-yə yazılır (versiya) və audit olunur.

Seçim açarları (``choices[].key``) sabitdir: etiket düzəlişi nəticələri qırmır. Mətn sahəsi
(``choices_text``) — hər sətir bir seçim; sətir mövqeyi köhnə açarı saxlayır.
"""

from __future__ import annotations

import difflib
import secrets

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import pgettext

from ..constants import (
    CHOICE_KINDS,
    GENERIC_KINDS,
    HELP_TEXT_MAX_LENGTH,
    MAX_OPTIONS,
    MAX_PAGES,
    MAX_QUESTIONS,
    MIN_OPTIONS,
    OPTION_MAX_LENGTH,
    QUESTION_TEXT_MAX_LENGTH,
    TEACHER_EVAL_KINDS,
    TITLE_MAX_LENGTH,
    TYPO_EDIT_MIN_RATIO,
    QuestionKind,
    Section,
)
from ..models import SurveyPage, SurveyQuestion
from .survey_builder import BuilderError, audit, has_answers

_CTX = "surveys.builder"


def allowed_kinds(survey) -> tuple:
    return TEACHER_EVAL_KINDS if survey.is_teacher_evaluation else GENERIC_KINDS


def is_locked(survey) -> bool:
    return has_answers(survey)


def _typo_ok(old, new) -> bool:
    old, new = (old or "").strip(), (new or "").strip()
    if old == new:
        return True
    if not old or not new:
        return False
    return difflib.SequenceMatcher(None, old, new).ratio() >= TYPO_EDIT_MIN_RATIO


def _typo_error():
    return BuilderError(
        pgettext(
            _CTX,
            "Cavab gəlmiş sualda yalnız kiçik düzəliş (yazı səhvi) mümkündür — mənanı dəyişmək üçün sorğunun "
            "dublikatını yaradın.",
        )
    )


def _text(value, limit, *, required=False, label=""):
    value = (value or "").strip()
    if required and not value:
        raise BuilderError(pgettext(_CTX, "Sualın mətni boş ola bilməz."))
    if len(value) > limit:
        raise BuilderError(
            pgettext(_CTX, "«%(field)s» %(limit)s simvoldan uzun ola bilməz.") % {"field": label, "limit": limit}
        )
    return value


def _flag(data, name) -> bool:
    return str(data.get(name) or "").strip().lower() in ("1", "true", "on", "yes")


# ── Seçimlər / parametrlər ──────────────────────────────────────────────────


def _new_key(existing) -> str:
    while True:
        key = secrets.token_hex(3)
        if key not in existing:
            return key


def parse_choices(raw_text, existing, *, locked) -> list:
    labels = [line.strip() for line in (raw_text or "").splitlines() if line.strip()]
    if len(labels) < MIN_OPTIONS:
        raise BuilderError(pgettext(_CTX, "Ən azı %(n)s seçim yazın (hər sətirdə bir).") % {"n": MIN_OPTIONS})
    if len(labels) > MAX_OPTIONS:
        raise BuilderError(pgettext(_CTX, "Ən çoxu %(n)s seçim ola bilər.") % {"n": MAX_OPTIONS})
    if any(len(label) > OPTION_MAX_LENGTH for label in labels):
        raise BuilderError(pgettext(_CTX, "Seçim %(n)s simvoldan uzun ola bilməz.") % {"n": OPTION_MAX_LENGTH})
    if len({label.casefold() for label in labels}) != len(labels):
        raise BuilderError(pgettext(_CTX, "Seçimlər təkrarlanmamalıdır."))
    existing = list(existing or [])
    if locked:
        if len(labels) != len(existing):
            raise BuilderError(pgettext(_CTX, "Cavab gəlmiş sualın seçim sayı dəyişmir."))
        if not all(_typo_ok(old.get("label"), new) for old, new in zip(existing, labels, strict=True)):
            raise _typo_error()
    keys = {item.get("key") for item in existing}
    choices = []
    for index, label in enumerate(labels):
        key = existing[index]["key"] if index < len(existing) and existing[index].get("key") else _new_key(keys)
        keys.add(key)
        choices.append({"key": key, "label": label})
    return choices


def _labels(data, prefix, count, existing, *, locked) -> list:
    values = [_text(data.get(f"{prefix}{index}"), 80, label=pgettext(_CTX, "Etiket")) for index in range(count)]
    if locked and not all(_typo_ok(old, new) for old, new in zip(existing or [""] * count, values, strict=False)):
        raise _typo_error()
    return values if any(values) else []


def _bounded_int(raw, low, high):
    raw = str(raw or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise BuilderError(pgettext(_CTX, "Minimum/maksimum seçim sayı tam ədəd olmalıdır.")) from exc
    if not low <= value <= high:
        raise BuilderError(pgettext(_CTX, "Minimum/maksimum seçim sayı seçimlərin sayına uyğun olmalıdır."))
    return value


def _default_choices() -> str:
    return "\n".join(pgettext(_CTX, "Variant %(n)s") % {"n": index} for index in (1, 2))


def build_options(kind, data, existing, *, locked) -> dict:
    existing = existing if isinstance(existing, dict) else {}
    if kind in (QuestionKind.SINGLE, QuestionKind.MULTI):
        raw = data.get("choices_text")
        if raw is None and not existing:
            raw = _default_choices()  # yeni sual — iki nümunə variantı, sonra redaktə olunur
        options = {"choices": parse_choices(raw, existing.get("choices"), locked=locked)}
        if kind == QuestionKind.MULTI:
            if locked:  # həddlər strukturdur — formada söndürülüb, köhnə dəyər qalır
                options.update({"min": existing.get("min"), "max": existing.get("max")})
                return options
            total = len(options["choices"])
            low = _bounded_int(data.get("min_choices"), 0, total)
            high = _bounded_int(data.get("max_choices"), 1, total)
            if low is not None and high is not None and low > high:
                raise BuilderError(pgettext(_CTX, "Minimum seçim sayı maksimumdan böyük ola bilməz."))
            options.update({"min": low, "max": high})
        return options
    if kind == QuestionKind.LIKERT5:
        labels = _labels(data, "label_", 5, existing.get("labels"), locked=locked)
        return {"labels": labels} if labels else {}
    if kind == QuestionKind.NPS:
        anchors = _labels(data, "anchor_", 2, existing.get("anchors"), locked=locked)
        return {"anchors": anchors} if anchors else {}
    return {}


# ── Sual əməliyyatları ──────────────────────────────────────────────────────


def _group_value(survey, data, question=None):
    """Müəllim dəsti: ``section`` (müəllim / ümumi); ümumi sorğu: ``page``."""
    if survey.is_teacher_evaluation:
        section = data.get("section") or (question.section if question else Section.TEACHER)
        if section not in Section.values:
            raise BuilderError(pgettext(_CTX, "Bölmə seçilməlidir."))
        return {"section": section, "page": None}
    raw = data.get("page") or (str(question.page_id) if question and question.page_id else "")
    page = SurveyPage.objects.filter(template_id=survey.template_id, pk=raw).first() if raw else None
    if page is None:
        page = SurveyPage.objects.filter(template_id=survey.template_id).order_by("-order").first()
    if page is None:
        page = SurveyPage.objects.create(organization_id=survey.organization_id, template_id=survey.template_id)
    return {"section": Section.GENERAL, "page": page}


def _new_code(template_id) -> str:
    existing = set(SurveyQuestion.objects.filter(template_id=template_id).values_list("code", flat=True))
    while True:
        code = f"q{secrets.token_hex(3)}"
        if code not in existing:
            return code


def add_question(survey, data, *, by_user=None, request=None) -> SurveyQuestion:
    with transaction.atomic():
        if is_locked(survey):
            raise BuilderError(pgettext(_CTX, "Cavab gəlmiş sorğuya sual əlavə etmək olmaz — dublikat yaradın."))
        template = survey.template
        if template.questions.count() >= MAX_QUESTIONS:
            raise BuilderError(pgettext(_CTX, "Sorğuda ən çoxu %(n)s sual ola bilər.") % {"n": MAX_QUESTIONS})
        kind = data.get("kind") or ""
        if kind not in allowed_kinds(survey):
            raise BuilderError(pgettext(_CTX, "Bu sorğu üçün sual növü uyğun deyil."))
        text = _text(data.get("text"), QUESTION_TEXT_MAX_LENGTH, required=True, label=pgettext(_CTX, "Sual"))
        group = _group_value(survey, data)
        top = template.questions.aggregate(top=Max("order"))["top"] or 0
        question = SurveyQuestion.objects.create(
            organization_id=survey.organization_id,
            template=template,
            code=_new_code(template.pk),
            kind=kind,
            text=text,
            help_text=_text(data.get("help_text"), HELP_TEXT_MAX_LENGTH, label=pgettext(_CTX, "İzah")),
            required=_flag(data, "required") if "required" in data else True,
            in_index=survey.is_teacher_evaluation and kind == QuestionKind.LIKERT5 and _flag(data, "in_index"),
            order=top + 10,
            options=build_options(kind, data, {}, locked=False),
            **group,
        )
        audit(survey, by_user=by_user, action="question_add", changes={"code": question.code}, request=request)
    return question


def update_question(survey, question, data, *, by_user=None, request=None) -> SurveyQuestion:
    with transaction.atomic():
        question = SurveyQuestion.objects.select_for_update().get(pk=question.pk, template_id=survey.template_id)
        locked = is_locked(survey)
        text = _text(data.get("text"), QUESTION_TEXT_MAX_LENGTH, required=True, label=pgettext(_CTX, "Sual"))
        help_text = _text(data.get("help_text"), HELP_TEXT_MAX_LENGTH, label=pgettext(_CTX, "İzah"))
        if locked:
            # Struktur sahələri (növ, məcburilik, indeks, bölmə) kilidlidir — formada söndürülüb;
            # göndərilsə belə NƏZƏRƏ ALINMIR, köhnə dəyər qalır.
            kind, required, in_index = question.kind, question.required, question.in_index
            group = {"section": question.section, "page": question.page}
        else:
            kind = data.get("kind") or question.kind
            if kind not in allowed_kinds(survey):
                raise BuilderError(pgettext(_CTX, "Bu sorğu üçün sual növü uyğun deyil."))
            required = _flag(data, "required")
            in_index = survey.is_teacher_evaluation and kind == QuestionKind.LIKERT5 and _flag(data, "in_index")
            group = _group_value(survey, data, question)
        same_family = kind == question.kind or (kind in CHOICE_KINDS and question.kind in CHOICE_KINDS)
        options = build_options(kind, data, question.options if same_family else {}, locked=locked)
        if locked:
            if not (_typo_ok(question.text, text) and _typo_ok(question.help_text, help_text)):
                raise _typo_error()
            if (text, help_text, options) != (question.text, question.help_text, question.options):
                question.history = [
                    *(question.history or []),
                    {
                        "at": timezone.now().isoformat(),
                        "by": getattr(by_user, "pk", None),
                        "text": question.text,
                        "help": question.help_text,
                        "options": question.options,
                    },
                ]
        question.text, question.help_text, question.kind = text, help_text, kind
        question.required, question.in_index, question.options = required, in_index, options
        question.section, question.page = group["section"], group["page"]
        question.save()
        audit(
            survey,
            by_user=by_user,
            action="question_edit_locked" if locked else "question_edit",
            changes={"code": question.code},
            request=request,
        )
    return question


def delete_question(survey, question, *, by_user=None, request=None) -> None:
    with transaction.atomic():
        if is_locked(survey):
            raise BuilderError(pgettext(_CTX, "Cavab gəlmiş sorğudan sual silinmir."))
        SurveyQuestion.objects.filter(pk=question.pk, template_id=survey.template_id).delete()
        audit(survey, by_user=by_user, action="question_delete", changes={"code": question.code}, request=request)


def _group_queryset(survey, group_key):
    queryset = SurveyQuestion.objects.filter(template_id=survey.template_id)
    if survey.is_teacher_evaluation:
        return queryset.filter(section=group_key)
    return queryset.filter(page_id=group_key or None)


def reorder(survey, group_key, ordered_ids, *, by_user=None, request=None) -> None:
    """Bir qrupun (bölmə / səhifə) suallarının tam sırası — ``ordered_ids`` qrupu TAM əhatə etməlidir."""
    with transaction.atomic():
        if is_locked(survey):
            raise BuilderError(pgettext(_CTX, "Cavab gəlmiş sorğuda sualların sırası dəyişmir."))
        rows = list(_group_queryset(survey, group_key).order_by("order", "code"))
        by_id = {str(row.pk): row for row in rows}
        ordered = [str(pk) for pk in ordered_ids]
        if sorted(ordered) != sorted(by_id):
            raise BuilderError(pgettext(_CTX, "Sıra köhnəlib — səhifəni yeniləyin."))
        base = min((row.order for row in rows), default=0)
        for index, pk in enumerate(ordered):
            by_id[pk].order = base + index
        SurveyQuestion.objects.bulk_update(rows, ["order"])
        _renumber(survey)
        audit(survey, by_user=by_user, action="question_reorder", request=request)


def move(survey, question, direction, *, by_user=None, request=None) -> None:
    """Klaviatura / düymə ilə bir addım yuxarı-aşağı (qrup daxilində)."""
    group_key = question.section if survey.is_teacher_evaluation else (str(question.page_id or "") or None)
    ids = [str(pk) for pk in _group_queryset(survey, group_key).order_by("order", "code").values_list("pk", flat=True)]
    index = ids.index(str(question.pk))
    target = index - 1 if direction == "up" else index + 1
    if 0 <= target < len(ids):
        ids[index], ids[target] = ids[target], ids[index]
        reorder(survey, group_key, ids, by_user=by_user, request=request)


def _renumber(survey) -> None:
    """Qlobal sıra: səhifə sırası → qrup daxilində sıra (10-luq addımla, boşluqsuz)."""
    queryset = SurveyQuestion.objects.filter(template_id=survey.template_id)
    if survey.is_teacher_evaluation:
        rows = sorted(queryset, key=lambda q: (q.section != Section.TEACHER, q.order, q.code))
    else:
        rows = list(queryset.order_by("page__order", "page_id", "order", "code"))
    for index, row in enumerate(rows):
        row.order = (index + 1) * 10
    SurveyQuestion.objects.bulk_update(rows, ["order"])


# ── Bölmələr (ümumi sorğu) ──────────────────────────────────────────────────


def add_page(survey, data, *, by_user=None, request=None) -> SurveyPage:
    if survey.is_teacher_evaluation:
        raise BuilderError(pgettext(_CTX, "Müəllim qiymətləndirməsinin bölmələri sabitdir."))
    with transaction.atomic():
        if is_locked(survey):
            raise BuilderError(pgettext(_CTX, "Cavab gəlmiş sorğuya bölmə əlavə etmək olmaz."))
        pages = SurveyPage.objects.filter(template_id=survey.template_id)
        if pages.count() >= MAX_PAGES:
            raise BuilderError(pgettext(_CTX, "Ən çoxu %(n)s bölmə ola bilər.") % {"n": MAX_PAGES})
        top = pages.aggregate(top=Max("order"))["top"] or 0
        page = SurveyPage.objects.create(
            organization_id=survey.organization_id,
            template_id=survey.template_id,
            title=_text(data.get("title"), TITLE_MAX_LENGTH, label=pgettext(_CTX, "Bölmə adı")),
            description=_text(data.get("description"), 1000, label=pgettext(_CTX, "İzah")),
            order=top + 10,
        )
        audit(survey, by_user=by_user, action="page_add", request=request)
    return page


def update_page(survey, page, data, *, by_user=None, request=None) -> SurveyPage:
    with transaction.atomic():
        page = SurveyPage.objects.select_for_update().get(pk=page.pk, template_id=survey.template_id)
        title = _text(data.get("title"), TITLE_MAX_LENGTH, label=pgettext(_CTX, "Bölmə adı"))
        description = _text(data.get("description"), 1000, label=pgettext(_CTX, "İzah"))
        if is_locked(survey) and not (_typo_ok(page.title, title) and _typo_ok(page.description, description)):
            raise _typo_error()
        page.title, page.description = title, description
        page.save(update_fields=["title", "description"])
        audit(survey, by_user=by_user, action="page_edit", request=request)
    return page


def delete_page(survey, page, *, by_user=None, request=None) -> None:
    """Bölmə silinir, sualları qonşu bölməyə keçir (sual itmir). Tək bölmə silinmir."""
    with transaction.atomic():
        if is_locked(survey):
            raise BuilderError(pgettext(_CTX, "Cavab gəlmiş sorğudan bölmə silinmir."))
        pages = list(SurveyPage.objects.filter(template_id=survey.template_id).order_by("order", "id"))
        if len(pages) <= 1:
            raise BuilderError(pgettext(_CTX, "Sorğuda ən azı bir bölmə qalmalıdır."))
        index = next(i for i, row in enumerate(pages) if row.pk == page.pk)
        target = pages[index - 1] if index > 0 else pages[1]
        SurveyQuestion.objects.filter(page_id=page.pk).update(page=target)
        SurveyPage.objects.filter(pk=page.pk).delete()
        _renumber(survey)
        audit(survey, by_user=by_user, action="page_delete", request=request)


def move_page(survey, page, direction, *, by_user=None, request=None) -> None:
    with transaction.atomic():
        if is_locked(survey):
            raise BuilderError(pgettext(_CTX, "Cavab gəlmiş sorğuda bölmələrin sırası dəyişmir."))
        pages = list(SurveyPage.objects.filter(template_id=survey.template_id).order_by("order", "id"))
        index = next(i for i, row in enumerate(pages) if row.pk == page.pk)
        target = index - 1 if direction == "up" else index + 1
        if not 0 <= target < len(pages):
            return
        pages[index], pages[target] = pages[target], pages[index]
        for position, row in enumerate(pages):
            row.order = (position + 1) * 10
        SurveyPage.objects.bulk_update(pages, ["order"])
        _renumber(survey)
        audit(survey, by_user=by_user, action="page_move", request=request)
