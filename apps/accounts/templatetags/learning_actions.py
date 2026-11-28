"""Write controls for the current cabinet request."""

from django import template

from apps.accounts.services.learning_action_access import can_create_personal_course, can_create_personal_exam

register = template.Library()
register.simple_tag(can_create_personal_course)
register.simple_tag(can_create_personal_exam)
