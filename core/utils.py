"""
Core utility functions for EMS Arena project.
Reusable helper functions used across the application.
"""

import random
import string

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags


def generate_otp(length=6):
    """
    Generate a random OTP (One-Time Password) of specified length.
    """
    return "".join(random.choices(string.digits, k=length))


def generate_pin(length=4):
    """
    Generate a random PIN of specified length.
    """
    return "".join(random.choices(string.digits, k=length))


def generate_code(length=8):
    """
    Generate a random alphanumeric code of specified length.
    """
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def send_template_email(
    subject, template_name, context, recipient_list, from_email=None
):
    """
    Send an email using a template.

    Args:
        subject: Email subject
        template_name: Path to email template
        context: Context dictionary for template rendering
        recipient_list: List of recipient email addresses
        from_email: Sender email (optional)
    """
    html_message = render_to_string(template_name, context)
    plain_message = strip_tags(html_message)

    send_mail(
        subject=subject,
        message=plain_message,
        from_email=from_email,
        recipient_list=recipient_list,
        html_message=html_message,
        fail_silently=False,
    )
