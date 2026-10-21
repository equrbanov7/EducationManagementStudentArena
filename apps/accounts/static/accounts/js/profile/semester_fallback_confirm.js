/* =========================================================================
   «Semestr açılışı» → «Plandan açılış yarat»: ən son planın TƏSDİQ siyahısı (rəy 2026-10-21, R06).

   AXIN
   ----
   1. Dialoq ortaq `teaching_office.js` ilə göndərilir. Qəbul ili üçün planı olmayan qrup varsa server
      HEÇ NƏ YAZMADAN 409 `fallback_confirmation_required` + `fallbacks` siyahısı qaytarır; ortaq
      handler formada `tof:submit-error` hadisəsi buraxır.
   2. Bu fayl siyahını dialoqdakı `[data-tof-fallback-confirm]` blokuna çəkir: hər qrup üçün
      «Təsdiq edirəm» çek-qutusu (`name="confirm_fallback"`, `data-tof-list`) + «Hamısını təsdiq
      edirəm»; gizli `fallback_reviewed=1` qoyulur.
   3. İkinci göndərişdə yalnız işarələnən qruplar ən son plandan açılır; qalanları SERVER atlayır və
      nəticədə adı ilə göstərir (qapı yalnız kliyentdə deyil).

   Semestr / ixtisas dəyişəndə və dialoq yenidən açılanda siyahı sıfırlanır (növbəti göndəriş yenidən
   önizləmə verir). Server mətni HTML kimi şərh OLUNMUR — hamısı `textContent`.

   AJAX-SAFE: yalnız sənəd səviyyəli dinləyicilər (bir dəfə, `window.EMSSemesterFallback` qoruyucusu).
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSSemesterFallback) {
        return;
    }

    var ERROR_CODE = "fallback_confirmation_required";

    function boxOf(form) {
        return form ? form.querySelector("[data-tof-fallback-confirm]") : null;
    }

    function reviewedField(form) {
        return form ? form.querySelector('input[name="fallback_reviewed"]') : null;
    }

    function cell(tag, text) {
        var node = document.createElement(tag);
        node.textContent = text === null || text === undefined ? "" : String(text);
        return node;
    }

    function syncAll(box) {
        var all = box.querySelector("[data-tof-fallback-all]");
        var boxes = box.querySelectorAll('input[name="confirm_fallback"]');
        var checked = 0;
        for (var i = 0; i < boxes.length; i += 1) {
            if (boxes[i].checked) {
                checked += 1;
            }
        }
        if (all) {
            all.checked = boxes.length > 0 && checked === boxes.length;
            all.indeterminate = checked > 0 && checked < boxes.length;
        }
    }

    function reset(form) {
        var box = boxOf(form);
        var field = reviewedField(form);
        if (field) {
            field.value = "";
        }
        if (!box) {
            return;
        }
        box.hidden = true;
        var head = box.querySelector("[data-tof-fallback-head]");
        var rows = box.querySelector("[data-tof-fallback-rows]");
        var message = box.querySelector("[data-tof-fallback-message]");
        if (head) {
            head.textContent = "";
        }
        if (rows) {
            rows.textContent = "";
        }
        if (message) {
            message.textContent = "";
        }
        var all = box.querySelector("[data-tof-fallback-all]");
        if (all) {
            all.checked = false;
            all.indeterminate = false;
        }
    }

    function render(form, payload) {
        var box = boxOf(form);
        var items = (payload && payload.fallbacks) || [];
        if (!box || !items.length) {
            return false;
        }
        reset(form);
        var data = box.dataset;
        var head = box.querySelector("[data-tof-fallback-head]");
        var rows = box.querySelector("[data-tof-fallback-rows]");
        var message = box.querySelector("[data-tof-fallback-message]");
        if (message) {
            message.textContent = (payload && payload.message) || "";
        }
        var headRow = document.createElement("tr");
        [data.labelConfirm, data.labelGroup, data.labelYear, data.labelReason, data.labelPlan, data.labelPlanYear].forEach(
            function (label) {
                var th = cell("th", label || "");
                th.setAttribute("scope", "col");
                headRow.appendChild(th);
            }
        );
        head.appendChild(headRow);
        items.forEach(function (item, index) {
            var tr = document.createElement("tr");
            var pick = document.createElement("td");
            var label = document.createElement("label");
            label.className = "tof-fallback__pick";
            var input = document.createElement("input");
            input.type = "checkbox";
            input.name = "confirm_fallback";
            input.value = String(item.group_id || "");
            input.setAttribute("data-tof-list", "1");
            input.id = "tof-fallback-" + index;
            label.appendChild(input);
            label.appendChild(cell("span", data.labelConfirm || ""));
            pick.appendChild(label);
            tr.appendChild(pick);
            var group = cell("th", item.group || "");
            group.setAttribute("scope", "row");
            tr.appendChild(group);
            tr.appendChild(cell("td", item.admission_year ? item.admission_year : data.labelUnknown || "—"));
            tr.appendChild(cell("td", item.reason_label || ""));
            var plan = item.plan_label || "";
            if (item.plan_version) {
                plan += " · v" + item.plan_version;
            }
            tr.appendChild(cell("td", plan));
            tr.appendChild(cell("td", item.plan_year || "—"));
            rows.appendChild(tr);
        });
        var field = reviewedField(form);
        if (field) {
            field.value = "1";
        }
        box.hidden = false;
        syncAll(box);
        return true;
    }

    document.addEventListener("tof:submit-error", function (event) {
        var form = event.target;
        var payload = event.detail && event.detail.payload;
        if (!form || !payload || payload.error !== ERROR_CODE) {
            return;
        }
        if (render(form, payload)) {
            // Xəta qutusu yox — siyahının öz izahı var (dialoqda iki eyni mətn olmasın).
            var errorBox = form.querySelector("[data-ems-form-error]");
            if (errorBox) {
                errorBox.textContent = "";
                errorBox.hidden = true;
            }
        }
    });

    document.addEventListener("change", function (event) {
        var target = event.target;
        if (!target || !target.closest) {
            return;
        }
        var box = target.closest("[data-tof-fallback-confirm]");
        if (box) {
            if (target.hasAttribute("data-tof-fallback-all")) {
                var boxes = box.querySelectorAll('input[name="confirm_fallback"]');
                for (var i = 0; i < boxes.length; i += 1) {
                    boxes[i].checked = target.checked;
                }
            }
            syncAll(box);
            return;
        }
        // Semestr / ixtisas dəyişdi → köhnə təsdiq etibarsızdır, növbəti göndəriş yenidən önizləmə verir.
        var form = target.closest("form");
        if (form && boxOf(form) && (target.name === "semester_number" || target.name === "programs")) {
            reset(form);
        }
    });

    document.addEventListener(
        "click",
        function (event) {
            var opener = event.target && event.target.closest ? event.target.closest("[data-tof-open]") : null;
            if (!opener) {
                return;
            }
            var dialog = document.getElementById(opener.getAttribute("data-tof-open"));
            var form = dialog ? dialog.querySelector("form") : null;
            if (boxOf(form)) {
                reset(form);
            }
        },
        true
    );

    window.EMSSemesterFallback = { render: render, reset: reset };
})(window, document);
