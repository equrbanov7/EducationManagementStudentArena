from django import template

register = template.Library()

@register.simple_tag
def user_attempts(assignment, user):
    """İstifadəçinin cəhd sayını qaytarır"""
    return assignment.get_user_attempts(user)

@register.simple_tag
def can_submit(assignment, user):
    """İstifadəçi cavab verə bilərmi"""
    return assignment.can_user_submit(user)