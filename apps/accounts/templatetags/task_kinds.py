"""``{% task_kind_visibility as tkv %}`` — kurs sistemi tapşırıq növlərinin görünüşü.

2026-10-13 (rol auditi B12): «Sərbəst iş» / «Kurs işi» tabları və filtr seçimləri RİM tənzimləməsi
(``academic.selfwork_enabled`` / ``academic.coursework_enabled``) söndürüləndə şablonlarda göstərilmir.
Qərar ``apps.accounts.views._helpers.task_kind_visibility``-dədir — kolleksiyaçılar da eyni funksiyanı
oxuyur ki, tab ilə sətirlər ayrılmasın.
"""

from django import template

from apps.accounts.views._helpers.task_kind_visibility import task_kind_visibility as _task_kind_visibility

register = template.Library()


@register.simple_tag
def task_kind_visibility():
    return _task_kind_visibility()
