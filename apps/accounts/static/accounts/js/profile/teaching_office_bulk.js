/* =========================================================================
   Toplu sətir seçimi — ekran 06 «Qruplar» (dizayn handoff Mərhələ 2).

   NƏ EDİR
   -------
   * `[data-tof-bulk-item="<id>"]` xanalarını izləyir, sayğacı yeniləyir
     (`[data-tof-bulk-count]`) və toplu əməl düymələrini (`[data-tof-bulk-action]`)
     seçim boş olduqda DISABLED saxlayır (gizlətmir — handoff §4);
   * dialoq açılanda seçilmiş id-ləri həmin dialoqun formasına GİZLİ
     `ids` sahələri kimi yazır (server `request.POST.getlist("ids")` oxuyur).

   NƏ ETMİR
   --------
   POST, dialoq doldurma, fokus tələsi və səbəb sayğacı ORTAQ qatdadır
   (`teaching_office.js` + `static/js/ems_ui/overlay.js`) — təkrarlanmır.

   AJAX-SAFE: yalnız `EMSDelegate` (sənəd səviyyəli) + `EMSReady`;
   `[data-tof-bulk]` yoxdursa heç nə etmir.
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSTeachingOfficeBulk) {
        return;
    }

    function host() {
        return document.querySelector("[data-tof-bulk]");
    }

    function selectedIds() {
        var boxes = document.querySelectorAll("[data-tof-bulk-item]");
        var ids = [];
        for (var i = 0; i < boxes.length; i += 1) {
            if (boxes[i].checked) {
                ids.push(boxes[i].getAttribute("data-tof-bulk-item"));
            }
        }
        return ids;
    }

    function syncToolbar() {
        var root = host();
        if (!root) {
            return;
        }
        var ids = selectedIds();
        // Mətnlər ŞABLONDAN gəlir (data-atribut) — JS-də tərcümə saxlanılmır,
        // çünki xarici `.js` faylı Django template engine-dən keçmir.
        var counter = root.querySelector("[data-tof-bulk-count]");
        if (counter) {
            var empty = counter.getAttribute("data-tof-bulk-empty") || "";
            var template = counter.getAttribute("data-tof-bulk-selected") || "%d";
            counter.textContent = ids.length ? template.replace("%d", String(ids.length)) : empty;
        }
        var buttons = root.querySelectorAll("[data-tof-bulk-action]");
        for (var i = 0; i < buttons.length; i += 1) {
            buttons[i].disabled = ids.length === 0;
            buttons[i].setAttribute("aria-disabled", ids.length === 0 ? "true" : "false");
        }
    }

    window.EMSDelegate.on("change", "[data-tof-bulk-item]", function () {
        syncToolbar();
    });

    /* Seçilmiş id-lər forma GÖNDƏRİLƏN anda əlavə olunur.
     *
     * ⚠️ NİYƏ AÇILIŞDA DEYİL? Ortaq `teaching_office.js` dialoqu açanda bütün
     * `[name]` sahələrini `data-tof-prefill`-dən doldurur; siyahıda olmayan
     * sahə BOŞALDILIR — yəni açılışda yazılan `ids` dəyərləri silinərdi.
     * `submit` hadisəsinin CAPTURE fazası isə ortaq handler-dən (bubble) ƏVVƏL
     * işləyir, ona görə sıra deterministikdir. */
    document.addEventListener(
        "submit",
        function (event) {
            var form = event.target;
            if (!form || !form.closest || !form.closest("[data-tof-bulk-target]")) {
                return;
            }
            var stale = form.querySelectorAll('input[name="ids"]');
            for (var i = 0; i < stale.length; i += 1) {
                stale[i].parentNode.removeChild(stale[i]);
            }
            selectedIds().forEach(function (id) {
                var field = document.createElement("input");
                field.type = "hidden";
                field.name = "ids";
                field.value = id;
                form.appendChild(field);
            });
        },
        true
    );

    window.EMSReady(function () {
        syncToolbar();
    });

    window.EMSTeachingOfficeBulk = { selectedIds: selectedIds, sync: syncToolbar };
})(window, document);
