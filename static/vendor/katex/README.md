# KaTeX (vendored)

Version: **0.16.47** (latest 0.16.x at 2026-09-14). Pinned; do not load from a CDN
(CSP: `script-src`/`style-src` are `'self'` + nonce only).

Source: https://github.com/KaTeX/KaTeX/releases/download/v0.16.47/katex.tar.gz
Release tarball SHA256: `e1a40008b02a0a9eb3d6097288a247317752148b7215edcf83fd25e8644bbd36`
License: MIT (see `0.16.47/LICENSE`, fetched from the `v0.16.47` tag).

Files copied from the tarball (unchanged) — SHA256:

```
a29d2961d3146de5949d78ac7c1a9d93ae54955bad22a6db4fbe836e88e8bf48  katex.min.js
c9eac1c75c95f7dcbb6db0210cf0a49a150d07aaf599292e5f9ca099c596a119  katex.min.css
e5372d199bcdae8b4de71d0f7ceba72a4ba12774a27c60a6f1f77d03b3228ee4  contrib/auto-render.min.js
766ccc1f306c885aa45542a9846bbd0a505b27a0374f146778171c2254ce18e3  LICENSE
0cdd387c9590a1a9f9794560022dbb59654a7d86f187aa0c81495ad42d3a7308  fonts/KaTeX_AMS-Regular.woff2
de7701e42cf1f4cf0b766c03fb27977207eee2f4fd5d76fa82188406da43ea4c  fonts/KaTeX_Caligraphic-Bold.woff2
5d53e70ad607c2352162dec9e0923fb54ecdafaccbf604cd8dcf7d00facb989b  fonts/KaTeX_Caligraphic-Regular.woff2
74444efd593c005e3f4573b44524704c0af0a937fe911cca9e94068d0d140d3f  fonts/KaTeX_Fraktur-Bold.woff2
51814d270d06ff0255dba0799994fa4d8c84d11f09951d47595f4abb1f3602dc  fonts/KaTeX_Fraktur-Regular.woff2
0f60d1b897938ec918c8ce073092411baf9438f6739465693ff18b0f9d20b021  fonts/KaTeX_Main-Bold.woff2
99cd42a3c072d918f2f44984a807cf7aa16e13545fd0875fc07c6c65f99e715b  fonts/KaTeX_Main-BoldItalic.woff2
97479ca6cce906abc961ecac96faa5f9ca2e61b8e7670d475826bcdee9a7c267  fonts/KaTeX_Main-Italic.woff2
c2342cd8b869e01752a9321dc17213fc40d4d04c79688c1d43f2cf316abd7866  fonts/KaTeX_Main-Regular.woff2
dc47344dbb6cb5b655c8460d561f4df5f501b90c804ad3c6cec65fe322351ab1  fonts/KaTeX_Math-BoldItalic.woff2
7af58c5ec8f132a2ddde9027c6d7814decce4d3b822a11192a42a20e2e973264  fonts/KaTeX_Math-Italic.woff2
e99ae51144bf1232efcc1bfe5add36262c6866b0faab24fa75740e1b98577a62  fonts/KaTeX_SansSerif-Bold.woff2
00b26ac825e2095056396e0553b8ac26d3f8ad158c3826e28b4c45b385c4714a  fonts/KaTeX_SansSerif-Italic.woff2
68e8c73ef42afd3ccec58bf0fba302cce448938e7fc020a5e31f8a952eee1342  fonts/KaTeX_SansSerif-Regular.woff2
036d4e95149b69ff9bcc0cd55771efeb25ffa3947293e69acd78d5ac328c684b  fonts/KaTeX_Script-Regular.woff2
6b47c40166b6dbe21a5dfca7718413f2147fd2399be1ba605d8ad39cedf25dfe  fonts/KaTeX_Size1-Regular.woff2
d04c54219f9eaec6d4d4fd42dfb28785975a4794d6b2fc71e566b9cd6db842dd  fonts/KaTeX_Size2-Regular.woff2
73d591271b1604960cb10bb90fee021670af7297017e0e98480b332d11f51995  fonts/KaTeX_Size3-Regular.woff2
a4af7d414440a1c1790825cfb700cf9cf43b0f2c4b04f0ebc523011ad9853ec0  fonts/KaTeX_Size4-Regular.woff2
71d517d67827787cfabdf186914cc3358eda539e37931941f2b2fd4a21f68c0b  fonts/KaTeX_Typewriter-Regular.woff2
```

Only the `.woff2` fonts are shipped — `katex.min.css` lists `woff2` first in every
`@font-face` `src` and every supported browser takes it; the `.woff`/`.ttf`
fallbacks are never requested.

## How it is used

- Assets are included through `templates/partials/ems_ui/_math_assets.html`
  (`<link>` + deferred `<script src>`; no inline code) ONLY on pages that render
  question text (take exam, results, attempt review, question bank lists,
  bulk-add preview).
- `static/js/ems_math.js` calls `renderMathInElement` inside `[data-ems-math]`
  containers with delimiters `$$…$$`, `\[…\]`, `\(…\)`, `$…$`, and
  `throwOnError:false, trust:false, strict:"ignore"`. Question HTML stays
  escaped by Django — KaTeX reads text nodes only. A `MutationObserver`
  re-renders content swapped in by AJAX (strict question delivery, cabinet
  sections).
- CSP: scripts/styles/fonts are same-origin. KaTeX's HTML output uses inline
  `style="…"` attributes, which is why `style-src-attr 'unsafe-inline'` (already
  present in `config/settings/components/csp.py`) is required. If that directive
  is ever removed, switch `ems_math.js` to `output: "mathml"` (no inline styles,
  native MathML rendering).

## Upgrading

Download the release tarball for the new tag, verify its SHA256 against the
GitHub release, copy the same file set into `static/vendor/katex/<version>/`,
update the version in `_math_assets.html` and this README.

**Qeyd (2026-09-14):** `katex.min.css`-dən `.woff`/`.ttf` fallback `src` girişləri
silinib — yalnız `fonts/*.woff2` vendorlanır (bütün dəstəklənən brauzerlər
woff2 oxuyur). Əks halda `CompressedManifestStaticFilesStorage` çatışmayan
fayl istinadına görə `collectstatic`-i qırır (CI docker-build 2026-09-14).
