from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        (
            "contact",
            "0002_rename_contact_con_created_idx_contact_con_created_00b9df_idx_and_more",
        ),
        ("contact", "0002_reply_fields"),
    ]

    operations = []
