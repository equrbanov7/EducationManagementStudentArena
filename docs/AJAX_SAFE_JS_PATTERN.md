# AJAX-safe JS — universal pattern (EMSReady / EMSDelegate)

## Problem

Profile/dashboard bölmələri AJAX-la DOM-a yüklənir (`profile.js` fragment fetch edib
`profile:section:loaded` event göndərir). CSP sərtdir: `script-src` yalnız `NONCE`
istifadə edir, `unsafe-inline` yoxdur → inline `onclick=""` **bloklanır**, hər
interaksiya JS-dən keçməlidir.

Köhnə antipattern:

```js
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".js-edit-post").forEach((btn) =>
    btn.addEventListener("click", handler)   // yalnız ilk paint-dəki elementlər
  );
});
```

`DOMContentLoaded` bir dəfə işləyir və yalnız o anda mövcud elementləri bağlayır.
AJAX swap-dan sonra gələn yeni düymələr **bağlanmamış** qalır → "ölü" görünür,
yalnız səhifəni refresh edəndə işləyir.

## Həll — 2 universal primitiv

Hər ikisi `static/js/ems_ajax_init.js`-dədir, `base.html`-də bütün section
script-lərindən **əvvəl** qlobal yüklənir.

### 1) `EMSDelegate.on(eventType, selector, handler)` — YENİ kod üçün (tövsiyə olunan)

`document`-ə bir dəfə delegated listener qoşur. `document` heç vaxt swap olunmadığı
üçün **cari və gələcək** bütün AJAX elementlərini avtomatik tutur. Heç vaxt
yığılmır, heç vaxt köhnəlmir.

```js
EMSDelegate.on("click", ".js-edit-post", function (e, btn) {
  openEditModal(btn.dataset.postId);   // `this` = `btn` = uyğun gələn element
});
```

### 2) `EMSReady(fn)` — MÖVCUD DOMContentLoaded init-i refactor etmədən AJAX-safe etmək üçün

`fn`-i ilk yüklənmədə VƏ hər `profile:section:loaded` swap-dan sonra işə salır.
`fn` **null-safe** (element lookup-ları `if (x)` ilə qoruyur) və **idempotent**
olmalıdır (document/window-a listener yığmamalı).

```js
window.EMSReady(function () {
  // ...mövcud init gövdəsi... (getElementById-lar hər swap-da yenidən query olunur)
});
```

### 3) `EMSReady.once(key, fn)` — yalnız bir dəfə qeydiyyat

`EMSReady` təkrar işləsə də `document`/`window`-a yalnız bir dəfə qoşulmalı olan
listener-lər üçün:

```js
EMSReady.once("post-esc", function () {
  document.addEventListener("keydown", onEsc);
});
```

## Artıq tətbiq olunub

- `apps/blog/static/js/user_profile.js` — posts bölməsi (edit/delete/create post).
  `EMSReady`-ə keçirildi, modal `<body>`-yə köçürmə idempotent edildi, ESC keydown
  hər run-da yenidən bağlanır (yığılmadan).

## Növbəti namizədlər (eyni antipattern, profile bölmələrində yüklənir)

Bu fayllar `profile.html`-də yüklənir və öz bölmələrində eyni "ölü düymə"
problemini verə bilər — lazım olduqca eyni qaydada (`EMSReady` sarğısı + ya
`EMSDelegate.on`) keçirin:

- `apps/accounts/static/accounts/js/category_management.js`
- `apps/accounts/static/accounts/js/role_assignment_search.js`
- `apps/accounts/static/accounts/js/permission_editor_ui.js`
- `apps/accounts/static/accounts/js/manage_roles.js`
- `apps/accounts/static/accounts/js/superadmin_user_management.js`
- `apps/blog/static/js/post_category_picker.js`
- `apps/courses/static/courses/js/create_course_modal.js`
- `apps/exams/static/exams/js/profile_group_modal.js`

## Struktur qayda — modallar/script-lər panel İÇİNDƏ olmalıdır

`profile.js` AJAX swap zamanı yalnız `[data-profile-section-panel]` elementini
götürür (`extractSectionFromHtml` → `root.querySelector('[data-profile-section-panel="..."]')`).
Bu elementdən **kənarda** olan hər şey (modal, `<script>`) AJAX-da **atılır** və
yalnız refresh-də işləyir.

> Bölmənin bütün modal və inline `<script>`-ləri həmin bölmənin
> `<section data-profile-section-panel>` ... `</section>` **İÇİNDƏ** olmalıdır.
> Düzgün nümunə: `_notifications.html`, `_statistics.html` (script panel içində).

## Bu sessiyada düzəldilən struktur buglar

- **`_pending_post_approvals.html`** — `postActionConfirmModal` + inline `<script>`
  panel-dən kənarda idi → deaktiv/sil/toggle düymələri AJAX-dan sonra ölü, "Redaktə et"
  isə `editTitle null` TypeError verirdi. Modal+script panel içinə köçürüldü, paylaşılan
  `_post_edit_modal.html` əlavə olundu, ESC keydown bir dəfə bağlanır.
- **`_assigned_exams.html`** — `assignedExamInfoBackdrop` modalı panel-dən kənarda idi.
  Panel içinə köçürüldü; `profile.js`-də açılış/bağlama/start/kod-submit referensləri
  re-query + delegasiya ilə AJAX-safe edildi.
- **`main.py`** — moderator edit modalının kateqoriya select-ləri üçün
  `pending-post-approvals` branch-ında picker option-ları qurulur.

## Qayda (gələcək üçün)

> 1. AJAX-la swap olunan istənilən interaktiv element **`document` üzərində event
>    delegation** ilə bağlanmalıdır (`EMSDelegate.on`), VƏ YA bölmə init-i `EMSReady`-ə
>    sarınmalıdır. Yükləmə anında `querySelectorAll(...).forEach(addEventListener)` ilə
>    birbaşa bağlama — bu "ölü düymə" problemi yaradır.
> 2. Bölmənin modal və `<script>`-ləri `[data-profile-section-panel]` **içində** olmalıdır.
> 3. `document`/`window`-a listener qoşan kodu `EMSReady.once(...)` və ya `window.__flag`
>    ilə bir dəfə qoş ki, swap-da yığılmasın.
