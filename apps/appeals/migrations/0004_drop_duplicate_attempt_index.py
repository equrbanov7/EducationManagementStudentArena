"""Data auditi 2026-09-13 §6.2 (W2 2026-09-14) — `appeals_scoreadjustment` dublikat indeksi.

`score_adj_attempt_idx` `attempt` FK-nın avtomatik indeksi
(`appeals_scoreadjustment_attempt_id_d1d212f5`) ilə eyni açarda idi.
`CONCURRENTLY` → `atomic = False`.
"""

from django.contrib.postgres.operations import RemoveIndexConcurrently
from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("appeals", "0003_alter_appeal_status_alter_appealitem_appeal_type_and_more"),
    ]

    operations = [
        RemoveIndexConcurrently(model_name="scoreadjustment", name="score_adj_attempt_idx"),
    ]
