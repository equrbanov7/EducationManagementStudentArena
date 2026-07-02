"""Admin OTP əməliyyatları üçün hook registry (shared kernel).

M3 (2026-07-02, AGENTS §5 pattern 3): core/admin_auth və core/admin_site
`apps.accounts.services`-dəki OTP funksiyalarını birbaşa import edirdi —
core→accounts kənarı. İndi accounts implementasiyaları
`AccountsConfig.ready()`-də bura qeyd edir; core accounts-u tanımır.

Default-lar FAIL-CLOSED-dur: qeydiyyat olmadan admin 2FA axını açıq
RuntimeError verir (səssiz keçid təhlükəsizlik riski olardı).
"""


def _unregistered(name):
    def _fail(*args, **kwargs):
        raise RuntimeError(
            f"core.auth_otp: {name!r} hook-u qeydiyyatsızdır — " "apps.accounts quraşdırılıb ready() işləməlidir."
        )

    return _fail


_HOOKS = {
    "issue_email_otp": _unregistered("issue_email_otp"),
    "verify_otp_code": _unregistered("verify_otp_code"),
}


def register(name, fn):
    """Hook implementasiyasını qeyd et (naməlum ad üçün KeyError)."""
    if name not in _HOOKS:
        raise KeyError(f"Naməlum auth_otp hook: {name!r}")
    _HOOKS[name] = fn


def issue_email_otp(user, *, purpose):
    """OTP yaradıb e-poçt kodunu qaytarır → (code, expires_at, otp)."""
    return _HOOKS["issue_email_otp"](user, purpose=purpose)


def verify_otp_code(user, *, code, purpose):
    """OTP kodunu yoxlayır → (success, otp)."""
    return _HOOKS["verify_otp_code"](user, code=code, purpose=purpose)
