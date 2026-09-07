"""RİM mərkəzi view-ları (profil SPA bölməsi + JSON endpoint-ləri)."""

from .actions import rim_action
from .api import rim_user_detail, rim_user_search
from .create import rim_create_account, rim_create_catalog
from .section import build_rim_center_section

__all__ = [
    "build_rim_center_section",
    "rim_action",
    "rim_create_account",
    "rim_create_catalog",
    "rim_user_detail",
    "rim_user_search",
]
