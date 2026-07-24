/*
 * journal_list.js
 * Source: apps/registrar/templates/registrar/partials/_journal_list_content.html
 * Filter auto-submit + loading skeleton for the journal (Elektron jurnal) list.
 */
// Filtr dəyişəndə skeleton göstər + formu göndər. bootstrap-select vidcet üçün
// inline onchange etibarsız ola bilər (proqramla dəyişmə) — açıq change listener
// ilə həm müəllim, həm korrektor görünüşündə işləyir. `jlShowLoading` server
// cavabını gözləyərkən skeleti açır ki, dizayn sıçramasın.
window.jlShowLoading = function () {
    var page = document.querySelector(".jl-page");
    if (page) { page.classList.add("is-loading"); }
};
(function autoSubmit() {
    var form = document.querySelector("[data-jd-filterform]");
    if (!form || form.dataset.jlAuto === "1") { return; }
    form.dataset.jlAuto = "1";
    form.querySelectorAll("[data-jl-autosubmit]").forEach(function (sel) {
        sel.addEventListener("change", function () { window.jlShowLoading(); form.submit(); });
    });
    // Dərs tipi pilləri (submit düymələri) və sıfırla keçidi də skeleton göstərsin.
    form.querySelectorAll(".jd2-kindpill").forEach(function (btn) {
        btn.addEventListener("click", function () { window.jlShowLoading(); });
    });
    var reset = form.querySelector(".jd2-filter-reset");
    if (reset) { reset.addEventListener("click", function () { window.jlShowLoading(); }); }
    // AXTARIŞ qutusu: yazdıqca 350ms debounce ilə göndər (hər hərfdə yox).
    var searchBox = form.querySelector("[data-jl-search-debounce]");
    if (searchBox) {
        var searchTimer = null;
        searchBox.addEventListener("input", function () {
            if (searchTimer) { clearTimeout(searchTimer); }
            searchTimer = setTimeout(function () { window.jlShowLoading(); form.submit(); }, 350);
        });
    }
})();
