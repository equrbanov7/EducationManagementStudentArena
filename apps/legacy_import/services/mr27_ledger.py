"""MR27 yeni mənbə açarları üçün mövcud immutable ledger müqaviləsi."""

from . import ledger
from .mr27_plan import RecoveryError
from .rehearsal_authorizer import build_rehearsal_authorizer, build_target_validators


class SourceLedger:
    def __init__(self, org, actor, sha, size):
        self.org, self.actor = org, actor
        self.authorize = build_rehearsal_authorizer()
        self.validators = build_target_validators()
        self.run = ledger.create_run(
            actor=actor,
            authorize=self.authorize,
            organization=org,
            source_system="myedu_mariadb",
            snapshot_sha256=sha,
            snapshot_size_bytes=size,
            source_row_count=4,
            schema_version="mr27-source-v1",
            transform_version="mr27-recovery-v1",
            mode="cutover",
            origin="command",
        )
        ledger.start_run(run_id=self.run.pk, actor=actor, authorize=self.authorize)

    def mapped(self, kind, key):
        from apps.legacy_import.models import LegacyEntityMap

        row = LegacyEntityMap.objects.filter(
            organization=self.org, source_system="myedu_mariadb", entity_type=kind, legacy_pk=str(key)
        ).first()
        if row is None:
            return None
        if row.state != "migrated":
            raise RecoveryError("legacy_mapping_conflict")
        return row.target_pk

    def bind(self, kind, key, obj, row_hash):
        ledger.upsert_entity_map(
            run_id=self.run.pk,
            actor=self.actor,
            authorize=self.authorize,
            entity_type=kind,
            legacy_pk=str(key),
            source_row_hash=row_hash,
            state="migrated",
            target_model_label=obj._meta.label_lower,
            target_pk=str(obj.pk),
            target_validators=self.validators,
        )

    def finish(self):
        ledger.finish_run(run_id=self.run.pk, actor=self.actor, authorize=self.authorize, outcome="succeeded")
