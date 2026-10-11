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
 *
 * 2026-10-10: «Yeni dərs» doldurması (journal_lesson_prefill.js) gizli dəyəri açılışdan ƏVVƏL qoyur;
 * dərs tipi dəyişəndə müəllimi `window.EMSJournalLessonTeacher.show(id)` ilə dəyişir. Ad sorğusu
 * uğursuz olsa da seçici «başlanğıc» vəziyyətində ilişib qalmır, köhnə cavab yenisinin üstünə yazılmır.
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

    var requestSeq = 0;

    /** Redaktədə/defaultda ARTIQ bilinən id-nin insan-oxunaqlı adını tapıb çipi doldurur. */
    function resolveLabel(id) {
        var mine = ++requestSeq;
        if (!id || !url) {
            initializing = false;
            return;
        }
        fetch(url + "?resolve=" + encodeURIComponent(id), { headers: { "X-Requested-With": "XMLHttpRequest" } })
            .then(function (r) {
                return r.ok ? r.json() : null;
            })
            .then(function (data) {
                var row = data && data.results && data.results[0];
                if (row && mine === requestSeq) {
                    initializing = true;
                    pick.setValue(row.id, row.text);
                }
            })
            .catch(function () {
                /* Sükutla keç — hidden dəyər onsuz da doğrudur, yalnız çip adsız qalır. */
            })
            .finally(function () {
                if (mine === requestSeq) {
                    initializing = false; // uğursuz sorğuda da müəllimin sonrakı seçimi yazılsın
                }
            });
    }

    /** Gizli dəyəri + çipi proqramla qoy (açılışda və «Yeni dərs»də tip dəyişəndə). Ad məlumdursa
     *  (doldurma — slotun öz müəllimi namizəd siyahısında olmaya bilər) sorğu göndərilmir. */
    function show(id, label) {
        initializing = true;
        pick.reset();
        hidden.value = id || "";
        if (id && label) {
            requestSeq++; // gecikən köhnə ad sorğusu bu seçimin üstünə yazmasın
            pick.setValue(id, label);
            initializing = false;
            return;
        }
        resolveLabel(id || "");
    }

    document.addEventListener("jd:lesson-modal-open", function (event) {
        if (event.target !== modal) {
            return;
        }
        var editData = event.detail;
        if (editData) {
            // Dərsin müəllimi slotun öz müəllimi ola bilər (namizəd siyahısında yoxdur) — ad doldurma adasından.
            var id = editData.instructor || hidden.value || "";
            var prefill = window.EMSJournalLessonPrefill;
            show(id, (id && prefill && typeof prefill.labelFor === "function" && prefill.labelFor(id)) || "");
        } else {
            show(hidden.value || "", hidden.dataset.jdLabel || "");
        }
    });

    window.EMSJournalLessonTeacher = { show: show };
})();
