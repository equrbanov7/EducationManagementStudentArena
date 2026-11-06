"""İmtahan dilinin seçimi — başlamazdan əvvəl MƏCBURİ, gözə çarpan addım (sahib 2026-11-06).

Sahib: «İmtahan başlayanda dil seçimi diqqəti çəkməlidir ki, tələbə «görmədim» deməsin» və «quiz-də dil
seçimi yoxdur, sonra «dil seç» xətası çıxır, amma tələbə seçə bilmir».

Kök səbəb: çoxdilli imtahanda dil yalnız «Mövcud imtahanlar» / kurs səhifəsi modalında seçilirdi.
Tələbənin əsas giriş yolu olan kabinet («Təyin olunmuş tapşırıqlar») modalında dil seçimi YOX idi, start
təsdiq səhifəsində də yox idi — server isə dili tapmayanda cəhd yaratmadan tələbəni siyahıya «dil seçin»
xəbərdarlığı ilə qaytarırdı; tələbənin dil seçə biləcəyi heç bir yer qalmırdı (quiz başlamırdı).

İndi dil tələb olunub gəlməyibsə tələbə HARADAN gəlməsindən asılı olmayaraq start təsdiq səhifəsinə düşür
və orada başlıqlı, nömrəli, məcburi dil addımı var (seçilməsə «Başla» keçmir, xəta vəziyyəti görünür).
AJAX (kod/PIN modalı) üçün JSON xəta qaytarılır — modal öz dil addımını göstərir. Tək dilli imtahanda
dil avtomatik seçilir və yalnız məlumat kimi göstərilir (:func:`new_attempt_language`).

:func:`new_attempt_language` HEÇ NƏ render etmir — start kilidi / tutum qapısı altında çağırılır və seçim
lazımdırsa :class:`LanguageChoiceRequired` qaldırır; səhifəni çağıran kilid buraxıldıqdan sonra qurur.
"""

from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import pgettext

from apps.exams.navigation import append_return_to, student_exams_home_url
from apps.exams.services.language_variants import available_language_options, resolve_requested_language

_CTX = "exams.language_step"
#: Kod/PIN yolu (``exam_code_check``) dil addımında yenidən göndərilən sahələr.
_CODE_FORWARD_FIELDS = ("exam_slug", "access_code", "next", "from_section", "assigned_type")


class LanguageChoiceRequired(Exception):
    """Çoxdilli imtahanda YENİ cəhd üçün dil gəlməyib — cəhd yaradılmır, tələbə dil addımını görür."""

    def __init__(self, language_options):
        super().__init__("language choice required")
        self.language_options = language_options


def new_attempt_language(request, exam):
    """YENİ cəhdin dili (və ya ``None`` — dil variantı yoxdur); seçim lazımdırsa ``LanguageChoiceRequired``.

    Tək dil avtomatik seçilir. POST-dakı dil köhnə query dilindən üstündür (dil addımı formu start URL-inə
    — əvvəlki ``?language=`` ilə birlikdə — göndərilir).
    """
    language_options = available_language_options(exam)
    if len(language_options) == 1:
        return language_options[0]["language"]
    if len(language_options) > 1:
        chosen = resolve_requested_language(exam, request.POST.get("language") or request.GET.get("language"))
        if chosen is None:
            raise LanguageChoiceRequired(language_options)
        return chosen
    return None


def language_choice_for_start(request, exam, pending, *, return_to=""):
    back_url = append_return_to(student_exams_home_url(request.user), return_to)
    return language_choice_response(request, exam, pending.language_options, back_url=back_url)


def language_required_message() -> str:
    return pgettext(_CTX, "İmtahana başlamaq üçün əvvəlcə imtahan dilini seçin.")


def language_step_options(language_options) -> list:
    """Şablon/JS üçün yığcam siyahı: ``[{"language", "label"}]``."""
    return [
        {"language": option["language"], "label": option.get("display_name") or option.get("label") or ""}
        for option in language_options
    ]


def language_step_context(request, language_options, *, chosen="") -> dict:
    """Start təsdiq səhifəsinin dil addımı konteksti (tək dil → yalnız məlumat)."""
    options = language_step_options(language_options)
    submitted = request.method == "POST" or "language" in request.GET
    return {
        "language_options": options,
        "language_required": len(options) > 1,
        "language_selected": chosen or "",
        # Tələbə formanı dilsiz (və ya mövcud olmayan dillə) göndəribsə — qırmızı xəta vəziyyəti.
        "language_error": language_required_message() if (len(options) > 1 and submitted and not chosen) else "",
    }


def _is_code_check(request) -> bool:
    match = getattr(request, "resolver_match", None)
    return bool(match and match.url_name == "exam_code_check")


def language_choice_response(request, exam, language_options, *, back_url=""):
    """Dil seçilməyib → cəhd yaradılmır; tələbə dil addımı olan təsdiq səhifəsini görür."""
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(
            {
                "success": False,
                "error": language_required_message(),
                "language_required": True,
                "language_options": language_step_options(language_options),
            },
            status=400,
        )
    context = {
        "exam": exam,
        "back_url": back_url or student_exams_home_url(request.user),
        "form_action": request.get_full_path(),
        "forward_fields": [],
        **language_step_context(request, language_options),
    }
    if _is_code_check(request):
        from django.urls import reverse

        context["form_action"] = reverse("exams:exam_code_check")
        context["forward_fields"] = [
            (name, request.POST.get(name, "")) for name in _CODE_FORWARD_FIELDS if request.POST.get(name)
        ]
    return render(request, "exams/student/exam_start_confirm.html", context)


__all__ = [
    "LanguageChoiceRequired",
    "language_choice_for_start",
    "language_choice_response",
    "language_required_message",
    "language_step_context",
    "language_step_options",
    "new_attempt_language",
]
