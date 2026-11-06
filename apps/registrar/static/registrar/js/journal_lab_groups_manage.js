/* «Lab qrupları» ekranı — seçim rahatlığı (sahib 2026-11-06; journal_lab_groups.html).

   Ekran JS-siz də işləyir (adi POST formları, server hər şeyi yoxlayır). Bu fayl yalnız:
   * seçilən tələbə sayını göstərir və hədəf qrup + ən azı bir tələbə seçilməyincə «Köçür»-ü bağlayır;
   * bölmənin başlığındakı checkbox həmin bölmənin görünən (və bağlı olmayan) tələbələrini seçir;
   * axtarış sətri adlara görə sətirləri gizlədir (seçim qalır).
   AJAX-safe: hadisələr yalnız EMSDelegate ilə (hər «hadisə|selektor» cütü fərqli), ilkin vəziyyət EMSReady ilə. */
(function () {
    "use strict";

    var ROOT = "[data-lgm]";

    function picks(scope, onlyVisible) {
        var found = [];
        scope.querySelectorAll("[data-lgm-pick]").forEach(function (box) {
            if (box.disabled) return;
            if (onlyVisible && box.closest("[data-lgm-row]").hidden) return;
            found.push(box);
        });
        return found;
    }

    function syncBucket(bucket) {
        var all = bucket.querySelector("[data-lgm-bucket-all]");
        if (!all) return;
        var boxes = picks(bucket, true);
        var checked = boxes.filter(function (box) { return box.checked; }).length;
        all.checked = boxes.length > 0 && checked === boxes.length;
        all.indeterminate = checked > 0 && checked < boxes.length;
        all.disabled = boxes.length === 0;
    }

    function refresh(form) {
        if (!form) return;
        var selected = picks(form, false).filter(function (box) { return box.checked; }).length;
        var counter = form.querySelector("[data-lgm-selected]");
        if (counter) counter.textContent = String(selected);
        var target = form.querySelector("[data-lgm-target]");
        var submit = form.querySelector("[data-lgm-submit]");
        if (submit) submit.disabled = !(selected > 0 && target && target.value);
        form.querySelectorAll("[data-lgm-bucket]").forEach(syncBucket);
    }

    function normalize(text) {
        return String(text || "")
            .toLocaleLowerCase("az")
            .normalize("NFD")
            .replace(/[̀-ͯ]/g, "")
            .replace(/ı/g, "i")
            .trim();
    }

    function filter(root, query) {
        var wanted = normalize(query);
        root.querySelectorAll("[data-lgm-row]").forEach(function (row) {
            row.hidden = wanted !== "" && normalize(row.getAttribute("data-lgm-name")).indexOf(wanted) === -1;
        });
        refresh(root.querySelector("[data-lgm-assign-form]"));
    }

    window.EMSDelegate.on("change", ROOT + " [data-lgm-pick]", function (event, box) {
        refresh(box.closest("[data-lgm-assign-form]"));
    });

    window.EMSDelegate.on("change", ROOT + " [data-lgm-bucket-all]", function (event, all) {
        var bucket = all.closest("[data-lgm-bucket]");
        picks(bucket, true).forEach(function (box) { box.checked = all.checked; });
        refresh(all.closest("[data-lgm-assign-form]"));
    });

    window.EMSDelegate.on("change", ROOT + " [data-lgm-target]", function (event, select) {
        refresh(select.closest("[data-lgm-assign-form]"));
    });

    window.EMSDelegate.on("input", ROOT + " [data-lgm-search]", function (event, input) {
        filter(input.closest(ROOT), input.value);
    });

    window.EMSReady(function () {
        document.querySelectorAll(ROOT + " [data-lgm-assign-form]").forEach(refresh);
    });
})();
