"""Preserve question IDs and answers when repairing duplicate display numbers."""

from django.db import migrations, models

# The ledger contains only IDs and integers. Rollback restores precisely the
# repaired rows if their assigned numbers and blocks have not changed since.
_REPAIR = """
SET LOCAL app.bypass_rls = 'on';
LOCK TABLE labs_labquestion IN SHARE ROW EXCLUSIVE MODE;
CREATE TABLE labs_question_number_repair_0004 (
    question_id bigint PRIMARY KEY, block_id bigint NOT NULL,
    previous_number integer NOT NULL, assigned_number integer NOT NULL
);
WITH ranked AS (
    SELECT id, block_id, question_number,
           ROW_NUMBER() OVER (PARTITION BY block_id, question_number ORDER BY id) AS occurrence,
           MAX(question_number) OVER (PARTITION BY block_id) AS highest
    FROM labs_labquestion
)
INSERT INTO labs_question_number_repair_0004
SELECT id, block_id, question_number, highest + ROW_NUMBER() OVER (PARTITION BY block_id ORDER BY id)
FROM ranked WHERE occurrence > 1;
UPDATE labs_labquestion AS q SET question_number = repair.assigned_number
FROM labs_question_number_repair_0004 AS repair WHERE q.id = repair.question_id;
-- Only the schema migration needs the ledger. Ordinary tenant sessions
-- have no policy that would make these cross-tenant IDs visible.
ALTER TABLE labs_question_number_repair_0004 ENABLE ROW LEVEL SECURITY;
ALTER TABLE labs_question_number_repair_0004 FORCE ROW LEVEL SECURITY;
"""

_RESTORE = """
SET LOCAL app.bypass_rls = 'on';
ALTER TABLE labs_question_number_repair_0004 DISABLE ROW LEVEL SECURITY;
UPDATE labs_labquestion AS q SET question_number = repair.previous_number
FROM labs_question_number_repair_0004 AS repair
WHERE q.id = repair.question_id AND q.block_id = repair.block_id AND q.question_number = repair.assigned_number;
DROP TABLE labs_question_number_repair_0004;
"""


class Migration(migrations.Migration):
    dependencies = [("labs", "0003_retain_answered_questions")]
    operations = [
        migrations.RunSQL(_REPAIR, _RESTORE),
        migrations.AddConstraint(
            model_name="labquestion",
            constraint=models.UniqueConstraint(
                fields=("block", "question_number"), name="labs_question_block_number_uniq"
            ),
        ),
    ]
