/* Sual göndərişi — fənn dropdown-unu seçilmiş qrupa görə skoplayır (Faza 1, bənd 4-5).
 * Məlumat mənbəyi: #qsubGroupsSubjects (json_script) = { groupId: [{value,label}, ...] }.
 * Qrup dəyişəndə fənn seçimləri həmin qrupun fənlərinə yenilənir. CSP-təhlükəsiz
 * (xarici fayl, inline yox). */
(function () {
    "use strict";

    function init() {
        var dataEl = document.getElementById("qsubGroupsSubjects");
        var subjectSelect = document.querySelector("[data-qsub-subject]");
        var groupSelect = document.getElementById("qsubGroup");
        if (!dataEl || !subjectSelect || !groupSelect) {
            return;
        }

        var map = {};
        try {
            map = JSON.parse(dataEl.textContent || "{}") || {};
        } catch (err) {
            map = {};
        }

        var placeholderNoGroup = (subjectSelect.getAttribute("data-noGroup-text") || "").trim();
        var placeholderEmpty = (subjectSelect.getAttribute("data-empty-text") || "").trim();
        var placeholderChoose = (subjectSelect.getAttribute("data-choose-text") || "").trim();
        // İlk render-dəki placeholder mətnini "qrup seçin" üçün ehtiyat kimi saxla.
        if (!placeholderNoGroup) {
            var firstOption = subjectSelect.querySelector('option[value=""]');
            placeholderNoGroup = firstOption ? firstOption.textContent : "";
        }

        function populate(groupId, preselect) {
            var subjects = (groupId && map[String(groupId)]) || [];
            subjectSelect.innerHTML = "";

            var placeholder = document.createElement("option");
            placeholder.value = "";
            if (!groupId) {
                placeholder.textContent = placeholderNoGroup;
            } else if (subjects.length === 0) {
                placeholder.textContent = placeholderEmpty || placeholderNoGroup;
            } else {
                placeholder.textContent = placeholderChoose || placeholderNoGroup;
            }
            subjectSelect.appendChild(placeholder);

            subjects.forEach(function (subject) {
                var option = document.createElement("option");
                option.value = subject.value;
                option.textContent = subject.label;
                if (preselect && String(preselect) === String(subject.value)) {
                    option.selected = true;
                }
                subjectSelect.appendChild(option);
            });
        }

        var initialPreselect = subjectSelect.getAttribute("data-initial-subject") || "";
        populate(groupSelect.value, initialPreselect);

        groupSelect.addEventListener("change", function () {
            populate(groupSelect.value, "");
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
