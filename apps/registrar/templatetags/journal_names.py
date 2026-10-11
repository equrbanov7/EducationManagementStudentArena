"""``{{ row.student|journal_name }}`` — jurnal tablarında «Soyad Ad Ata adı»."""

from django import template

from apps.registrar.journal_names import journal_student_name

register = template.Library()


@register.filter(name="journal_name")
def journal_name(user):
    return journal_student_name(user)
