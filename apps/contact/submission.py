"""A public form can be retried. Each new form gets its own session-bound receipt."""

from uuid import UUID, uuid4

from django.core.signing import BadSignature, Signer

from .models import ContactMessage


def receipt_signer(request):
    owner = request.session.get("contact_form_owner")
    if not owner:
        owner = uuid4().hex
        request.session["contact_form_owner"] = owner
    return Signer(salt=f"contact.form.{owner}")


def receipt_key(signer, token):
    try:
        return UUID(signer.unsign(token))
    except (BadSignature, ValueError):
        return None


def received(key):
    return key is not None and ContactMessage.objects.filter(submission_key=key).exists()
