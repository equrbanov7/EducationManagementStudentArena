"""Data auditi 2026-09-13 §6.2 (W2 2026-09-14) — `accounts_userprofile` dublikat indeksləri.

`role` (`db_index=True`) və `requested_organization` (FK) üçün Django onsuz da
`accounts_userprofile_role_f557a06b` / `accounts_userprofile_requested_organization_id_14043874`
indekslərini yaradır; `Meta.indexes`-dəki `accounts_us_role_e16858_idx` və
`accounts_us_request_9a72ac_idx` eyni açarın təkrarı idi (hər yazıda əlavə xərc).
`CONCURRENTLY` → `atomic = False`.
"""

from django.contrib.postgres.operations import RemoveIndexConcurrently
from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("accounts", "0022_evidence_reason_student_reinstatement"),
    ]

    operations = [
        RemoveIndexConcurrently(model_name="userprofile", name="accounts_us_role_e16858_idx"),
        RemoveIndexConcurrently(model_name="userprofile", name="accounts_us_request_9a72ac_idx"),
    ]
