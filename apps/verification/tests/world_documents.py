"""Rəsmi sənəd buraxılışı (``transcript.issue``) testləri üçün ``world.build_world`` + şablon rolları.

Əlavə üzvlər (hamısı rol ŞABLONUNDAN — açarı şablon verir, test əl ilə vermir): Tədris şöbəsinin müdiri,
Tələbə xidmətləri, RİM rəhbəri (``*``), prorektor (köhnə ``course.edit`` yolu), F1-ə bağlı dekan və dekan
müavini. Tələbə «Elvin Qurbanov» F1/KE-101-dədir, «Nərmin Əliyeva» F2/KE-201-dədir.
"""

from __future__ import annotations

from django.urls import reverse

from apps.accounts.models import UserProfile
from core.rls import bypass_rls

from .world import _member, build_world, client_for

TEMPLATE_ISSUERS = ("teaching_office_head", "student_services", "ikt_rehber", "dean", "vice_dean")


def build_documents_world(slug: str) -> dict:
    world = build_world(slug)
    org, f1 = world["org"], world["f1"]
    with bypass_rls():
        world["to_head"] = _member(org, f"{slug}_tohead", "teaching_office_head")
        world["txm"] = _member(org, f"{slug}_txm", "student_services")
        world["rim"] = _member(org, f"{slug}_rim", "ikt_rehber")
        world["vrector"] = _member(org, f"{slug}_vrector", "vice_rector")
        world["dean"] = _member(org, f"{slug}_dean", "dean", unit=f1)
        world["vdean"] = _member(org, f"{slug}_vdean", "vice_dean", unit=f1)
        profile, _ = UserProfile.objects.get_or_create(user=world["student"])
        profile.patronymic = "Rauf"
        profile.gender = UserProfile.Gender.MALE
        profile.save(update_fields=["patronymic", "gender"])
    return world


def arayis_url(record) -> str:
    return reverse("registrar:student_enrollment_certificate_pdf", args=[record.id])


def transcript_url(record) -> str:
    return reverse("registrar:student_transcript_pdf", args=[record.id])


def post_arayis(world, user, *, record=None, place=""):
    client = client_for(world["org"], user)
    return client.post(arayis_url(record or world["record"]), {"place": place})


def get_transcript(world, user, *, record=None):
    client = client_for(world["org"], user)
    return client.get(transcript_url(record or world["record"]))


def pdf_text(payload: bytes) -> str:
    import fitz

    with fitz.open(stream=payload, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)
