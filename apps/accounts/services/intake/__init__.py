"""Tələbə idxalı (student intake) — PUBLIC fasad.

AUDİT BOŞLUĞU (2026-09, PHASE 1 §4). «Tələbə şöbəsi siyahı yükləyir → qeydlər →
əlaqələr → hesablar → tələbə girə bilir» axınının işləyən YEGANƏ yolu legacy
köçürmə idi: `import_users_from_excel` management komandası prod-da
`core/management/command_safety.py` ilə QƏSDƏN bağlıdır, RİM mərkəzi isə yalnız
MÖVCUD hesabları idarə edir (blok/parol/silmə/bərpa). Bu paket həmin boşluğu
nəzarətli, icazəli və audit olunan UI səthi ilə örtür.

⚠️ Management komandasının prod kill-switch-i ZƏİFLƏDİLMİR. O, superadmin-in
server aləti olaraq qalır; universitetin gündəlik əməliyyatı isə profil
kabinetindəki «Tələbə idxalı» bölməsidir (`user.import` icazəsi).

Modul bölgüsü:

* ``policy``  — icazə qapısı (`user.import`, fail-closed, aktiv üzvlük tələbi)
* ``spec``    — sütun müqaviləsi + şablon faylı (.xlsx / CSV)
* ``parsing`` — yüklənmiş faylın oxunması (ölçü/uzantı/sətir tavanı)
* ``validate``— sətir-sətir QURU icra: plan + xəbərdarlıq + xəta
* ``apply``   — planların icrası (sətir başına savepoint + audit)

TƏHLÜKƏSİZLİK QEYDLƏRİ

* `alumni` / arxiv qaydalarına TOXUNULMUR: idxal yalnız YENİ kimlik yaradır,
  mövcud hesabın `access_state`-inə heç vaxt yazmır. `login_blocked_access_states`
  dəsti dəyişməz qalır.
* Yaradılan hesab ``password_change_required=True`` + ``email_verified=False``
  ilə gəlir → ilk girişdə e-poçt + OTP + yeni parol məcburidir.
* Birdəfəlik parol audit jurnalına YAZILMIR; yalnız əməliyyatın cavabında
  qayıdır (operator onu CSV kimi endirir — `provision_student_credentials`
  komandasının çap-parol modeli ilə eyni).
"""

from .apply import apply_plans
from .create import (
    ACCOUNT_KINDS,
    KIND_STUDENT,
    KIND_TEACHER,
    IntakeApplyError,
    account_role,
    create_account,
    generate_initial_password,
    student_role,
    teacher_role,
)
from .parsing import MAX_ROWS, MAX_UPLOAD_BYTES, IntakeFileError, read_rows
from .policy import PERM_IMPORT, IntakeAccessError, can_import, require_import
from .spec import build_template, columns, header_row
from .validate import PLACEHOLDER_DOMAIN, RowPlan, build_plans, summarize

__all__ = [
    "ACCOUNT_KINDS",
    "KIND_STUDENT",
    "KIND_TEACHER",
    "MAX_ROWS",
    "MAX_UPLOAD_BYTES",
    "PERM_IMPORT",
    "PLACEHOLDER_DOMAIN",
    "IntakeAccessError",
    "IntakeApplyError",
    "IntakeFileError",
    "RowPlan",
    "account_role",
    "apply_plans",
    "build_plans",
    "build_template",
    "can_import",
    "columns",
    "create_account",
    "generate_initial_password",
    "header_row",
    "read_rows",
    "require_import",
    "student_role",
    "summarize",
    "teacher_role",
]
