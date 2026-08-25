"""Drive an idempotent, resumable legacy identity rehearsal from the CLI."""

import argparse
import json
import os
import signal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.legacy_import.services.account_cutover import LegacyAccountCutoverError
from apps.legacy_import.services.field_contracts import LegacyFieldContractError
from apps.legacy_import.services.ledger import LegacyLedgerError
from apps.legacy_import.services.mariadb_gateway import MariaDBSourceGatewayError
from apps.legacy_import.services.pk_inventory import LegacyPKInventoryError
from apps.legacy_import.services.preflight import LegacySourcePreflightError
from apps.legacy_import.services.rehearsal_contracts import (
    DEFAULT_BATCH_ROWS,
    IDENTITY_COHORT_MAX_ROWS,
    MAX_BATCH_ROWS,
    EmailTrustPolicy,
    LegacyRehearsalError,
    RehearsalPolicy,
    StudentIdentifierPolicy,
    UsernamePolicy,
    load_rehearsal_phase_registry,
)
from apps.legacy_import.services.rehearsal_identity_phase import load_email_trust_manifest
from apps.legacy_import.services.rehearsal_orchestrator import cancel_rehearsal, execute_rehearsal, plan_rehearsal
from apps.legacy_import.services.source_attestation import LegacySourceAttestationError
from apps.legacy_import.services.source_extraction import MAX_SOURCE_CHUNK_SIZE, LegacySourceExtractionError
from apps.legacy_import.services.table_plan import LegacyTablePlanError
from apps.organizations.models import Organization
from core.management.command_safety import ProductionCommandSafetyMixin

MAX_SNAPSHOT_SIZE_BYTES = 1 << 42
REPORT_DIR_PARTS = ("docs", "migration", "reports")
# SPEC §14: the run stays RUNNING and the operator may resume it, so the shell
# must be able to tell an interruption apart from a fail-closed refusal.
RESUMABLE_CODES = frozenset(
    {
        "legacy_rehearsal_cancelled",
        "legacy_rehearsal_interrupted",
        "legacy_scope_busy",
        "legacy_mariadb_gateway_connection_failed",
        "legacy_source_fetch_failed",
        # open_audited_identity_stream wins a cancellation raised mid-stream.
        "legacy_source_extraction_cancelled",
    }
)
_SERVICE_ERRORS = (
    LegacyRehearsalError,
    MariaDBSourceGatewayError,
    LegacySourcePreflightError,
    LegacySourceAttestationError,
    LegacySourceExtractionError,
    LegacyPKInventoryError,
    LegacyTablePlanError,
    LegacyFieldContractError,
    LegacyAccountCutoverError,
    LegacyLedgerError,
)


def _bounded_integer(*, code: str, minimum: int, maximum: int):
    def parse(value: str) -> int:
        if not value.isascii() or not value.isdecimal():
            raise argparse.ArgumentTypeError(code)
        parsed = int(value, 10)
        if not minimum <= parsed <= maximum:
            raise argparse.ArgumentTypeError(code)
        return parsed

    return parse


class Command(ProductionCommandSafetyMixin, BaseCommand):
    help = "Drive an idempotent, resumable legacy identity rehearsal against a disposable target."
    safety_command_name = "legacy_import_rehearse"
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--mode", choices=("plan", "apply"), default="plan")
        parser.add_argument("--apply-confirm", default="")
        parser.add_argument("--organization-slug", required=True)
        parser.add_argument("--actor-username", required=True)
        parser.add_argument("--source", required=True)
        parser.add_argument(
            "--expected-size-bytes",
            required=True,
            type=_bounded_integer(
                code="legacy_rehearsal_source_size_invalid", minimum=1, maximum=MAX_SNAPSHOT_SIZE_BYTES
            ),
        )
        parser.add_argument(
            "--rehearsal-ordinal",
            type=_bounded_integer(code="legacy_rehearsal_ordinal_invalid", minimum=1, maximum=2),
        )
        parser.add_argument("--phase", action="append", default=[])
        parser.add_argument(
            "--batch-rows",
            default=DEFAULT_BATCH_ROWS,
            type=_bounded_integer(code="legacy_rehearsal_batch_rows_invalid", minimum=1, maximum=MAX_BATCH_ROWS),
        )
        parser.add_argument(
            "--source-chunk-size",
            default=DEFAULT_BATCH_ROWS,
            type=_bounded_integer(code="legacy_rehearsal_chunk_size_invalid", minimum=1, maximum=MAX_SOURCE_CHUNK_SIZE),
        )
        parser.add_argument("--username-policy", choices=("legacy_key",), default="legacy_key")
        parser.add_argument("--student-identifier-policy", choices=("legacy_pk",), default="legacy_pk")
        parser.add_argument("--email-trust-policy", choices=("deny_all", "evidence_manifest"), default="deny_all")
        parser.add_argument("--email-trust-manifest", default="")
        parser.add_argument(
            "--stage-contact-pending",
            action="store_true",
            help="Yalnız email_untrusted qaydalı contact-pending sətirləri də locked hesab kimi stage et.",
        )
        parser.add_argument(
            "--max-staged-accounts",
            default=0,
            type=_bounded_integer(
                code="legacy_rehearsal_staging_cap_invalid",
                minimum=0,
                maximum=IDENTITY_COHORT_MAX_ROWS,
            ),
        )
        parser.add_argument("--student-role-name", default="")
        parser.add_argument("--worker-role-name", default="")
        parser.add_argument("--resume-run-id", default="")
        parser.add_argument("--compare-report", default="")
        parser.add_argument("--report-dir", default="")
        parser.add_argument("--emit-report-only", action="store_true")
        parser.add_argument("--cancel-run", action="store_true")

    def handle(self, *args, **options):
        cancellation = {"requested": False}

        def request_cancellation(_signal_number, _frame):
            cancellation["requested"] = True

        installed = {}
        for signal_number in (signal.SIGINT, signal.SIGTERM):
            try:
                installed[signal_number] = signal.signal(signal_number, request_cancellation)
            except (OSError, ValueError):  # pragma: no cover - non-main thread
                pass
        try:
            payload = self._dispatch(options, lambda: cancellation["requested"])
        except _SERVICE_ERRORS as exc:
            code = getattr(exc, "code", "legacy_rehearsal_failed")
            raise CommandError(code, returncode=3 if code in RESUMABLE_CODES else 1) from None
        except CommandError:
            raise
        except Exception:
            raise CommandError("legacy_rehearsal_failed") from None
        finally:
            for signal_number, previous in installed.items():
                signal.signal(signal_number, previous)

        self.stdout.write(json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True))

    def _dispatch(self, options, cancellation_requested):
        organization = self._organization(options["organization_slug"])
        actor = self._actor(options["actor_username"])
        if options["cancel_run"]:
            outcome = cancel_rehearsal(
                settings_object=settings,
                organization=organization,
                actor=actor,
                run_id=self._required_run_id(options),
            )
            return outcome.payload

        manifest_digests, manifest_digest = self._email_trust_manifest(options)
        policy = RehearsalPolicy(
            phase_keys=tuple(options["phase"]) or tuple(phase.phase_key for phase in load_rehearsal_phase_registry()),
            username_policy=UsernamePolicy(options["username_policy"]),
            student_identifier_policy=StudentIdentifierPolicy(options["student_identifier_policy"]),
            email_trust_policy=EmailTrustPolicy(options["email_trust_policy"]),
            email_trust_manifest_digest=manifest_digest,
            batch_rows=options["batch_rows"],
            source_chunk_size=options["source_chunk_size"],
            max_staged_accounts=options["max_staged_accounts"],
            stage_contact_pending=bool(options.get("stage_contact_pending")),
            student_role_name=options["student_role_name"],
            worker_role_name=options["worker_role_name"],
        )
        if options["mode"] == "plan":
            return plan_rehearsal(
                settings_object=settings,
                policy=policy,
                organization=organization,
                actor=actor,
                source_path=options["source"],
                source_size_bytes=options["expected_size_bytes"],
            )

        ordinal = options.get("rehearsal_ordinal")
        if ordinal is None:
            raise CommandError("legacy_rehearsal_ordinal_invalid")
        outcome = execute_rehearsal(
            settings_object=settings,
            policy=policy,
            organization=organization,
            actor=actor,
            report_dir=options["report_dir"] or os.path.join(str(settings.BASE_DIR), *REPORT_DIR_PARTS),
            rehearsal_ordinal=ordinal,
            apply_confirmation=options["apply_confirm"],
            source_path=options["source"],
            source_size_bytes=options["expected_size_bytes"],
            resume_run_id=options["resume_run_id"] or None,
            compare_report_path=options["compare_report"],
            emit_report_only=options["emit_report_only"],
            email_trust_manifest_digests=manifest_digests,
            cancellation_requested=cancellation_requested,
            stdout_note=lambda _note: None,
        )
        if outcome.status not in ("succeeded", "planned"):
            raise CommandError(outcome.failure_code or "legacy_rehearsal_failed")
        return outcome.payload

    @staticmethod
    def _email_trust_manifest(options):
        if options["email_trust_policy"] != "evidence_manifest":
            if options["email_trust_manifest"]:
                raise CommandError("legacy_rehearsal_email_manifest_invalid")
            return frozenset(), ""
        return load_email_trust_manifest(options["email_trust_manifest"])

    @staticmethod
    def _required_run_id(options):
        if not options["resume_run_id"]:
            raise CommandError("legacy_rehearsal_resume_run_required")
        return options["resume_run_id"]

    @staticmethod
    def _organization(slug):
        organization = Organization.objects.filter(slug=slug, is_active=True, status="active").first()
        if organization is None:
            raise CommandError("legacy_rehearsal_organization_invalid")
        return organization

    @staticmethod
    def _actor(username):
        actor = get_user_model()._default_manager.filter(username=username, is_active=True).first()
        if actor is None:
            raise CommandError("legacy_rehearsal_actor_invalid")
        return actor
