/* Source: exams/teacher/question_submission_form.html
   Meta sahələri (başlıq/dil/fənn/qeyd + ÇOX-seçimli qrup) form="saveForm"-a
   bağlıdır. Preview (birinci forma) POST olunanda itməsinlər deyə dəyərləri
   preview formuna hidden input kimi köçürür + localStorage-da saxlayır.
   Extracted from an inline <script> for CSP (no unsafe-inline). */
(function () {
    var STORAGE_KEY = "qsub_meta_v2";

    function singleFields() {
        return Array.prototype.slice.call(document.querySelectorAll("[data-qsub-meta]"));
    }
    function multiBoxes() {
        return Array.prototype.slice.call(document.querySelectorAll('[data-qsub-meta-multi]'));
    }

    function saveMeta() {
        try {
            var data = { _single: {}, _multi: [] };
            singleFields().forEach(function (f) { if (f.name) data._single[f.name] = f.value; });
            multiBoxes().forEach(function (b) { if (b.checked) data._multi.push(b.value); });
            localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
        } catch (e) { /* ötür */ }
    }

    function restoreMeta() {
        try {
            var data = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
            if (!data) return;
            singleFields().forEach(function (f) {
                if (f.name && !f.value && data._single && data._single[f.name]) f.value = data._single[f.name];
            });
            var anyChecked = multiBoxes().some(function (b) { return b.checked; });
            if (!anyChecked && data._multi && data._multi.length) {
                multiBoxes().forEach(function (b) { if (data._multi.indexOf(b.value) !== -1) b.checked = true; });
            }
        } catch (e) { /* ötür */ }
    }

    restoreMeta();
    singleFields().concat(multiBoxes()).forEach(function (f) {
        f.addEventListener("input", saveMeta);
        f.addEventListener("change", saveMeta);
    });

    var previewForm = document.querySelector(".split-layout");
    if (previewForm) {
        previewForm.addEventListener("submit", function () {
            saveMeta();
            // Köhnə mirror-ları təmizlə.
            Array.prototype.slice.call(previewForm.querySelectorAll('[data-qsub-meta-mirror]'))
                .forEach(function (h) { h.remove(); });
            function mirror(name, value) {
                var h = document.createElement("input");
                h.type = "hidden"; h.name = name; h.value = value;
                h.setAttribute("data-qsub-meta-mirror", name);
                previewForm.appendChild(h);
            }
            singleFields().forEach(function (f) { if (f.name) mirror(f.name, f.value); });
            multiBoxes().forEach(function (b) { if (b.checked) mirror(b.name, b.value); });
        });
    }

    // Göndəriş yola düşəndə saxlanmış meta təmizlənir.
    var saveForm = document.getElementById("saveForm");
    if (saveForm) {
        saveForm.addEventListener("submit", function () {
            try { localStorage.removeItem(STORAGE_KEY); } catch (e) { /* ötür */ }
        });
    }
})();
