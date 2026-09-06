/* Dərs modalı — "DƏRSİN MÜƏLLİMİ" axtarışlı/lazy seçici (QA 2026-09-05 P3-13).
 *
 * Əvvəllər təşkilatın BÜTÜN namizədləri (554-ə qədər) hər jurnal səhifəsi
 * yüklənməsində <option> kimi HTML-ə bişirilirdi. İndi mövcud
 * `EMSSearchableSelect` komponenti (bax `journal_list_pickers.js` — eyni
 * nümunə) server-side axtarışla işləyir; namizəd siyahısı yalnız seçici
 * açılanda, hərflə-hərflə axtarışla gəlir.
 *
 * Hidden input-un (`lesson_instructor`) dəyəri HƏR ZAMAN doğrudur — ya
 * server-dən ilkin dəyər (`value="{{ offering.instructor_id }}"`), ya da
 * `journal_grid.js`-in redaktə açılışında yazdığı xam id (bax
 * `openModal()` → `setSelectValue(instrField, editData.instructor)`, hidden
 * input üçün bu sadəcə `.value` təyinatıdır). Bu modul YALNIZ görünən çipin
 * İNSAN-OXUNAQLI adını tamamlayır — şəbəkə geciksə/uğursuz olsa belə POST
 * dəyəri təsirlənmir.
 */
(function boot() {
    if (!window.EMSSearchableSelect) {
        setTimeout(boot, 30);
        return;
    }
    var modal = document.querySelector("[data-jd-lesson-modal]");
    var hidden = modal ? modal.querySelector("[data-jd-lesson-instructor]") : null;
    var root = modal ? modal.querySelector(".js-jdt-teacher") : null;
    if (!modal || !hidden || !root || modal.dataset.jdtTeacherInit === "1") {
        return;
    }
    modal.dataset.jdtTeacherInit = "1";

    var url = hidden.dataset.searchUrl;
    var SS = window.EMSSearchableSelect;
    var initializing = true;
    var pick = SS.create(root, {
        url: url,
        onChange: function () {
            if (initializing) {
                return;
            }
            hidden.value = pick.value() || "";
        },
    });
    if (!pick) {
        return;
    }

    /** Redaktədə/defaultda ARTIQ bilinən id-nin insan-oxunaqlı adını tapıb çipi doldurur. */
    function resolveLabel(id) {
        if (!id || !url) {
            return;
        }
        fetch(url + "?resolve=" + encodeURIComponent(id), { headers: { "X-Requested-With": "XMLHttpRequest" } })
            .then(function (r) {
                return r.ok ? r.json() : null;
            })
            .then(function (data) {
                var row = data && data.results && data.results[0];
                if (row) {
                    initializing = true;
                    pick.setValue(row.id, row.text);
                    initializing = false;
                }
            })
            .catch(function () {
                /* Sükutla keç — hidden dəyər onsuz da doğrudur, yalnız çip adsız qalır. */
            });
    }

    document.addEventListener("jd:lesson-modal-open", function (event) {
        if (event.target !== modal) {
            return;
        }
        initializing = true;
        pick.reset();
        var editData = event.detail;
        var id = (editData && editData.instructor) || hidden.value || "";
        if (id) {
            hidden.value = id;
            resolveLabel(id);
        } else {
            initializing = false;
        }
    });
})();
