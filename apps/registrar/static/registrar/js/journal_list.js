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
 * AJAX-safe: `EMSReady` (kabinet qabığında bölmə swap olunanda yenidən qurulur,
 * null-safe, idempotent — `data-jl-auto` bayrağı ilə təkrar bağlanmır).
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

window.EMSReady(function () {
    var form = document.querySelector("[data-jd-filterform]");
    if (!form || form.dataset.jlAuto === "1") { return; }
    form.dataset.jlAuto = "1";

    // Hər göndəriş yolu (Enter, düymə, JS submit) — tək lövbər.
    form.addEventListener("submit", function () { window.jlShowLoading(); });

    // Select-lər: bootstrap-select vidcetində dəyişiklik proqramla olur, ona
    // görə inline onchange yox, açıq `change` dinləyicisi.
    form.querySelectorAll("[data-jl-autosubmit]").forEach(function (sel) {
        sel.addEventListener("change", function () { window.jlShowLoading(); form.submit(); });
    });

    // Dərs tipi pilləri submit düymələridir → `submit` hadisəsi tutur; sıfırla
    // isə adi keçiddir, onu ayrıca bağlayırıq.
    var reset = form.querySelector(".jd2-filter-reset");
    if (reset) { reset.addEventListener("click", function () { window.jlShowLoading(); }); }

    // AXTARIŞ qutusu: yazdıqca 350ms debounce ilə göndər (hər hərfdə yox).
    var searchBox = form.querySelector("[data-jl-search-debounce]");
    if (searchBox) {
        var searchTimer = null;
        searchBox.addEventListener("input", function () {
            if (searchTimer) { clearTimeout(searchTimer); }
            searchTimer = setTimeout(function () { form.submit(); }, 350);
        });
    }
});

// Səhifələmə keçidləri (paylaşılan `_pagination.html`) — `document`-ə bir dəfə
// delegasiya olunur ki, swap-dan sonra yığılmasın.
window.EMSDelegate.on("click", ".jl-page .pagination-wrapper a", function () {
    window.jlShowLoading();
});
