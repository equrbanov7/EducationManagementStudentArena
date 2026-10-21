"""`ExamForm` — kateqoriyaya görə avtomatik sual sayı (sahib 2026-10-21).

Sahib: «Finalda 50 sualdır, midterm imtahanında 30 sual — bunu avtomatik sistem tənzimləsin, yəni midterm
seçərkən özü 30 sual gəlsin, yaddan çıxa bilər.» Dəyərlər «Sistem tənzimləmələri»ndədir
(``exam.final_question_count`` / ``exam.midterm_question_count``, ``core.runtime_settings_exam_center``).

Qayda (server — JS olmasa da işləyir):

* **Yeni imtahan.** Final/midterm seçilibsə və say boşdur və ya «avtomatik» dəyərlərdən biridir (yeni forma
  defoltu 50 ya digər kateqoriyanın sayı) → kateqoriyanın sayı yazılır. Başqa (əl ilə yazılmış) say saxlanır.
* **Redaktə.** Say SƏSSİZ dəyişdirilmir. Yalnız kateqoriya dəyişib, göndərilən say imtahanın saxlanmış sayına
  bərabərdir VƏ o say köhnə kateqoriyanın avtomatik sayıdır → yeni kateqoriyanın sayı (JS ilə eyni qayda).

Klient (``exam_create_edit_modal/toggles.js``): input-un ``data-qcount-*`` atributları — kateqoriya
dəyişəndə sahə yalnız son avtomatik doldurmadan bəri əl ilə dəyişdirilməyibsə yenilənir.
"""

from __future__ import annotations

from django.utils.translation import pgettext

#: Yeni imtahan formasının kateqoriyasız defoltu (əvvəlki sabit davranış).
NEW_EXAM_DEFAULT_COUNT = 50
_CTX = "exams.form.exam.help"


def category_counts() -> dict:
    from core.runtime_settings_exam_center import category_question_counts

    return category_question_counts()


def count_hint(category, counts) -> str:
    """Kateqoriyanın avtomatik say ipucu («Midterm üçün 30 sual (Sistem tənzimləmələri)») və ya boş."""
    count = counts.get(category or "")
    if count is None:
        return ""
    if category == "midterm":
        return pgettext(_CTX, "Midterm üçün %(count)s sual (Sistem tənzimləmələri)") % {"count": count}
    return pgettext(_CTX, "Final üçün %(count)s sual (Sistem tənzimləmələri)") % {"count": count}


def _new_exam_auto_values(counts) -> set:
    return {NEW_EXAM_DEFAULT_COUNT, *[value for value in counts.values() if value is not None]}


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def is_auto_value(value, *, instance, counts) -> bool:
    """Sahədəki say «avtomatik»dirmi (kateqoriya dəyişəndə yenilənə bilər)."""
    number = _as_int(value)
    if number is None:
        return value in (None, "")
    if getattr(instance, "pk", None):
        return number == counts.get(getattr(instance, "exam_type_extended", None) or "")
    return number in _new_exam_auto_values(counts)


def resolve_submitted_count(value, *, category, instance, counts):
    """Göndərilən sayı kateqoriyaya görə uyğunlaşdırır (yuxarıdakı qayda). ``value`` — təmizlənmiş say/None."""
    target = counts.get(category or "")
    if target is None:
        return value
    if not getattr(instance, "pk", None):
        if value in (None, "") or value in _new_exam_auto_values(counts) - {target}:
            return target
        return value
    old_category = getattr(instance, "exam_type_extended", None) or ""
    old_default = counts.get(old_category)
    if (
        old_category != category
        and old_default is not None
        and value == old_default
        and getattr(instance, "random_question_count", None) == old_default
    ):
        return target
    return value


def initial_count(category, counts) -> int:
    count = counts.get(category or "")
    return NEW_EXAM_DEFAULT_COUNT if count is None else count


def decorate_widget(form, counts) -> None:
    """Sual sayı input-una JS üçün ``data-qcount-*`` atributları + form üzərində ilkin ipucu."""
    field = form.fields.get("random_question_count")
    if field is None:
        return
    category_field = form["exam_type_extended"] if "exam_type_extended" in form.fields else None
    category = (category_field.value() if category_field is not None else "") or ""
    current = form["random_question_count"].value()
    attrs = {
        "data-qcount-final": str(counts.get("final") or ""),
        "data-qcount-midterm": str(counts.get("midterm") or ""),
        "data-qcount-hint-final": count_hint("final", counts),
        "data-qcount-hint-midterm": count_hint("midterm", counts),
    }
    if is_auto_value(current, instance=form.instance, counts=counts):
        attrs["data-qcount-auto"] = "" if current in (None, "") else str(current)
    field.widget.attrs.update(attrs)
    form.question_count_hint = count_hint(category, counts)


__all__ = [
    "NEW_EXAM_DEFAULT_COUNT",
    "category_counts",
    "count_hint",
    "decorate_widget",
    "initial_count",
    "is_auto_value",
    "resolve_submitted_count",
]
