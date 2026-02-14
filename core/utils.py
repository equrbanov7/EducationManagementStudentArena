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


def send_template_email(subject, template_name, context, recipient_list, from_email=None):
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


def generate_unique_slug(model_class, title, slug_field="slug"):
    """
    Generate a unique slug for a model instance.

    Args:
        model_class: The model class to check uniqueness against
        title: The title/name to slugify
        slug_field: Name of the slug field (default: 'slug')

    Returns:
        A unique slug string
    """
    from django.utils.text import slugify

    base_slug = slugify(title)
    slug = base_slug
    counter = 1

    # Check if slug exists
    filter_kwargs = {slug_field: slug}
    while model_class.objects.filter(**filter_kwargs).exists():
        slug = f"{base_slug}-{counter}"
        filter_kwargs = {slug_field: slug}
        counter += 1

    return slug


def get_client_ip(request):
    """
    Get the client's IP address from the request.

    Args:
        request: Django HttpRequest object

    Returns:
        IP address as a string
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip
