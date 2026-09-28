# EMSArena OTP Auth

This project now supports secure email OTP flows over Brevo SMTP.

## Environment

Use the variables in `.env.example`:

- `EMAIL_HOST=smtp-relay.brevo.com`
- `EMAIL_PORT=587`
- `EMAIL_USE_TLS=True`
- `BREVO_SMTP_LOGIN=your-brevo-smtp-login`
- `BREVO_EMAIL=no-reply@emsarena.com`
- `BREVO_FROM_EMAIL=no-reply@emsarena.com`
- `BREVO_SMTP_KEY=...`
- `BREVO_API_KEY=...` (optional HTTP fallback for contact replies when SMTP is unavailable)
- `DEFAULT_FROM_EMAIL=no-reply@emsarena.com`

`BREVO_SMTP_LOGIN` is the SMTP username Brevo expects for authentication. Keep
`BREVO_EMAIL` / `BREVO_FROM_EMAIL` as the visible sender address.

`EmailCampaignsApi` is for Brevo marketing campaigns. EMSArena OTP, login,
admin, and other system emails should continue to use Brevo transactional SMTP
with the settings above so delivery stays synchronous with the existing Django
email flow.

## OTP Rules

- OTP length: 6 digits
- Expiry: 5 minutes
- Resend cooldown: 60 seconds
- Max verification attempts per OTP: 5
- Max sends per email per hour: 5
- OTP is hashed before storage

## OTP flows (server-rendered pages only)

The standalone JSON endpoints `/send-otp/`, `/verify-otp/` and `/resend-otp/`
(also under `/accounts/`) were **removed on 2026-09-28** (audit SA-01/02):
`send-otp` (purpose=login) enumerated registered e-mails and mailed the victim,
and `verify-otp` (purpose=login) logged any account in with e-mail possession
only, skipping the password. They now return 404 (see `apps/accounts/tests/test_otp_api.py`).
OTP is only used inside the regular HTML flows (login second factor, registration
verification, password reset), which carry CSRF protection and per-flow state.

Signup verification continues to work through the existing registration flow:

1. `POST /accounts/register/`
2. Signup data is held in server-side cache until verification
3. OTP email is sent automatically
4. User confirms on `/accounts/verify-code/`
5. User/profile/organization records are created only after successful OTP verification
