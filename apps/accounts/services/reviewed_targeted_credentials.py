"""Exact request-backed pending accounts only; encrypted in-memory CSV, atomic issuance."""

import hashlib
import io
import json
import os
from pathlib import Path

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction

from core.encrypted_export import encrypt_export
from core.export_safety import safe_csv_writer

from ..management.commands.issue_staff_credentials import Command as Issuer

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
FINGERPRINT = "f21b002d94fdd65fb346e557e6eb85109f60bda3afa8d8c5a2a14e4b9fc922bf"
STAFF = [
    (8396, "jale.heyderova", "Jalə", "Heydərova", "Aydın"),
    (8151, "vusal.heyderov", "Vüsal", "Heydərov", "Sədrəddin"),
    (8311, "ibrahim.yaqublu2", "Ibrahim", "Yaqublu", "Mail"),
    (9554, "elnur.islamov", "Elnur", "İslamov", "İlham"),
    (11620, "nigar.haciyeva2", "Nigar", "Hacıyeva", "Elman"),
    (8096, "gunel.velizade", "Günel", "Vəlizadə", "Rauf"),
    (11608, "solmaz.memmedova3", "Solmaz", "Məmmədova", "Sərdar"),
]
STUDENTS = [
    (12030, "fatime.eliyeva3", "Fatimə", "Əliyeva", "Allahverdi", "10127"),
    (12031, "reqsane.ceferli", "Rəqsanə", "Cəfərli", "Ruslan", "10128"),
]
BATCHES = {
    "staff-seven": STAFF,
    "magistr-two": STUDENTS,
    "behruz-one": [(7363, "behruz.quluzade", "Bəhruz", "Quluzadə", "Kərim", "9622")],
}


def require(condition):
    if not condition:
        raise ValueError("targeted_credentials_guard_failed")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _snapshot(batch, organization):
    require(batch in BATCHES)
    result, eligible = [], []
    User = get_user_model()
    Profile = apps.get_model("accounts.UserProfile")
    Membership = apps.get_model("organizations.Membership")
    for expected in BATCHES[batch]:
        pk, username, first, last, patronymic, *code = expected
        user = User.objects.select_for_update(of=("self",)).get(username=username)
        profile = Profile.objects.select_for_update().get(user=user)
        require((pk is None or user.pk == pk) and str(profile.organization_id) == str(organization.pk))
        require((user.first_name, user.last_name, profile.patronymic) == (first, last, patronymic))
        academic = []
        if code:
            require(str(profile.institutional_identifier) == code[0])
            academic = list(
                apps.get_model("registrar.StudentAcademicRecord")
                .objects.select_for_update(of=("self",))
                .filter(student=user, organization=organization)
                .order_by("pk")
                .values(
                    "id",
                    "status",
                    "group_id",
                    "group__name",
                    "program_id",
                    "program__name",
                    "program__degree_level",
                    "curriculum_id",
                    "admission_year",
                )
            )
            require(len(academic) == 1 and academic[0]["group__name"] is not None)
            record = academic[0]
            if batch == "behruz-one":
                require(
                    record["status"] == "academic_leave"
                    and record["group__name"].replace(" ", "").replace("İ", "I").casefold() == "404/5iht"
                    and record["program__name"] == "İqtisadiyyatın tənzimlənməsi"
                )
            else:
                require(
                    record["status"] == "enrolled"
                    and record["group__name"].replace(" ", "") == "510/6BİEO"
                    and record["program__degree_level"] == "master"
                )
        memberships = list(
            Membership.objects.select_for_update()
            .filter(user=user, organization=organization)
            .order_by("pk")
            .values("id", "role_id", "role__name", "role__is_active", "is_active", "scope_unit_id")
        )
        roles = {m["role__name"] for m in memberships if m["is_active"] and m["role__is_active"]}
        permitted = bool(roles & ({"student", "lead_student"} if code else {"teacher", "assistant"}))
        safe = (
            user.is_active
            and not user.is_superuser
            and not user.is_staff
            and profile.access_state == "active"
            and not profile.is_deleted
            and profile.blocked_at is None
            and permitted
        )
        pending = not (profile.email_verified and not profile.password_change_required)
        reason = "eligible" if safe and pending else "activated" if safe else "inactive_or_scope"
        result.append(
            dict(
                user_id=user.pk,
                username=username,
                password=user.password,
                first_name=user.first_name,
                last_name=user.last_name,
                patronymic=profile.patronymic,
                access_state=profile.access_state,
                deleted=profile.is_deleted,
                blocked=profile.blocked_at,
                active=user.is_active,
                staff=user.is_staff,
                superuser=user.is_superuser,
                verified=profile.email_verified,
                required=profile.password_change_required,
                memberships=memberships,
                academic=academic,
                reason=reason,
            )
        )
        if reason == "eligible":
            eligible.append(
                dict(user_id=user.pk, username=username, full_name=" ".join((first, last, patronymic)), faculty="")
            )
    return result, eligible


@transaction.atomic
def issue(*, organization, actor, batch, apply=False, baseline="", public_key="", output=""):
    require(str(organization.pk) == ORG and organization.is_active and type(apply) is bool)
    profile = apps.get_model("accounts.UserProfile").objects.select_for_update().get(user=actor)
    require(
        actor.is_active
        and actor.is_superuser
        and str(profile.organization_id) == ORG
        and profile.access_state == "active"
        and not profile.is_deleted
        and profile.blocked_at is None
    )
    state, targets = _snapshot(batch, organization)
    before = digest({"batch": batch, "state": state})
    result = dict(
        status="dry_run",
        baseline=before,
        requested=len(state),
        eligible=len(targets),
        skipped=len(state) - len(targets),
        issued=0,
        encrypted_sha256="none",
        academic_review_required=int(batch == "behruz-one"),
    )
    if not apply:
        return result
    require(baseline == before and bool(public_key) and bool(output))
    # Validate pinned recipient BEFORE changing credentials, then lock-protected native issuer.
    key = Path(public_key).read_bytes()
    encrypt_export({}, key, fingerprint=FINGERPRINT)
    issued = Issuer()._issue(
        organization,
        targets,
        "Explicit request-backed pending-only initial credentials",
        verb="reviewed_targeted_credentials",
    )
    require(len(issued) == len(targets))
    stream = io.StringIO(newline="")
    writer = safe_csv_writer(stream)
    writer.writerow(["ad_soyad_ata_adi", "username", "ilkin_parol"])
    writer.writerows((row["full_name"], row["username"], row["password"]) for row in issued)
    payload = {"format": "wcu-targeted-credentials/1", "batch": batch, "baseline": before, "csv": stream.getvalue()}
    encoded = json.dumps(encrypt_export(payload, key, fingerprint=FINGERPRINT), sort_keys=True).encode()
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as target:
        target.write(encoded)
    result.update(status="applied", issued=len(issued), encrypted_sha256=hashlib.sha256(encoded).hexdigest())
    return result
