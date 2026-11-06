/* «Lab qrupları» kabinet bölməsi — iş sahəsinin davranışı (sahib 2026-11-07).
   Şablon: accounts/profile/sections/lab_groups/_workspace.html (data-atributlar: [data-lgx-ws]).

   * seçim: tələbə checkbox-u, sütunun «hamısını seç»-i (yalnız görünən və kilidsiz sətirlər), sayğac;
     «Köçür» yalnız ən azı bir tələbə + hədəf qrup seçiləndə açılır;
   * axtarış: adlara görə sətirləri gizlədir (az hərfləri, registr / diakritik fərqi sayılmır), seçim qalır;
   * sürüşdür-at: kilidsiz sətri başqa sütunun üzərinə atmaq = həmin qrupa köçürmək (sətir seçilibsə — bütün seçim);
   * yaratmaq / ad / silmək (EMSConfirm ilə təsdiq, `confirm=1`);
   * hər yazı EMSCore.fetchJSON ilə JSON endpoint-inə (data-action-url) gedir; uğurdan sonra mesaj (EMSToast) və
     bölmə yerində yenilənir (EMSProfileLoadSection). Server hər şeyi yenidən yoxlayır (səlahiyyət, kilid, bağlı jurnal).
   AJAX-safe: hadisələr yalnız EMSDelegate ilə, ilkin vəziyyət EMSReady ilə (idempotent). */
(function () {
    "use strict";

    var WS = "[data-lgx-ws]";
    var SECTION = "lab-groups";
    var DRAG_TYPE = "application/x-ems-lab-enrollments";
    var dragged = null;

    function attr(el, name) {
        return (el && el.getAttribute(name)) || "";
    }

    function normalize(text) {
        return String(text || "")
            .toLocaleLowerCase("az")
            .normalize("NFD")
            .replace(/[̀-ͯ]/g, "")
            .replace(/ı/g, "i")
            .trim();
    }

    function readOnly(ws) {
        return attr(ws, "data-readonly") === "1";
    }

    function boxes(scope, onlyVisible) {
        var found = [];
        scope.querySelectorAll("[data-lgx-pick]").forEach(function (box) {
            if (box.disabled) return;
            if (onlyVisible && box.closest("[data-lgx-row]").hidden) return;
            found.push(box);
        });
        return found;
    }

    function picked(ws) {
        return boxes(ws, false).filter(function (box) { return box.checked; });
    }

    function syncColumn(col) {
        var all = col.querySelector("[data-lgx-col-all]");
        if (!all) return;
        var list = boxes(col, true);
        var checked = list.filter(function (box) { return box.checked; }).length;
        all.checked = list.length > 0 && checked === list.length;
        all.indeterminate = checked > 0 && checked < list.length;
        all.disabled = list.length === 0;
    }

    function refresh(ws) {
        if (!ws) return;
        var selected = picked(ws);
        ws.querySelectorAll("[data-lgx-row]").forEach(function (row) {
            var box = row.querySelector("[data-lgx-pick]");
            row.classList.toggle("is-picked", !!(box && box.checked));
        });
        var counter = ws.querySelector("[data-lgx-selected]");
        if (counter) counter.textContent = String(selected.length);
        var target = ws.querySelector("[data-lgx-target]");
        var move = ws.querySelector("[data-lgx-move]");
        if (move) move.disabled = !(selected.length > 0 && target && target.value);
        var clear = ws.querySelector("[data-lgx-clear]");
        if (clear) clear.hidden = selected.length === 0;
        ws.querySelectorAll("[data-lgx-col]").forEach(syncColumn);
    }

    function filter(ws, query) {
        var wanted = normalize(query);
        ws.querySelectorAll("[data-lgx-row]").forEach(function (row) {
            row.hidden = wanted !== "" && normalize(attr(row, "data-lgx-name")).indexOf(wanted) === -1;
        });
        refresh(ws);
    }

    function toast(text, level) {
        if (!text) return;
        if (window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(text, level || "success");
        }
    }

    function reloadSection() {
        if (typeof window.EMSProfileLoadSection === "function") {
            window.EMSProfileLoadSection(SECTION, window.location.href);
        } else {
            window.location.reload();
        }
    }

    function errorText(ws, err) {
        var payload = err && err.payload;
        if (payload && typeof payload === "object" && (payload.message || payload.detail)) {
            return payload.message || payload.detail;
        }
        return attr(ws, "data-msg-generic");
    }

    /* Bir əməl: FormData → JSON endpoint; uğurda mesajlar + bölmənin yenilənməsi. */
    function send(ws, fields) {
        if (!ws || readOnly(ws) || ws.getAttribute("data-busy") === "1") return Promise.resolve(false);
        var body = new window.FormData();
        Object.keys(fields).forEach(function (key) {
            var value = fields[key];
            (Array.isArray(value) ? value : [value]).forEach(function (item) { body.append(key, item); });
        });
        ws.setAttribute("data-busy", "1");
        ws.classList.add("is-busy");
        return window.EMSCore.fetchJSON(attr(ws, "data-action-url"), { method: "POST", body: body })
            .then(function (payload) {
                ((payload && payload.messages) || []).forEach(function (item) { toast(item.text, item.level); });
                reloadSection();
                return true;
            })
            .catch(function (err) {
                toast(errorText(ws, err), "error");
                return false;
            })
            .then(function (ok) {
                ws.removeAttribute("data-busy");
                ws.classList.remove("is-busy");
                return ok;
            });
    }

    function assign(ws, target, ids) {
        if (!ids.length) {
            toast(attr(ws, "data-msg-pick"), "warning");
            return Promise.resolve(false);
        }
        if (!target) {
            toast(attr(ws, "data-msg-target"), "warning");
            return Promise.resolve(false);
        }
        return send(ws, { action: "assign", target: target, enrollment: ids });
    }

    // ── Seçim, axtarış ──────────────────────────────────────────────────────
    window.EMSDelegate.on("change", WS + " [data-lgx-pick]", function (event, box) {
        refresh(box.closest(WS));
    });

    window.EMSDelegate.on("change", WS + " [data-lgx-col-all]", function (event, all) {
        boxes(all.closest("[data-lgx-col]"), true).forEach(function (box) { box.checked = all.checked; });
        refresh(all.closest(WS));
    });

    window.EMSDelegate.on("change", WS + " [data-lgx-target]", function (event, select) {
        refresh(select.closest(WS));
    });

    window.EMSDelegate.on("input", WS + " [data-lgx-search]", function (event, input) {
        filter(input.closest(WS), input.value);
    });

    window.EMSDelegate.on("click", WS + " [data-lgx-clear]", function (event, button) {
        var ws = button.closest(WS);
        picked(ws).forEach(function (box) { box.checked = false; });
        refresh(ws);
    });

    // ── Köçür ───────────────────────────────────────────────────────────────
    window.EMSDelegate.on("click", WS + " [data-lgx-move]", function (event, button) {
        var ws = button.closest(WS);
        var target = ws.querySelector("[data-lgx-target]");
        assign(ws, target ? target.value : "", picked(ws).map(function (box) { return box.value; }));
    });

    // ── Yaratmaq / ad ───────────────────────────────────────────────────────
    window.EMSDelegate.on("submit", WS + " [data-lgx-create-form]", function (event, form) {
        event.preventDefault();
        var name = form.querySelector("[name=name]");
        send(form.closest(WS), { action: "create", name: name ? name.value.trim() : "" });
    });

    window.EMSDelegate.on("click", WS + " [data-lgx-rename-toggle]", function (event, button) {
        var col = button.closest("[data-lgx-col]");
        var form = col && col.querySelector("[data-lgx-rename-form]");
        if (!form) return;
        form.hidden = !form.hidden;
        if (!form.hidden) {
            var input = form.querySelector("[name=name]");
            if (input) {
                input.focus();
                input.select();
            }
        }
    });

    window.EMSDelegate.on("click", WS + " [data-lgx-rename-cancel]", function (event, button) {
        var form = button.closest("[data-lgx-rename-form]");
        if (form) form.hidden = true;
    });

    window.EMSDelegate.on("submit", WS + " [data-lgx-rename-form]", function (event, form) {
        event.preventDefault();
        send(form.closest(WS), {
            action: "rename",
            group: form.querySelector("[name=group]").value,
            name: form.querySelector("[name=name]").value.trim(),
        });
    });

    // ── Silmək (təsdiqlə) ───────────────────────────────────────────────────
    window.EMSDelegate.on("click", WS + " [data-lgx-delete]", function (event, button) {
        var ws = button.closest(WS);
        var body = attr(ws, "data-msg-delete-body")
            .replace("%(label)s", attr(button, "data-label"))
            .replace("%(n)s", attr(button, "data-members") || "0");
        // EMSConfirm qlobaldır (base.html); Bootstrap yoxdursa onun özü ehtiyat yoluna düşür.
        if (!window.EMSConfirm || typeof window.EMSConfirm.open !== "function") return;
        window.EMSConfirm.open({
            title: attr(ws, "data-msg-delete-title"),
            body: body,
            confirmLabel: attr(ws, "data-msg-delete-ok"),
            danger: true,
        }).then(function (ok) {
            if (ok) send(ws, { action: "delete", group: attr(button, "data-group"), confirm: "1" });
        });
    });

    // ── Sürüşdür-at ─────────────────────────────────────────────────────────
    function clearDrop(ws) {
        if (!ws) return;
        ws.querySelectorAll(".is-drop").forEach(function (col) { col.classList.remove("is-drop"); });
    }

    window.EMSDelegate.on("dragstart", WS + " [data-lgx-row][draggable=true]", function (event, row) {
        var ws = row.closest(WS);
        if (readOnly(ws)) return;
        var own = row.querySelector("[data-lgx-pick]");
        var ids = own && own.checked
            ? picked(ws).map(function (box) { return box.value; })
            : [attr(row, "data-enrollment")];
        dragged = { ws: ws, ids: ids, from: attr(row.closest("[data-lgx-col]"), "data-lgx-col") };
        row.classList.add("is-dragging");
        if (event.dataTransfer) {
            event.dataTransfer.effectAllowed = "move";
            try {
                event.dataTransfer.setData(DRAG_TYPE, ids.join(","));
                event.dataTransfer.setData("text/plain", ids.join(","));
            } catch (ignore) { /* köhnə brauzer — `dragged` kifayətdir */ }
        }
    });

    window.EMSDelegate.on("dragend", WS + " [data-lgx-row]", function (event, row) {
        row.classList.remove("is-dragging");
        clearDrop(row.closest(WS));
        dragged = null;
    });

    window.EMSDelegate.on("dragover", WS + " [data-lgx-col]", function (event, col) {
        if (!dragged || dragged.ws !== col.closest(WS) || attr(col, "data-lgx-col") === dragged.from) return;
        event.preventDefault();
        if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
        if (!col.classList.contains("is-drop")) {
            clearDrop(dragged.ws);
            col.classList.add("is-drop");
        }
    });

    window.EMSDelegate.on("dragleave", WS + " [data-lgx-col]", function (event, col) {
        if (!col.contains(event.relatedTarget)) col.classList.remove("is-drop");
    });

    window.EMSDelegate.on("drop", WS + " [data-lgx-col]", function (event, col) {
        if (!dragged || dragged.ws !== col.closest(WS)) return;
        event.preventDefault();
        var move = dragged;
        dragged = null;
        clearDrop(move.ws);
        var target = attr(col, "data-lgx-col");
        if (target && target !== move.from) assign(move.ws, target, move.ids);
    });

    window.EMSReady(function () {
        document.querySelectorAll(WS).forEach(refresh);
    });
})();
