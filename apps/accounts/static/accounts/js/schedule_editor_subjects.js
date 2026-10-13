/* Cədvəl redaktoru — «Xanaya dərs qoy» dialoqunun SERVERDƏN gələn siyahıları.

   1) FƏNN siyahısı müəllimə görə yenilənir (sahib 2026-09-21: «müəllimi seçirəm,
      fənni görünmür») — `action=options`.
   2) «Dərsi aparan müəllim» (bölünmüş tədris, 2026-09-25): siyahı seçilmiş fənn +
      qrup açılışını APARA BİLƏNLƏRDƏN gəlir — `action=slot_teachers`; default
      «Jurnal sahibi» (boş dəyər). Seçim `check`/`save`-də SERVERDƏ yoxlanır — burada
      heç nə hesablanmır. Dialoq açılanda (redaktə) kartın `data-slot-instructor-*`
      dəyəri DƏRHAL yazılır ki, əsas skriptin ilk `check`-i elə həmin müəllimlə getsin.

   `schedule_editor.js`-dən ayrıdır (fayl həcmi qapısı); onun daxili
   funksiyalarına toxunmur: kök `[data-sedit-root]` (data-editor-url,
   data-group-id, data-period-id) və sahələr `[data-sedit-field]` DOM-dan
   oxunur, sorğular `EMSCore.fetchJSON` ilə gedir, dəyər dəyişəndə seçiciyə
   `change` hadisəsi göndərilir ki, əsas skriptin delegasiyalı `runCheck`-i işə
   düşsün.  AJAX-safe: `EMSDelegate` ilə bağlanır, kök yoxdursa heç nə etmir.

   MÜƏLLİM GÖRÜNÜŞÜ (2026-10-14): qrup dialoqun «Qrup» sahəsindən oxunur (`group_id`);
   qrup dəyişəndə fənn + «Dərsi aparan müəllim» siyahıları yenilənir, dialoq açılanda
   fənn siyahısı kartın fənnini SAXLAYARAQ (qrup + jurnal sahibi ilə) yenidən qurulur. */
(function () {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE || !window.EMSCore) {
        return;
    }

    var slotTeacherRequest = 0;

    function root() {
        return document.querySelector("[data-sedit-root]");
    }

    function field(name) {
        var dialog = document.getElementById("seditCell");
        return dialog ? dialog.querySelector("[data-sedit-field='" + name + "']") : null;
    }

    function groupId(host) {
        var picked = field("group_id");
        return picked ? picked.value || "" : host.getAttribute("data-group-id") || "";
    }

    function post(host, payload) {
        payload.group_id = groupId(host);
        payload.period_id = host.getAttribute("data-period-id") || "";
        return window.EMSCore.fetchJSON(host.getAttribute("data-editor-url"), { method: "POST", data: payload });
    }

    function refreshSelect(select) {
        if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
            window.EMSBootstrapSelect.refresh(select);
        }
    }

    function addOption(select, value, label) {
        var option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        select.appendChild(option);
    }

    /* `silent` — dialoq açılışında: «Dərsi aparan müəllim»i sıfırlamamaq üçün fənnin
       `change`-i göndərilmir; yalnız yoxlama (runCheck) üçün saat sahəsi «dəyişir». */
    function reloadSubjects(want, silent) {
        var host = root();
        var select = field("subject_id");
        var teacher = field("instructor_id");
        if (!host || !select || !teacher) {
            return;
        }
        post(host, { action: "options", instructor_id: teacher.value || "" })
            .then(function (data) {
                if (!data || !data.ok || !Array.isArray(data.subjects)) {
                    return;
                }
                var current = want || select.value;
                select.textContent = "";
                data.subjects.forEach(function (row) {
                    addOption(select, row.id, row.code + " — " + row.name);
                });
                /* Cari fənn yeni siyahıda varsa seçili qalır. */
                if (current && select.querySelector("option[value='" + current + "']")) {
                    select.value = current;
                }
                refreshSelect(select);
                var target = silent ? field("time_slot") : select;
                if (target) {
                    target.dispatchEvent(new Event("change", { bubbles: true }));
                }
            })
            .catch(function () {});
    }

    /* ── «Dərsi aparan müəllim» ───────────────────────────────────────────── */

    /* Seçicini yenidən qurur: «Jurnal sahibi[ — ad]» + serverin siyahısı. `keep`
       ({value, label}) siyahıda yoxdursa da saxlanır (redaktə olunan slotun cari
       müəllimi — serverin yoxlaması qərar verəcək). */
    function fillSlotTeachers(select, ownerName, rows, keep) {
        var base = select.getAttribute("data-owner-label") || "";
        select.textContent = "";
        addOption(select, "", ownerName ? base + " — " + ownerName : base);
        (rows || []).forEach(function (row) {
            addOption(select, row.id, row.name);
        });
        if (keep && keep.value && !select.querySelector("option[value='" + keep.value + "']")) {
            addOption(select, keep.value, keep.label || keep.value);
        }
        select.value = keep && keep.value ? keep.value : "";
        refreshSelect(select);
    }

    function reloadSlotTeachers(keepUnknown) {
        var host = root();
        var select = field("slot_instructor_id");
        var subject = field("subject_id");
        var teacher = field("instructor_id");
        if (!host || !select || !subject) {
            return;
        }
        var ticket = (slotTeacherRequest += 1);
        var payload = {
            action: "slot_teachers",
            subject_id: subject.value || "",
            instructor_id: teacher ? teacher.value : "",
        };
        post(host, payload)
            .then(function (data) {
                if (ticket !== slotTeacherRequest || !data || !data.ok) {
                    return;             /* köhnə cavab — daha yeni sorğu gedib */
                }
                var before = select.value;
                var option = select.options[select.selectedIndex];
                var rows = Array.isArray(data.teachers) ? data.teachers : [];
                var known = rows.some(function (row) {
                    return row.id === before;
                });
                var keep = null;
                if (before && (known || keepUnknown)) {
                    keep = { value: before, label: option ? option.textContent : "" };
                }
                fillSlotTeachers(select, data.owner && data.owner.name, rows, keep);
                if (select.value !== before) {
                    select.dispatchEvent(new Event("change", { bubbles: true }));
                }
            })
            .catch(function () {});
    }

    /* Dialoq açılanda: yeni xana → «Jurnal sahibi»; redaktə → kartın cari müəllimi. */
    DELEGATE.on("ems:overlay:open", "#seditCell", function () {
        var select = field("slot_instructor_id");
        var slotField = field("slot_id");
        if (!root() || !select) {
            return;
        }
        var slotId = slotField ? slotField.value : "";
        var card = slotId ? document.querySelector("[data-sedit-slot='" + slotId + "']") : null;
        var value = card ? card.getAttribute("data-slot-instructor-id") || "" : "";
        var label = card ? card.getAttribute("data-slot-instructor-name") || "" : "";
        fillSlotTeachers(select, "", [], value ? { value: value, label: label } : null);
        if (root().getAttribute("data-view") === "teacher" && field("group_id")) {
            /* Fənn siyahısı qrup + jurnal sahibinə görə; kartın fənni itməsin. */
            reloadSubjects(card ? card.getAttribute("data-subject-id") || "" : "", true);
        }
        reloadSlotTeachers(true);
    });

    DELEGATE.on("change", "[data-sedit-field='group_id']", function () {
        if (root()) {
            reloadSubjects();
            reloadSlotTeachers(false);
        }
    });

    DELEGATE.on("change", "[data-sedit-field='instructor_id']", function () {
        if (root()) {
            reloadSubjects();
        }
    });

    DELEGATE.on("change", "[data-sedit-field='subject_id']", function () {
        if (root()) {
            reloadSlotTeachers(false);
        }
    });
})();
