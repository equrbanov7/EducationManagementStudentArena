# EMS Arena — layihə qaydaları (Claude Code)

## Frontend: HEÇ VAXT inline/internal CSS və ya JS — YALNIZ external fayl

**Qayda.** Template-lərdə (`apps/**/templates/**/*.html`, `templates/**/*.html`)
CSS və JS **inline / internal** yazılmır. Hər zaman **xarici fayla** çıxarılıb
`static/`-dən yüklənir.

Bu, təsadüfi üslub seçimi deyil — layihənin CSP-si (`config/settings/components/csp.py`)
`script-src` və `style-src` üçün `unsafe-inline` **vermir** (yalnız `SELF` + `NONCE`).
Yəni:

- Xarici `<link rel="stylesheet" href="{% static ... %}">` və
  `<script src="{% static ... %}">` — nonce-suz işləyir. ✅ **Doğru yol.**
- Inline `<style>…</style>` / `<script>…</script>` — yalnız `{{ request.csp_nonce }}`
  ilə işləyir, əks halda brauzer bloklayır. ❌ **Yazmayın.**
- Inline `style="…"` atributu — `style-src-attr: 'unsafe-inline'` ilə **müvəqqəti**
  icazəlidir; hədəf ondan tam çıxmaqdır (bax csp.py şərhi). Yeni kodda yazmayın.

### Harada saxlanılır

Per-app static strukturu (mövcud konvensiya):

```
apps/<app>/static/<app>/css/<template-adı>.css
apps/<app>/static/<app>/js/<template-adı>.js
```

Qlobal/paylaşılan olanlar: `static/css/…`, `static/js/…`.

### Necə yüklənir

- **Tam səhifə (base.html extend edir):** CSS-i `{% block extraCss %}` içində
  `<link>`, JS-i `{% block extraJs %}` içində `<script src>` ilə yüklə.
- **Partial (AJAX/HTMX ilə swap olunur):** partial-ın öz içində `<link>` /
  `<script src>` qoy. Bölmə script-ləri `[data-profile-section-panel]` **içində**
  olmalıdır (bax `docs/frontend/AJAX_SAFE_JS_PATTERN.md`).

### Dinamik dəyər (Django template dəyişəni) olan JS/CSS

Xarici `.js`/`.css` faylı Django template engine-dən **keçmir** — orada
`{{ var }}` / `{% url %}` / `{% csrf_token %}` **işləmir**. Ona görə dinamik
dəyəri koda “bişirmək” olmaz; onu **data-atribut** və ya **JSON script bloku** ilə
ötür, xarici JS isə onu DOM-dan oxusun:

```html
<!-- template -->
<div id="grade-panel"
     data-save-url="{% url 'journal:save' offering.id %}"
     data-student-id="{{ student.id }}"
     data-max-score="{{ offering.max_score }}">…</div>
<script src="{% static 'journal/js/grade_panel.js' %}"></script>
```

```js
// apps/journal/static/journal/js/grade_panel.js  — AJAX-safe (EMSReady)
window.EMSReady(function () {
  const el = document.getElementById("grade-panel");
  if (!el) return;                       // null-safe (swap olmamış ola bilər)
  const url = el.dataset.saveUrl;        // {% url %} nəticəsi data-atributdan
  const maxScore = Number(el.dataset.maxScore);
  // … EMSCore.fetchJSON(url, …)
});
```

Çoxlu/struktur data üçün JSON:

```html
<script id="exam-config" type="application/json">{{ config_json|safe }}</script>
```
```js
const cfg = JSON.parse(document.getElementById("exam-config").textContent);
```

### JS həmişə AJAX-safe olmalıdır

Çıxarılan JS `DOMContentLoaded + querySelectorAll().forEach(addEventListener)`
antipattern-i ilə yazılmır. `window.EMSReady(fn)` sarğısı (idempotent, null-safe)
və ya `EMSDelegate.on(evt, selector, fn)` işlət. CSRF/fetch üçün `EMSCore.getCookie`
/ `EMSCore.fetchJSON`. Detallar: `docs/frontend/AJAX_SAFE_JS_PATTERN.md`.

### Inline `style="…"` atributları

- **Statik** (`style="display:none"`, `style="margin-top:8px"`) → CSS class-a çevir
  (utility class və ya komponent CSS-i).
- **Dinamik** (`style="width: {{ pct }}%"`) → hələlik saxla (çıxarmaq praktik deyil);
  lazım olsa CSS custom property + data-atribut ilə (`style="--pct:{{ pct }}%"` və
  CSS `width:var(--pct)`), amma bu opsionaldır. Statiklərdən başla.

### Yoxlama

Dəyişiklikdən sonra:
```bash
grep -rlE '<style|<script(?![^>]*src=)[^>]*>[^<]' apps templates --include='*.html'
```
azalmalıdır; `python manage.py collectstatic --dry-run` və dəyişən səhifənin
brauzerdə konsol/CSP xətası olmadan işlədiyi yoxlanılır.
