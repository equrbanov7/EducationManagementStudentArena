"""RİM (Rəqəmsal İnkişaf Mərkəzi) — hesab idarəetmə servisləri (PUBLIC fasad).

SƏLAHİYYƏT HÜDUDU (RİM Əsasnaməsi, X bölmə + Proqram inzibatçısı təlimatı §34)
------------------------------------------------------------------------------
Mərkəz TEXNİKİ PLATFORMANIN idarəedicisidir. Akademik və inzibati məlumatın
MƏZMUN DOĞRULUĞUNA görə isə müvafiq biznes sahibi struktur bölmə (dekanlıq /
kafedra / tədris hissəsi) cavabdehdir. Buna görə bu modulun səthi qəsdən belə
bölünüb:

* **BƏLİ** — hesabın özü: parol təyini, giriş bloku, soft-delete/bərpa, şəxsi
  identifikasiya məlumatı (ad, soyad, ata adı, email, telefon, FİN), rol-üzvlük
  görünüşü.
* **XEYR** — akademik MƏZMUN: qiymət, davamiyyət, jurnal yazısı, imtahan
  nəticəsi. Bu modulda onlara toxunan heç bir funksiya YOXDUR və əlavə
  edilməməlidir. Səhv qiymət düzəlişi ayrıca, sənədli (PDF + audit) jurnal
  korreksiya axınının işidir (`journal.correct` icazəsi, apps/registrar).

SƏLAHİYYƏT AYRILIĞI (Əsasnamə 5.5)
----------------------------------
«Yeni administrator səlahiyyəti bir nəfərin nəzarətsiz qərarı ilə həyata
keçirilməməlidir.» Ona görə `user.grant_privileged` açarı RİM rolunun DEFAULT
dəstinə daxil deyil və `user.*` wildcard-ı rol təriflərində işlədilmir. Admin
təyinatı mövcud `org.admin.assign` qapısından keçir (bax
`views/roles/_assignment_flow/flow.py`).

Modul bölgüsü:

* ``policy``       — icazə + iyerarxiya qapısı (kim kimi idarə edə bilər)
* ``search``       — ad/soyad/ATA ADI/email/FİN/username üzrə axtarış
* ``credentials``  — birdəfəlik parol təyini (parol audit-ə YAZILMIR)
* ``profile_edit`` — şəxsi məlumatların redaktəsi (email dəyişəndə təsdiq sıfırlanır)
* ``lifecycle``    — blok / blokdan çıxarma / soft-delete / bərpa (hard delete YOX)
* ``detail``       — siyahı sətri + detal kartı serializasiyası (ikili rol görünür)
* ``create_unit``  — «yeni inzibati bölmə» OXU qapısı (yazı struktur ağacındadır)
"""

from .create import PERM_CREATE, RimCreateError, can_create, create_account, require_create
from .create_options import CATALOGS, search_catalog
from .create_unit import (
    ADMIN_UNIT_TYPES,
    PERM_UNIT_TREE,
    admin_unit_type_choices,
    can_create_unit,
    require_create_unit,
)
from .credentials import set_temporary_password
from .detail import serialize_detail, serialize_memberships, serialize_row
from .lifecycle import block_user, normalize_reason, restore_user, soft_delete_user, unblock_user
from .policy import (
    PERM_BLOCK,
    PERM_CREDENTIALS,
    PERM_EDIT,
    PERM_SEARCH,
    PERM_SOFT_DELETE,
    RIM_PERMISSIONS,
    RimAccessError,
    RimActor,
    assert_can_manage,
    manageable_users_queryset,
    require_permission,
    resolve_actor,
    target_level,
)
from .profile_edit import EDITABLE_FIELDS, FIELD_LABELS, update_user_fields
from .search import account_status, search_users

__all__ = [
    "ADMIN_UNIT_TYPES",
    "CATALOGS",
    "EDITABLE_FIELDS",
    "FIELD_LABELS",
    "PERM_BLOCK",
    "PERM_CREATE",
    "PERM_CREDENTIALS",
    "PERM_EDIT",
    "PERM_SEARCH",
    "PERM_SOFT_DELETE",
    "PERM_UNIT_TREE",
    "RIM_PERMISSIONS",
    "RimAccessError",
    "RimActor",
    "RimCreateError",
    "account_status",
    "admin_unit_type_choices",
    "assert_can_manage",
    "block_user",
    "can_create",
    "can_create_unit",
    "create_account",
    "require_create",
    "search_catalog",
    "manageable_users_queryset",
    "normalize_reason",
    "require_create_unit",
    "require_permission",
    "resolve_actor",
    "restore_user",
    "search_users",
    "serialize_detail",
    "serialize_memberships",
    "serialize_row",
    "set_temporary_password",
    "soft_delete_user",
    "target_level",
    "unblock_user",
    "update_user_fields",
]
