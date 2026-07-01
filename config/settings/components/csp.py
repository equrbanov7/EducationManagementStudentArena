"""EMS Arena base settings — csp komponenti.

Bu fayl `config/settings/base.py` tərəfindən paylaşılan namespace-də
`exec`-include olunur (django-split-settings üslubu). Ona görə burada
ayrıca import yoxdur — os, Path, messages, CSP sabitləri və `_env_*`
köməkçiləri base.py-dən gəlir. Sıra base.py-dəki _COMPONENTS siyahısı ilə
idarə olunur (asılılıqlar: bax base.py).
"""

# flake8: noqa: F821  (paylaşılan namespace: adlar base.py-dən gəlir)

# Content Security Policy (CSP) settings
# https://django-csp.readthedocs.io/en/latest/configuration.html
#
# 'unsafe-inline' is intentionally absent from script-src.
# Inline <script> blocks must use a per-request nonce
# via {{ request.csp_nonce }} and the NONCE sentinel.
#
# Inline <style> blocks must also use a per-request nonce. Inline style=""
# attributes are temporarily scoped to style-src-attr so style-src itself can
# remain strict while the remaining templates are migrated off inline attrs.
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": [SELF],
        "font-src": [
            SELF,
            "data:",
            "https://fonts.gstatic.com",
        ],
        "img-src": [
            SELF,
            "data:",
            "blob:",
            *MICROSOFT_CLARITY_IMG_SRC,
        ],
        "media-src": [
            SELF,
            "blob:",
        ],
        "script-src": [
            SELF,
            NONCE,
            *MICROSOFT_CLARITY_SCRIPT_SRC,
        ],
        "style-src": [
            SELF,
            NONCE,
            "https://fonts.googleapis.com",
        ],
        "style-src-attr": [
            UNSAFE_INLINE,
        ],
        "connect-src": [
            SELF,
            "ws://127.0.0.1:8000",
            "ws://localhost:8000",
            "ws://0.0.0.0:8000",
            *MICROSOFT_CLARITY_CONNECT_SRC,
        ],
        "object-src": [NONE],
        "base-uri": [SELF],
        "frame-ancestors": [NONE],
        "form-action": [SELF],
    }
}
