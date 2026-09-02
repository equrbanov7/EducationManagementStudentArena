"""``accounts_accountrestoreevidence`` cədvəlini Django state-inə qeyd edir.

0018 cədvəli, trigger-lərini və ``SECURITY DEFINER`` yazma funksiyasını XAM SQL
ilə qurur, amma ONA UYĞUN MODEL yaratmır.  Nəticə: cədvəl
``introspection.django_table_names()``-də yoxdur, ``flush`` isə yalnız həmin
siyahını ``TRUNCATE`` edir — qeydiyyatsız cədvəlin
``organizations_organization``-a FK-si bütün əməliyyatı bloklayır:

    psycopg2.errors.FeatureNotSupported:
        cannot truncate a table referenced in a foreign key constraint
    → "Database test_… couldn't be flushed"
    → ardınca hər ``TransactionTestCase``-də duplicate key auth_user.

0013-dəki aktivasiya sübutu bu tələyə düşmür, çünki o, ``CreateModel`` ilə
yaradılıb.  Burada eyni nəticəni ALDIQ MİQRASİYAYA TOXUNMADAN alırıq: 0018
klondan tutmuş bütün mühitlərdə artıq tətbiq olunub, ona görə cədvəl SQL
səviyyəsində yenidən yaradılmır — yalnız state-ə əlavə olunur
(``SeparateDatabaseAndState``, ``database_operations=[]``).

Cədvəlin append-only təbiəti dəyişmir: trigger-lər və REVOKE-lar 0018-dədir,
burada heç bir DDL icra olunmur.  ``(organization_id, user_ref)`` indeksi də
0018-də qalır — adı Django-nun 30 simvolluq indeks-ad limitindən uzundur, ona
görə state-ə daxil edilmir (DB əməliyyatı olmadığından drift yaranmır).
"""

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0018_account_restore_evidence"),
        ("organizations", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="AccountRestoreEvidence",
                    fields=[
                        (
                            "id",
                            models.UUIDField(
                                default=uuid.uuid4,
                                editable=False,
                                primary_key=True,
                                serialize=False,
                            ),
                        ),
                        ("user_ref", models.CharField(editable=False, max_length=64)),
                        ("role_ref", models.CharField(editable=False, max_length=64)),
                        ("actor_ref", models.CharField(editable=False, max_length=64)),
                        ("evidence_digest", models.CharField(editable=False, max_length=64)),
                        (
                            "reason_code",
                            models.CharField(
                                choices=[
                                    ("institution_registry_match", "Institution registry match"),
                                    ("manual_registry_verification", "Manual registry verification"),
                                    ("signed_authoritative_export", "Signed authoritative export"),
                                ],
                                editable=False,
                                max_length=64,
                            ),
                        ),
                        ("transaction_id", models.PositiveBigIntegerField(editable=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True, editable=False)),
                        ("consumed_at", models.DateTimeField(editable=False, null=True)),
                        (
                            "organization",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.PROTECT,
                                related_name="account_restore_evidence",
                                to="organizations.organization",
                            ),
                        ),
                    ],
                    options={
                        "ordering": ["-created_at"],
                    },
                ),
            ],
        ),
    ]
