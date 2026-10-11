"""blog köməkçiləri.

Sahib 2026-10-10: köhnə qeydiyyat dublikatının köməkçiləri (``send_verify_email`` —
``accounts:verify_email_link``-ə link quran — və ``generate_otp``) çağıranı qalmadığı
üçün silindi; hesab OTP-ləri ``apps.accounts.services.auth``-dadır.
"""

# M2 (2026-07-02): tərif core-a köçüb; import səthi qorunur (AGENTS §1).
from core.constants import DATA_URL_PNG_RE  # noqa: F401
