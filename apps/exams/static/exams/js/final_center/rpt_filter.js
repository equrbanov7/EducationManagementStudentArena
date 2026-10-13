/* Hesabat filtri — avtomatik göndəriş + skeleton yükləmə.

   "Filtrlə" düyməsi yoxdur: seçim dəyişən kimi forma göndərilir. Mətn/tarix
   sahələri debounce ilə gedir ki, hər hərfdə sorğu atılmasın. Göndəriş anında
   nəticə bloku skeleton-la əvəz olunur — səhifə tam yenilənənə qədər boş
   ekran görünməsin.

   Excel yükləmə düyməsi İSTİSNADIR: o, səhifəni dəyişmir (fayl endirir), ona
   görə skeleton göstərilmir və avtomatik göndəriş onu tetikləmir. */

(function () {
    "use strict";

    function init() {
        var form = document.querySelector("[data-rpt-filter]");
        if (!form || form.dataset.rptBound === "1") return;
        form.dataset.rptBound = "1";

        var skeleton = document.querySelector("[data-rpt-skeleton]");
        var results = document.querySelector("[data-rpt-results]");
        var timer = null;
        var submitting = false;

        function showSkeleton() {
            if (skeleton) skeleton.hidden = false;
            if (results) results.hidden = true;
        }

        function submitNow() {
            if (submitting) return;
            submitting = true;
            showSkeleton();
            // Səhifə dəyişəndə `export` göndərilməməlidir — o, ayrıca düymədir.
            form.submit();
        }

        function scheduleSubmit(delay) {
            if (timer) clearTimeout(timer);
            timer = setTimeout(submitNow, delay);
        }

        // Select və tarix sahələri: dəyişən kimi dərhal.
        form.addEventListener("change", function (event) {
            var el = event.target;
            if (!el || el.name === "export") return;
            if (el.tagName === "SELECT" || el.type === "date") scheduleSubmit(0);
        });

        // Mətn axtarışı: vahid EMSSearchInput (2026-10-14: yazı dayananda 1500 ms,
        // ≥ 2 simvol, Enter dərhal, IME). Nəticə bloku skeletə çevrilmir (sakitcə
        // solur); yeni səhifədə fokus + kursor axtarış sahəsinə qayıdır.
        Array.prototype.forEach.call(form.querySelectorAll('input[type="search"], input[type="text"]'), function (el) {
            window.EMSSearchInput.bind(el, {
                onSearch: function () {
                    if (submitting) return;
                    submitting = true;
                    if (results) results.classList.add("ems-search-pending");
                    window.EMSSearchInput.submitForm(form, { input: el });
                }
            });
        });

        // Enter ilə dərhal (mətn sahələrində Enter-i EMSSearchInput idarə edir).
        form.addEventListener("keydown", function (event) {
            var t = event.target;
            if (t && window.EMSSearchInput.isTextField(t)) return;
            if (event.key === "Enter" && t && t.tagName === "INPUT") {
                event.preventDefault();
                if (timer) clearTimeout(timer);
                submitNow();
            }
        });

        // Excel düyməsi faylı endirir — skeleton qalıb səhifəni "yüklənir"
        // vəziyyətində dondurmasın.
        var exportBtn = form.querySelector('[name="export"]');
        if (exportBtn) {
            exportBtn.addEventListener("click", function () {
                if (timer) clearTimeout(timer);
                submitting = true;
                setTimeout(function () {
                    submitting = false;
                }, 1500);
            });
        }

        var reset = document.querySelector("[data-rpt-reset]");
        if (reset) reset.addEventListener("click", showSkeleton);

        // Geri düyməsi ilə qayıdanda bfcache köhnə skeleton vəziyyətini
        // saxlaya bilir — nəticəni geri qaytar.
        window.addEventListener("pageshow", function () {
            submitting = false;
            if (skeleton) skeleton.hidden = true;
            if (results) results.hidden = false;
        });
    }

    if (window.EMSReady) {
        window.EMSReady(init);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init, { once: true });
    } else {
        init();
    }
})();
