"""Custom password hashers — tuned for exam-day mass-login CPU cost.

Django 5.2 ships PBKDF2 at 1,000,000 iterations (~150-300 ms of pure CPU per
`check_password`). During an exam-day login stampede (thousands of students in
one window) that turns into tens of CPU-cores of continuous PBKDF2 work,
starving every other request. We pin to the OWASP-2023 floor (600k) — still
compliant, ~40% cheaper. Old 1M-iteration hashes keep verifying and Django
transparently re-hashes each user on their next successful login (the iteration
count travels inside the stored hash), so there is no data migration/downtime.

For an even bigger win, add `argon2-cffi` to requirements and put
`django.contrib.auth.hashers.Argon2PasswordHasher` first instead — Argon2id is
faster than PBKDF2 at equivalent strength (needs an image rebuild + load test).
"""

from django.contrib.auth.hashers import PBKDF2PasswordHasher


class OWASPPBKDF2PasswordHasher(PBKDF2PasswordHasher):
    iterations = 600_000
