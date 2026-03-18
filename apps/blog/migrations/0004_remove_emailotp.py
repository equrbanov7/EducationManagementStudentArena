from django.db import migrations


class Migration(migrations.Migration):
    """
    Remove EmailOTP from the blog app state.

    The actual database table was already renamed by accounts migration 0009.
    This migration only updates Django's migration state.
    """

    dependencies = [
        ("accounts", "0009_emailotp"),
        ("blog", "0003_hash_email_otp_codes"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="EmailOTP"),
            ],
            database_operations=[],
        ),
    ]
