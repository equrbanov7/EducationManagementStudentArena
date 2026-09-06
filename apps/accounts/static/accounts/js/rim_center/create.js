/* RİM «yeni hesab» — növ seçimi + tək-tək form + uğur vəziyyəti.
 *
 * Dialoq DAVRANIŞI (fokus tələsi, Escape, scrim, fokusun qayıtması) ortaq
 * qatdadır — `static/js/ems_ui/overlay.js`; bu fayl yalnız FORMANIN məntiqidir.
 *
 * Qaydalar (CLAUDE.md + docs/frontend/AJAX_SAFE_JS_PATTERN.md):
 *   · inline JS yoxdur — URL-lər `data-*`, mətnlər JSON blokundadır;
 *   · `EMSDelegate.on` ilə document səviyyəsində delegasiya (swap-safe);
 *   · kök element (`[data-rimc-root]`) yoxdursa heç nə etmir (null-safe);
 *   · parol DOM-da YALNIZ dialoq açıq olduğu müddətdə qalır — bağlananda silinir.
 */
(function (window, document) {
    "use strict";

    var ns = (window.EMSRimCreate = window.EMSRimCreate || {});
    if (!window.EMSDelegate || !window.EMSReady) {
        return;
    }

    var form = (ns.form = {});
    var FIN_RE = /^[A-Za-z0-9]{7}$/;
    /* Doğum tarixi HƏR İKİ növdə məcburidir — toplu idxal da boş tarixi rədd
     * edir (bax services/rim/create_form.py şərhi); iki səth ayrılmasın. */
    var REQUIRED = {
        student: ["fin", "first_name", "last_name", "birth_date", "group", "admission_year"],
        teacher: ["fin", "first_name", "last_name", "birth_date"]
    };

    var state = { kind: "student", busy: false };

    function root() {
        return document.querySelector("[data-rimc-root]");
    }

    /** Şablondakı JSON blokundan tərcümələr (xarici JS `{% trans %}` görmür). */
    ns.t = function t(key) {
        var el = document.querySelector("[data-rimc-i18n]");
        if (!el) {
            return key;
        }
        try {
            var dict = JSON.parse(el.textContent || "{}");
            return dict[key] || key;
        } catch (err) {
            return key;
        }
    };

    function field(name) {
        return document.querySelector('[data-rimc-field="' + name + '"]');
    }

    function fields() {
        return document.querySelectorAll("[data-rimc-field]");
    }

    function control(name) {
        // Seçicidə görünən element input-dur, dəyər isə gizli sahədədir.
        var node = document.querySelector('[data-rimc-combo="' + name + '"]');
        return node ? node.querySelector("[data-rimc-combo-input]") : field(name);
    }

    /* ── Sahə xətaları ──────────────────────────────────────────────────── */

    form.clearError = function clearError(name) {
        var box = document.querySelector('[data-rimc-error="' + name + '"]');
        if (box) {
            box.hidden = true;
            box.textContent = "";
        }
        var el = control(name);
        if (el) {
            el.removeAttribute("aria-invalid");
            if (el.dataset.rimcDescribed !== undefined) {
                if (el.dataset.rimcDescribed) {
                    el.setAttribute("aria-describedby", el.dataset.rimcDescribed);
                } else {
                    el.removeAttribute("aria-describedby");
                }
            }
        }
    };

    function clearAllErrors() {
        var boxes = document.querySelectorAll("[data-rimc-error]");
        Array.prototype.forEach.call(boxes, function (box) {
            form.clearError(box.getAttribute("data-rimc-error"));
        });
        var summary = document.querySelector("[data-rimc-form-error]");
        if (summary) {
            summary.hidden = true;
            summary.textContent = "";
        }
    }

    function showErrors(fieldErrors, message) {
        clearAllErrors();
        var summary = document.querySelector("[data-rimc-form-error]");
        if (summary && message) {
            summary.textContent = message;
            summary.hidden = false;
        }
        var first = null;
        Object.keys(fieldErrors || {}).forEach(function (name) {
            var box = document.querySelector('[data-rimc-error="' + name + '"]');
            if (!box) {
                return;
            }
            box.id = box.id || "rimc-err-" + name;
            box.textContent = fieldErrors[name];
            box.hidden = false;
            var el = control(name);
            if (el) {
                if (el.dataset.rimcDescribed === undefined) {
                    el.dataset.rimcDescribed = el.getAttribute("aria-describedby") || "";
                }
                el.setAttribute("aria-invalid", "true");
                el.setAttribute("aria-describedby", (el.dataset.rimcDescribed + " " + box.id).trim());
                first = first || el;
            }
        });
        if (first && typeof first.focus === "function") {
            first.focus();
        }
    }

    /* ── Vəziyyət ───────────────────────────────────────────────────────── */

    /** Görünən məcburi sahələr doludursa «Hesabı yarat» aktivləşir. */
    form.refresh = function refresh() {
        var button = document.querySelector("[data-rimc-submit]");
        if (!button) {
            return;
        }
        var ok = !state.busy;
        (REQUIRED[state.kind] || []).forEach(function (name) {
            var el = field(name);
            var value = el ? String(el.value || "").trim() : "";
            if (!value) {
                ok = false;
            }
            if (name === "fin" && value && !FIN_RE.test(value)) {
                ok = false;
            }
        });
        button.disabled = !ok;
        button.setAttribute("aria-disabled", ok ? "false" : "true");
    };

    function setBusy(busy) {
        state.busy = busy;
        var body = document.querySelector("[data-rimc-body]");
        var button = document.querySelector("[data-rimc-submit]");
        if (body) {
            body.setAttribute("aria-busy", busy ? "true" : "false");
        }
        if (button) {
            if (busy) {
                button.dataset.rimcLabel = button.dataset.rimcLabel || button.textContent;
                button.textContent = ns.t("busy");
            } else if (button.dataset.rimcLabel) {
                button.textContent = button.dataset.rimcLabel;
            }
        }
        form.refresh();
        if (busy && button) {
            button.disabled = true;
            button.setAttribute("aria-disabled", "true");
        }
    }

    function toggleKindFields(kind) {
        var blocks = document.querySelectorAll("[data-rimc-only]");
        Array.prototype.forEach.call(blocks, function (block) {
            var visible = block.getAttribute("data-rimc-only") === kind;
            block.hidden = !visible;
            // Gizli sahə formanın validasiyasına qarışmasın.
            var inputs = block.querySelectorAll("input, select, textarea");
            Array.prototype.forEach.call(inputs, function (input) {
                input.disabled = !visible;
            });
        });
    }

    function resetForm() {
        var node = document.querySelector("[data-rimc-form]");
        if (node) {
            node.reset();
        }
        if (ns.combo && ns.combo.reset) {
            ns.combo.reset(document);
        }
        clearAllErrors();
        setDone(false);
        setBusy(false);
    }

    /* ── Uğur vəziyyəti ─────────────────────────────────────────────────── */

    function setDone(done) {
        var body = document.querySelector("[data-rimc-body]");
        var panel = document.querySelector("[data-rimc-done]");
        if (body) {
            body.hidden = done;
        }
        if (panel) {
            panel.hidden = !done;
        }
        [
            ["[data-rimc-submit]", !done],
            ["[data-rimc-cancel]", !done],
            ["[data-rimc-again]", done],
            ["[data-rimc-done-close]", done]
        ].forEach(function (pair) {
            var el = document.querySelector(pair[0]);
            if (el) {
                el.hidden = !pair[1];
            }
        });
    }

    function clearSecret() {
        var el = document.querySelector("[data-rimc-done-password]");
        if (el) {
            el.textContent = "";
        }
    }

    function showDone(payload) {
        var title = document.querySelector("[data-rimc-done-title]");
        var username = document.querySelector("[data-rimc-done-username]");
        var password = document.querySelector("[data-rimc-done-password]");
        var warnings = document.querySelector("[data-rimc-done-warnings]");
        if (title) {
            title.textContent = ns.t("done_" + (payload.kind || state.kind));
        }
        if (username) {
            username.textContent = payload.username || "";
        }
        if (password) {
            // Parol YALNIZ burada görünür — dialoq bağlananda silinir.
            password.textContent = payload.password || "";
        }
        if (warnings) {
            warnings.textContent = "";
            (payload.warnings || []).forEach(function (text) {
                var item = document.createElement("li");
                item.textContent = text;
                warnings.appendChild(item);
            });
            warnings.hidden = !(payload.warnings && payload.warnings.length);
        }
        setDone(true);
    }

    /* ── Göndərmə ───────────────────────────────────────────────────────── */

    function payload() {
        var data = { kind: state.kind };
        Array.prototype.forEach.call(fields(), function (input) {
            if (!input.disabled) {
                data[input.getAttribute("data-rimc-field")] = input.value;
            }
        });
        var note = document.querySelector("[data-rimc-note]");
        data.note = note ? note.value : "";
        return data;
    }

    function submit() {
        var host = root();
        var fetchJSON = window.EMSCore && window.EMSCore.fetchJSON;
        if (!host || !fetchJSON || state.busy) {
            return;
        }
        clearAllErrors();
        setBusy(true);
        fetchJSON(host.getAttribute("data-create-url"), { method: "POST", data: payload() })
            .then(function (response) {
                showDone(response || {});
                if (window.EMSRimCenter && window.EMSRimCenter.actions) {
                    // Yeni hesab axtarış nəticələrində dərhal görünsün.
                    window.EMSRimCenter.actions.search();
                }
            })
            .catch(function (err) {
                var body = err && err.payload;
                var message = (body && body.message) || ns.t("failed");
                showErrors((body && body.fields) || {}, message);
            })
            .then(function () {
                setBusy(false);
            });
    }

    /* ── Kopyalama ──────────────────────────────────────────────────────── */

    function copy(button, text) {
        if (!text) {
            return;
        }
        var done = function () {
            var original = button.innerHTML;
            button.textContent = ns.t("copied");
            window.setTimeout(function () {
                button.innerHTML = original;
            }, 1500);
        };
        if (window.navigator.clipboard && window.navigator.clipboard.writeText) {
            window.navigator.clipboard.writeText(text).then(done, function () {});
            return;
        }
        var helper = document.createElement("textarea");
        helper.value = text;
        document.body.appendChild(helper);
        helper.select();
        try {
            document.execCommand("copy");
            done();
        } catch (err) {
            /* səssiz — operator əl ilə seçə bilər */
        }
        document.body.removeChild(helper);
    }

    /* ── Hadisələr ──────────────────────────────────────────────────────── */

    ns.open = function open(kind) {
        if (!window.EMSOverlay) {
            return;
        }
        window.EMSOverlay.close("rimc-chooser");
        if (kind === "unit") {
            // İnzibati bölmə AYRI axındır (`create_unit.js`) — mövcud struktur
            // ağacı endpoint-inə gedir, hesab formu ilə heç nə paylaşmır.
            if (ns.unit && ns.unit.open) {
                ns.unit.open();
            }
            return;
        }
        if (kind === "bulk") {
            if (ns.bulk && ns.bulk.reset) {
                ns.bulk.reset();
            }
            window.EMSOverlay.open("rimc-bulk");
            return;
        }
        state.kind = kind === "teacher" ? "teacher" : "student";
        toggleKindFields(state.kind);
        resetForm();
        var title = document.querySelector("[data-rimc-title]");
        var codeLabel = document.querySelector("[data-rimc-code-label]");
        if (title) {
            title.textContent = ns.t("title_" + state.kind);
        }
        if (codeLabel) {
            codeLabel.textContent = ns.t("code_" + state.kind);
        }
        window.EMSOverlay.open("rimc-form");
    };

    window.EMSDelegate.on("click", "[data-rimc-open]", function (event, button) {
        event.preventDefault();
        ns.open(button.getAttribute("data-rimc-open"));
    });

    window.EMSDelegate.on("submit", "[data-rimc-form]", function (event) {
        event.preventDefault();
        submit();
    });

    window.EMSDelegate.on("click", "[data-rimc-submit]", function (event) {
        event.preventDefault();
        submit();
    });

    window.EMSDelegate.on("click", "[data-rimc-again]", function (event) {
        event.preventDefault();
        clearSecret();
        resetForm();
        var first = field("fin");
        if (first) {
            first.focus();
        }
    });

    window.EMSDelegate.on("click", "[data-rimc-copy]", function (event, button) {
        event.preventDefault();
        var target = document.querySelector("[data-rimc-done-" + button.getAttribute("data-rimc-copy") + "]");
        copy(button, target ? target.textContent : "");
    });

    window.EMSDelegate.on("input", "[data-rimc-field]", function () {
        form.refresh();
    });

    window.EMSDelegate.on("change", "[data-rimc-field]", function () {
        form.refresh();
    });

    // Dialoq bağlananda parol DOM-dan silinir (brauzer yaddaşında qalmasın).
    window.EMSDelegate.on("ems:overlay:close", "#rimc-form", function () {
        clearSecret();
    });

    window.EMSReady(function () {
        if (!root()) {
            return; // Bölmə bu səhifədə yoxdur — null-safe çıxış.
        }
        toggleKindFields(state.kind);
        form.refresh();
    });
})(window, document);
