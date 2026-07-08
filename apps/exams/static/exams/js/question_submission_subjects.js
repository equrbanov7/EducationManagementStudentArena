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
        var groupBoxes = Array.prototype.slice.call(
            document.querySelectorAll("[data-qsub-group-checkbox], [data-qsub-meta-multi][name='group_ids']")
        );
        if (!dataEl || !subjectSelect || (!groupSelect && groupBoxes.length === 0)) {
            return;
        }

        var map = {};
        try {
            map = JSON.parse(dataEl.textContent || "{}") || {};
        } catch (err) {
            map = {};
        }

        var placeholderNoGroup = (
            subjectSelect.getAttribute("data-no-group-text") ||
            subjectSelect.getAttribute("data-noGroup-text") ||
            ""
        ).trim();
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

        function groupHasSubject(groupId, subjectValue) {
            var subjects = (groupId && map[String(groupId)]) || [];
            if (!subjectValue) {
                return true;
            }
            return subjects.some(function (subject) {
                return String(subject.value) === String(subjectValue);
            });
        }

        function syncGroupBoxes() {
            var selectedSubject = subjectSelect.value || "";
            groupBoxes.forEach(function (box) {
                var allowed = groupHasSubject(box.value, selectedSubject);
                var chip = box.closest(".qsubm-chip");
                box.disabled = !allowed;
                if (!allowed) {
                    box.checked = false;
                }
                if (chip) {
                    chip.classList.toggle("is-disabled", !allowed);
                }
            });
        }

        var initialPreselect = subjectSelect.getAttribute("data-initial-subject") || "";
        if (groupSelect) {
            populate(groupSelect.value, initialPreselect);
            groupSelect.addEventListener("change", function () {
                populate(groupSelect.value, "");
            });
        }
        if (groupBoxes.length) {
            syncGroupBoxes();
            subjectSelect.addEventListener("change", syncGroupBoxes);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
