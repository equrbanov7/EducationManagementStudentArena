import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Move EmailOTP from the blog app to the accounts app.

    The database table is renamed from blog_emailotp to accounts_emailotp;
    only the migration state is updated in the blog app (see blog 0004).
    """

    dependencies = [
        ("accounts", "0008_userprofile_requested_organization_message"),
        ("blog", "0003_hash_email_otp_codes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="EmailOTP",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("code", models.CharField(max_length=128)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("expires_at", models.DateTimeField()),
                        ("is_used", models.BooleanField(default=False)),
                        (
                            "user",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="email_otps",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Email OTP",
                        "verbose_name_plural": "Email OTPs",
                    },
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    "ALTER TABLE blog_emailotp RENAME TO accounts_emailotp;",
                    reverse_sql="ALTER TABLE accounts_emailotp RENAME TO blog_emailotp;",
                ),
            ],
        ),
    ]
