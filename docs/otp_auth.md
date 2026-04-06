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

## Example Usage

Send login OTP:

```bash
curl -X POST http://127.0.0.1:8000/send-otp/ \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "email=user@example.com&purpose=login"
```

Verify login OTP:

```bash
curl -X POST http://127.0.0.1:8000/verify-otp/ \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "email=user@example.com&otp=123456&purpose=login"
```

Resend OTP:

```bash
curl -X POST http://127.0.0.1:8000/resend-otp/ \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "email=user@example.com&purpose=login"
```

Signup verification continues to work through the existing registration flow:

1. `POST /accounts/register/`
2. Signup data is held in server-side cache until verification
3. OTP email is sent automatically
4. User confirms on `/accounts/verify-code/`
5. User/profile/organization records are created only after successful OTP verification
