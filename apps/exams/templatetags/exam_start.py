"""``{% exam_start_intent exam %}`` — «Başla» linkləri üçün başlatma niyyəti tokeni (EXAMQA R1, 2026-10-01).

İstifadə: ``href="{% url 'exams:start_exam' exam.slug %}?si={% exam_start_intent exam %}"``.
Bax ``apps/exams/services/start_intent.py``.
"""

from django import template

from apps.exams.services.start_intent import start_intent_token

register = template.Library()


@register.simple_tag(takes_context=True)
def exam_start_intent(context, exam):
    request = context.get("request")
    user = getattr(request, "user", None)
    if exam is None or user is None or not getattr(user, "is_authenticated", False):
        return ""
    return start_intent_token(user.pk, exam.pk)
