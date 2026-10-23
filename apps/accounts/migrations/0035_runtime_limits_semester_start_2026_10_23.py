"""Sahib 2026-10-23: 2026/2027 tədris ili başladı — giriş / OTP limitləri «Sistem tənzimləmələri»nin İCAZƏ VERDİYİ
ƏN YÜKSƏK dəyərlərə qaldırılır.

Sahib: «bütün universitet istifadə edəcək — OTP səhvlərini, eyni İP-dən bloklanmanı və s. hamısını maks elə ki,
ilkdir, heç kim bloklanmasın». Universitet Wi-Fi-ında yüzlərlə tələbə EYNİ İP-dən çıxır; ilk girişdə kod səhv
yazılır, «yenidən göndər» çox basılır. Dəyərlər ``core/runtime_settings.py`` spesifikasiyalarının ``max`` (say) və
ən qısa pəncərəsi (1 dəqiqə) — ``coerce`` onları qəbul edir. Hamısı «Sistem tənzimləmələri»ndə görünür və oradan
istənilən vaxt geri endirilə bilər. Geri miqrasiya 0028-in (2026-10-03) artırılmış dəyərlərini bərpa edir.
"""

from django.db import migrations

SEMESTER_START_MAXIMUMS = {
    "login.device_rate": "100/1m",
    "login.account_rate": "200/1m",
    "login.ip_rate": "5000/1m",
    "otp.expiry_minutes": 60,
    "otp.max_sends_per_hour": 50,
    "otp.resend_cooldown_seconds": 30,
    "otp.max_attempts": 20,
    "otp.resend_rate": "50/1m",
    "otp.verify_rate": "100/1m",
    "otp.send_ip_rate": "5000/1m",
    "otp.verify_ip_rate": "5000/1m",
}

#: 0028-in dəyərləri (geri qaytarma üçün); ``otp.resend_cooldown_seconds`` orada yox idi → sətir silinir (defolt).
PREVIOUS = {
    "login.device_rate": "10/10m",
    "login.account_rate": "40/60m",
    "login.ip_rate": "300/10m",
    "otp.expiry_minutes": 10,
    "otp.max_sends_per_hour": 10,
    "otp.max_attempts": 8,
    "otp.resend_rate": "6/10m",
    "otp.verify_rate": "10/10m",
    "otp.send_ip_rate": "150/10m",
    "otp.verify_ip_rate": "300/10m",
}


def _realign_sequence(schema_editor):
    """Serial sequence ``max(id)``-yə — miqrasiya round-trip testləri sequence-i 1-ə salır (yeni sətir toqquşmasın)."""
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "SELECT setval(pg_get_serial_sequence('accounts_runtimesetting', 'id'), "
        "GREATEST((SELECT COALESCE(MAX(id), 1) FROM accounts_runtimesetting), 1))"
    )


def raise_limits(apps, schema_editor):
    RuntimeSetting = apps.get_model("accounts", "RuntimeSetting")
    _realign_sequence(schema_editor)
    for key, value in SEMESTER_START_MAXIMUMS.items():
        RuntimeSetting.objects.update_or_create(key=key, defaults={"value": value})


def restore_limits(apps, schema_editor):
    RuntimeSetting = apps.get_model("accounts", "RuntimeSetting")
    _realign_sequence(schema_editor)
    for key in SEMESTER_START_MAXIMUMS:
        if key in PREVIOUS:
            RuntimeSetting.objects.update_or_create(key=key, defaults={"value": PREVIOUS[key]})
        else:
            RuntimeSetting.objects.filter(key=key).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0034_profile_username_changed_at"),
    ]

    operations = [
        migrations.RunPython(raise_limits, restore_limits),
    ]
