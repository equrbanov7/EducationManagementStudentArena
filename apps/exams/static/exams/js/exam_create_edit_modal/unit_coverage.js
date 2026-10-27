/* Qrup imtahanın fənnini keçmir — xəbərdarlıq modalı + məcburi əlavə (sahib 2026-10-27).

   «Giriş» addımında reyestr qrupu seçiləndə (və fənn / kateqoriya dəyişəndə) `exams:unit_journal_coverage`
   çağırılır. Qrupun ən azı bir tələbəsi fənnin cari semestr jurnalında yoxdursa sehrbazın içində modal açılır:
   «Qrupu çıxar» (seçimdən çıxarır) və ya səbəb (≥ N simvol) yazaraq «Yenə də əlavə et». Məcburi əlavələr gizli
   `forced_units` sahəsinə JSON {qrup_id: səbəb} kimi yazılır. Server avtoritetdir — səbəbsiz göndərilsə 400 ilə
   qayıdır və `data-blocked` modalı yenidən açır. İmtahanın mövcud qrupları (`data-existing`) yoxlanmır.
   Mətnlər şablonun `data-t-*` atributlarından gəlir (tərcümə olunmuş); inline JS yoxdur. */
(function (ns, document) {
    "use strict";

    var dialogSeq = 0;

    function parseJSON(text, fallback) {
        try {
            var value = JSON.parse(text || "");
            return value === null || value === undefined ? fallback : value;
        } catch (error) {
            return fallback;
        }
    }

    function fmt(template, params) {
        return String(template || "").replace(/\{(\w+)\}/g, function (match, key) {
            return params && params[key] !== undefined && params[key] !== null ? String(params[key]) : match;
        });
    }

    function normalize(text) {
        return String(text || "").replace(/\s+/g, " ").trim();
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined && text !== null) {
            node.textContent = String(text);
        }
        return node;
    }

    function init(form, unitSelector) {
        var box = form ? form.querySelector("[data-ew-unit-coverage]") : null;
        if (!box || !unitSelector || box.getAttribute("data-ew-bound") === "1") {
            return;
        }
        box.setAttribute("data-ew-bound", "1");

        var url = box.getAttribute("data-url") || "";
        var minLength = Number(box.getAttribute("data-min-length")) || 10;
        var forcedInput = box.querySelector("[data-ew-unit-forced]");
        var forcedList = box.querySelector("[data-ew-unit-forced-list]");
        var subjectSelect = form.querySelector("[data-exam-subject-native]");
        var category = form.querySelector('[name="exam_type_extended"]');
        var existing = Object.create(null);
        parseJSON(box.getAttribute("data-existing"), []).forEach(function (id) {
            existing[String(id)] = true;
        });
        var forced = parseJSON(forcedInput ? forcedInput.value : "", {});
        if (!forced || typeof forced !== "object" || Array.isArray(forced)) {
            forced = {};
        }
        var labels = Object.create(null);
        var known = Object.create(null);
        var pending = [];
        var overlay = null;

        function t(key) {
            return box.getAttribute("data-t-" + key) || "";
        }

        function subjectId() {
            return subjectSelect ? String(subjectSelect.value || "") : "";
        }

        function subjectText() {
            var opt = subjectSelect ? subjectSelect.querySelector("option[value]") : null;
            return opt ? normalize(opt.textContent) : "—";
        }

        function selectedSet() {
            var out = Object.create(null);
            unitSelector.getSelectedValues().forEach(function (value) {
                out[String(value)] = true;
            });
            return out;
        }

        function writeForced() {
            if (forcedInput) {
                forcedInput.value = JSON.stringify(forced);
            }
            if (!forcedList) {
                return;
            }
            forcedList.innerHTML = "";
            Object.keys(forced).forEach(function (id) {
                var item = el("li", "ew-unit-coverage__forced-item");
                item.appendChild(el("span", "ew-unit-coverage__forced-badge", t("forced")));
                item.appendChild(el("strong", "", labels[id] || id));
                item.appendChild(el("span", "ew-unit-coverage__forced-reason", forced[id]));
                forcedList.appendChild(item);
            });
            forcedList.hidden = !forcedList.children.length;
        }

        function closeDialog() {
            if (overlay && overlay.parentNode) {
                overlay.parentNode.removeChild(overlay);
            }
            overlay = null;
            pending = [];
        }

        function titleFor(rows) {
            if (rows.length > 1) {
                return t("title-many");
            }
            var row = rows[0];
            if (!row.has_journal || row.uncovered >= row.total) {
                return t("title-none");
            }
            return fmt(t("title-some"), { n: row.uncovered });
        }

        function groupItem(row) {
            var item = el("li", "ew-unit-cov__group");
            item.appendChild(el("strong", "ew-unit-cov__name", row.name));
            item.appendChild(el("span", "ew-unit-cov__count", fmt(t("counts"), { n: row.uncovered, total: row.total })));
            if (!row.has_journal) {
                item.appendChild(el("span", "ew-unit-cov__nojournal", t("no-journal")));
            }
            var names = (row.names || []).slice();
            if (row.more) {
                names.push(fmt(t("more"), { n: row.more }));
            }
            if (names.length) {
                item.appendChild(el("span", "ew-unit-cov__names", names.join(", ")));
            }
            return item;
        }

        function renderDialog(subjectLabel) {
            var host = form.closest(".modal-content") || form.parentNode;
            if (!host) {
                return;
            }
            if (overlay && overlay.parentNode) {
                overlay.parentNode.removeChild(overlay);
            }
            dialogSeq += 1;
            var titleId = "ewUnitCovTitle" + dialogSeq;
            var reasonId = "ewUnitCovReason" + dialogSeq;
            overlay = el("div", "ew-confirm ew-unit-cov-overlay");
            overlay.setAttribute("data-ew-unit-cov-dialog", "");
            var dialog = el("div", "ew-confirm-box ew-confirm-box--review ew-unit-cov");
            dialog.setAttribute("role", "alertdialog");
            dialog.setAttribute("aria-modal", "true");
            dialog.setAttribute("aria-labelledby", titleId);
            var icon = el("span", "ew-confirm-ic");
            icon.appendChild(el("i", "fas fa-triangle-exclamation"));
            icon.firstChild.setAttribute("aria-hidden", "true");
            dialog.appendChild(icon);
            var title = el("h4", "", titleFor(pending));
            title.id = titleId;
            dialog.appendChild(title);
            dialog.appendChild(el("p", "", fmt(t("intro"), { subject: subjectLabel || subjectText() })));
            var list = el("ul", "ew-unit-cov__groups");
            pending.forEach(function (row) {
                list.appendChild(groupItem(row));
            });
            dialog.appendChild(list);

            var reasonWrap = el("div", "ew-unit-cov__reason");
            var label = el("label", "ew-label", t("reason") + " ");
            label.setAttribute("for", reasonId);
            var req = el("span", "ew-req", "*");
            req.setAttribute("aria-hidden", "true");
            label.appendChild(req);
            var reason = document.createElement("textarea");
            reason.className = "form-control ew-unit-cov__textarea";
            reason.id = reasonId;
            reason.rows = 3;
            reason.maxLength = 1000;
            reason.placeholder = t("placeholder");
            reasonWrap.appendChild(label);
            reasonWrap.appendChild(reason);
            reasonWrap.appendChild(el("small", "form-text", fmt(t("hint"), { n: minLength })));
            dialog.appendChild(reasonWrap);

            var actions = el("div", "ew-confirm-actions");
            var removeBtn = el("button", "ew-btn ew-btn--ghost", t("remove"));
            removeBtn.type = "button";
            removeBtn.setAttribute("data-ew-unit-cov-remove", "");
            var forceBtn = el("button", "ew-btn ew-btn--primary", t("force"));
            forceBtn.type = "button";
            forceBtn.disabled = true;
            forceBtn.setAttribute("data-ew-unit-cov-force", "");
            actions.appendChild(removeBtn);
            actions.appendChild(forceBtn);
            dialog.appendChild(actions);
            overlay.appendChild(dialog);
            host.appendChild(overlay);

            reason.addEventListener("input", function () {
                forceBtn.disabled = normalize(reason.value).length < minLength;
            });
            removeBtn.addEventListener("click", function () {
                var ids = pending.map(function (row) { return row.id; });
                closeDialog();
                ids.forEach(function (id) {
                    delete forced[id];
                });
                writeForced();
                if (typeof unitSelector.deselect === "function") {
                    unitSelector.deselect(ids);
                }
            });
            forceBtn.addEventListener("click", function () {
                var text = normalize(reason.value);
                if (text.length < minLength) {
                    return;
                }
                pending.forEach(function (row) {
                    forced[row.id] = text;
                    labels[row.id] = row.name;
                });
                closeDialog();
                writeForced();
            });
            reason.focus();
        }

        function showRows(rows, subjectLabel) {
            var byId = Object.create(null);
            pending.forEach(function (row) {
                byId[row.id] = true;
            });
            rows.forEach(function (row) {
                labels[row.id] = row.name;
                if (!byId[row.id]) {
                    pending.push(row);
                    byId[row.id] = true;
                }
            });
            if (pending.length) {
                renderDialog(subjectLabel);
            }
        }

        function check(ids) {
            var subject = subjectId();
            ids = ids.filter(function (id) {
                return !existing[id] && !forced[id];
            });
            if (!url || !subject || !ids.length) {
                return;
            }
            var query = url + (url.indexOf("?") === -1 ? "?" : "&") +
                "units=" + encodeURIComponent(ids.join(",")) +
                "&subject=" + encodeURIComponent(subject) +
                "&category=" + encodeURIComponent(category ? (category.value || "") : "");
            fetch(query, { headers: { "X-Requested-With": "XMLHttpRequest" }, credentials: "same-origin" })
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (data) {
                    if (!data || !data.applies || subject !== subjectId() || !document.body.contains(form)) {
                        return; // fənn arada dəyişib / sehrbaz bağlanıb — köhnə cavab
                    }
                    var selectedNow = selectedSet();
                    var rows = (data.groups || []).filter(function (row) {
                        return row && row.uncovered > 0 && selectedNow[String(row.id)] && !forced[String(row.id)];
                    });
                    if (rows.length) {
                        showRows(rows, data.subject);
                    }
                })
                .catch(function () {
                    /* yoxlama köməkçidir — server saxlamada yenə yoxlayır */
                });
        }

        function onSelectionChange() {
            var now = selectedSet();
            var added = Object.keys(now).filter(function (id) { return !known[id]; });
            var removedForced = Object.keys(forced).filter(function (id) { return !now[id]; });
            known = now;
            if (removedForced.length) {
                removedForced.forEach(function (id) {
                    delete forced[id];
                });
                writeForced();
            }
            check(added);
        }

        function recheckAll() {
            // Fənn / kateqoriya dəyişdi — əvvəlki səbəblər köhnə fənnə aid idi: hamısı yenidən yoxlanılır.
            forced = {};
            writeForced();
            closeDialog();
            check(Object.keys(selectedSet()));
        }

        known = selectedSet();
        unitSelector.getSelectedItems().forEach(function (item) {
            labels[String(item.value)] = normalize(item.text);
        });
        Object.keys(forced).forEach(function (id) {
            if (!known[id]) {
                delete forced[id];
            }
        });
        unitSelector.addSelectionListener(onSelectionChange);
        if (subjectSelect) {
            subjectSelect.addEventListener("change", recheckAll);
        }
        if (category) {
            category.addEventListener("change", recheckAll);
        }
        writeForced();

        var blocked = parseJSON(box.getAttribute("data-blocked"), []);
        if (Array.isArray(blocked) && blocked.length) {
            showRows(blocked.filter(function (row) { return row && known[String(row.id)]; }), "");
        }
    }

    ns.unitCoverage = { init: init };
})(window.EMSExamCreateEditModal = window.EMSExamCreateEditModal || {}, document);
