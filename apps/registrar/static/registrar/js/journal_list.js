/*
 * journal_list.js
 * Source: apps/registrar/templates/registrar/partials/_journal_list_content.html
 * Filter auto-submit + loading skeleton for the journal (Elektron jurnal) list.
 *
 * Sahib tələbi (2026-09-06): «search edəndə, seçəndə dizaynı pozmuyan rahat
 * formada olan bir hissə olsun» — hər filtr yolu (select, axtarış, dərs tipi
 * pilləsi, sıfırla, səhifələmə, Enter ilə göndəriş) skeleti açır, ona görə
 * server cavabını gözləyərkən boş ekran və ya sıçrayan düzüm görünmür.
 *
 * AJAX-safe: yalnız document səviyyəli delegasiya (EMSDelegate / EMSSearchInput).
 */
window.jlShowLoading = function () {
    var page = document.querySelector(".jl-page");
    if (!page) { return; }
    page.classList.add("is-loading");
    // Skeleton siyahının yerinə keçir — istifadəçi onu görsün deyə kartın
    // yuxarısına sürüşdürülür (uzun filtr sətrindən sonra ekrandan çıxa bilər).
    var skel = page.querySelector("[data-jl-skel]");
    if (skel && skel.scrollIntoView) {
        skel.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
};

/* 2026-10-14 (sahib: «yazarkən search gedir, render olur, axtardığım itir»):
 * dinləyicilər delegasiyalıdır (form/select-ə bağlanmır). AXTARIŞ qutusu vahid
 * EMSSearchInput qaydası ilə — yazı DAYANANDAN 1500 ms sonra, ≥ 2 simvol,
 * Enter dərhal, IME gözlənilir. Göndəriş «soft»-dur: səhifə yenilənmir,
 * filtr sətri (input + axtarışlı seçicilər) YERİNDƏ qalır, yalnız siyahı
 * `.jl-page` daxilində yenilənir (köhnə yavaş cavab atılır). */
var JL_FORM = "[data-jd-filterform]";

// Hər tam göndəriş yolu (düymə, dərs tipi pilləsi, JS submit) — tək lövbər.
window.EMSDelegate.on("submit", JL_FORM, function () { window.jlShowLoading(); });

// Select-lər: bootstrap-select vidcetində dəyişiklik proqramla olur → `change`.
window.EMSDelegate.on("change", JL_FORM + " [data-jl-autosubmit]", function (event, sel) {
    if (sel.form) { window.jlShowLoading(); sel.form.submit(); }
});

// Sıfırla adi keçiddir.
window.EMSDelegate.on("click", JL_FORM + " .jd2-filter-reset", function () { window.jlShowLoading(); });

window.EMSSearchInput.delegate(JL_FORM + " [data-jl-search-debounce]", {
    onSearch: function (value, meta) {
        if (meta.input.form) {
            window.EMSSearchInput.submitForm(meta.input.form, { input: meta.input, soft: ".jl-page" });
        }
    },
});

// Səhifələmə keçidləri (paylaşılan `_pagination.html`) — `document`-ə bir dəfə
// delegasiya olunur ki, swap-dan sonra yığılmasın.
window.EMSDelegate.on("click", ".jl-page .pagination-wrapper a", function () {
    window.jlShowLoading();
});
