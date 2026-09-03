"""CI E2E seed kanalı — production profili + komanda qapısının AÇIQ CI opt-in-i.

YALNIZ `.github/workflows/_e2e-smoke.yml`-in seed addımları istifadə edir:
prod-stil konteynerdə deterministik E2E istifadəçilərini yaratmaq üçün.
Qapının məqsədi TƏSADÜFİ production icrasının qarşısıdır; bu modulun seçilməsi
workflow-da görünən şüurlu aktdır və heç bir env dəyişəni ilə aktivləşmir.
Real production deploy-u bu modulu heç vaxt işlətmir.
"""

from .production import *  # noqa: F401,F403

MANAGEMENT_COMMAND_ENVIRONMENT = "test"
