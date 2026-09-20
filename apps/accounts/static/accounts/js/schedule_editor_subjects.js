/* Cədvəl redaktoru — «Xanaya dərs qoy» dialoqunda FƏNN siyahısının müəllimə
   görə yenilənməsi (sahib 2026-09-21: «müəllimi seçirəm, fənni görünmür»).

   `schedule_editor.js`-dən ayrıdır (fayl həcmi qapısı); onun daxili
   funksiyalarına toxunmur: kök `[data-sedit-root]` (data-editor-url,
   data-group-id, data-period-id) və sahələr `[data-sedit-field]` DOM-dan
   oxunur, `action=options` sorğusu `EMSCore.fetchJSON` ilə gedir, sonra fənn
   seçicisinə `change` hadisəsi göndərilir ki, əsas skriptin delegasiyalı
   `runCheck`-i işə düşsün.  AJAX-safe: `EMSDelegate` ilə bağlanır, kök yoxdursa
   heç nə etmir. */
(function () {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE || !window.EMSCore) {
        return;
    }

    function root() {
        return document.querySelector("[data-sedit-root]");
    }

    function field(name) {
        var dialog = document.getElementById("seditCell");
        return dialog ? dialog.querySelector("[data-sedit-field='" + name + "']") : null;
    }

    function reloadSubjects() {
        var host = root();
        var select = field("subject_id");
        var teacher = field("instructor_id");
        if (!host || !select || !teacher) {
            return;
        }
        var payload = {
            action: "options",
            group_id: host.getAttribute("data-group-id") || "",
            period_id: host.getAttribute("data-period-id") || "",
            instructor_id: teacher.value || "",
        };
        window.EMSCore.fetchJSON(host.getAttribute("data-editor-url"), { method: "POST", data: payload })
            .then(function (data) {
                if (!data || !data.ok || !Array.isArray(data.subjects)) {
                    return;
                }
                var current = select.value;
                select.textContent = "";
                data.subjects.forEach(function (row) {
                    var option = document.createElement("option");
                    option.value = row.id;
                    option.textContent = row.code + " — " + row.name;
                    select.appendChild(option);
                });
                /* Cari fənn yeni siyahıda varsa seçili qalır. */
                if (current && select.querySelector("option[value='" + current + "']")) {
                    select.value = current;
                }
                if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
                    window.EMSBootstrapSelect.refresh(select);
                }
                select.dispatchEvent(new Event("change", { bubbles: true }));
            })
            .catch(function () {});
    }

    DELEGATE.on("change", "[data-sedit-field='instructor_id']", function () {
        if (root()) {
            reloadSubjects();
        }
    });
})();
