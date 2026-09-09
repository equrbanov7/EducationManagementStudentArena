/* ═══════════════════════════════════════════════════════════════════════════
   registrar_catalog.js — «Registrar (kataloq)» bölməsinin dialoqu

   Panel SERVER-RENDER-lidir; bu fayl yalnız:
     * tab keçidini (bölməni yenidən yükləyir, SƏHİFƏ DƏYİŞMİR),
     * yaratma/redaktə dialoqunun doldurulmasını və POST-unu,
     * sahə-sahə xəta göstərilməsini idarə edir.

   Sahib (2026-09-09): kataloq kabinetdən ÇIXMAMALIDIR — ona görə burada heç bir
   `location.href` yoxdur; hər şey `EMSProfileLoadSection` (SPA swap) ilə gedir.

   AJAX-safe: `EMSDelegate` + `EMSReady`; seçicilər YALNIZ bu faylda işlənir
   (delegate açar toqquşması qapısı: `test_static_js_delegate_keys`).
   ═══════════════════════════════════════════════════════════════════════════ */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE) {
        return;
    }

    /* ⚠️ `EMSCore` bu skriptdən SONRA yüklənir (bölmə paneli səhifənin
     * gövdəsindədir, `core/http.js` isə sonda) — ona görə modul yüklənəndə
     * DEYİL, çağırış anında oxunur. Əvvəl modul səviyyəsində tutulurdu və
     * bütün dialoq düymələri səssizcə işləmirdi. */
    function core() {
        return window.EMSCore;
    }

    var DIALOG_ID = "rcatForm";

    function root() {
        return document.querySelector("[data-rcat-root]");
    }

    function dialog() {
        return document.getElementById(DIALOG_ID);
    }

    function options() {
        var node = document.getElementById("rcat-options");
        if (!node) {
            return {};
        }
        try {
            return JSON.parse(node.textContent) || {};
        } catch (err) {
            return {};
        }
    }

    function field(name) {
        var box = dialog();
        return box ? box.querySelector('[data-rcat-field="' + name + '"]') : null;
    }

    function fields() {
        var box = dialog();
        return box ? box.querySelectorAll("[data-rcat-field]") : [];
    }

    /* Seçiciləri serverdən gələn siyahı ilə doldurur. `data-rcat-blank` olan
     * sahədə boş sətir də olur («təyin edilməyib» halı). */
    function fillSelects() {
        var data = options();
        var box = dialog();
        if (!box) {
            return;
        }
        box.querySelectorAll("select[data-rcat-options]").forEach(function (select) {
            var list = data[select.getAttribute("data-rcat-options")] || [];
            select.textContent = "";
            if (select.hasAttribute("data-rcat-blank")) {
                select.appendChild(new Option("—", ""));
            }
            list.forEach(function (item) {
                select.appendChild(new Option(item.label, item.value));
            });
            if (window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.refresh(select);
            }
        });
    }

    function setError(message) {
        var node = dialog() && dialog().querySelector("[data-rcat-error]");
        if (!node) {
            return;
        }
        node.textContent = message || "";
        node.hidden = !message;
    }

    function clearFieldErrors() {
        var box = dialog();
        if (!box) {
            return;
        }
        box.querySelectorAll(".is-invalid").forEach(function (el) {
            el.classList.remove("is-invalid");
        });
        box.querySelectorAll("[data-rcat-fielderror]").forEach(function (el) {
            el.remove();
        });
    }

    function showErrors(errors) {
        clearFieldErrors();
        var general = [];
        Object.keys(errors || {}).forEach(function (name) {
            var messages = errors[name] || [];
            var el = field(name);
            if (!el) {
                general = general.concat(messages);
                return;
            }
            el.classList.add("is-invalid");
            var note = document.createElement("p");
            note.className = "ems-field__error";
            note.setAttribute("data-rcat-fielderror", "1");
            note.textContent = messages.join(" ");
            (el.closest(".ems-field") || el.parentNode).appendChild(note);
        });
        setError(general.join(" "));
    }

    function reset() {
        clearFieldErrors();
        setError("");
        fillSelects();
        fields().forEach(function (el) {
            if (el.type === "checkbox") {
                el.checked = true;
            } else {
                el.value = "";
            }
            if (el.tagName === "SELECT" && window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.sync(el);
            }
        });
    }

    function apply(values) {
        Object.keys(values || {}).forEach(function (name) {
            var el = field(name);
            if (!el) {
                return;
            }
            if (el.type === "checkbox") {
                el.checked = Boolean(values[name]);
                return;
            }
            el.value = values[name] === null ? "" : values[name];
            if (el.tagName === "SELECT" && window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.sync(el);
            }
        });
    }

    function post(payload) {
        var host = root();
        payload.tab = host ? host.getAttribute("data-rcat-tab") : "";
        var http = core();
        if (!host || !http) {
            return Promise.reject(new Error("core_unavailable"));
        }
        return http.fetchJSON(host.getAttribute("data-rcat-action-url"), {
            method: "POST",
            data: payload,
        });
    }

    /* Bölməni yenidən yükləyir — cari süzgəcləri və tabı SAXLAYARAQ.
     * `EMSProfileLoadSection` layihənin SPA yükləyicisidir (bax
     * `accounts/js/profile/ui.js`); tam səhifə naviqasiyası OLMUR. */
    function sectionUrl(tab) {
        var host = root();
        var url = new URL(host.getAttribute("data-rcat-section-url"), window.location.origin);
        url.searchParams.set(host.getAttribute("data-rcat-tab-param"), tab);
        return url.pathname + url.search;
    }

    function reload() {
        var host = root();
        if (!host || typeof window.EMSProfileLoadSection !== "function") {
            return;
        }
        var url = new URL(host.getAttribute("data-rcat-section-url"), window.location.origin);
        url.searchParams.set(host.getAttribute("data-rcat-tab-param"), host.getAttribute("data-rcat-tab"));
        var form = document.querySelector("[data-ems-filters]");
        if (form) {
            form.querySelectorAll("[data-ems-filter]").forEach(function (el) {
                if (el.value) {
                    url.searchParams.set(el.getAttribute("data-ems-filter"), el.value);
                }
            });
        }
        window.EMSProfileLoadSection("registrar-catalog", url.pathname + url.search);
    }

    function openDialog(id) {
        if (!window.EMSOverlay) {
            return;
        }
        reset();
        if (!id) {
            window.EMSOverlay.open(DIALOG_ID);
            return;
        }
        post({ action: "values", id: id })
            .then(function (result) {
                apply(result.values);
                var idField = field("id");
                if (idField) {
                    idField.value = id;
                }
                window.EMSOverlay.open(DIALOG_ID);
            })
            .catch(function () {
                setError("");
            });
    }

    function submit() {
        var payload = { action: "save" };
        fields().forEach(function (el) {
            var name = el.getAttribute("data-rcat-field");
            payload[name] = el.type === "checkbox" ? (el.checked ? "on" : "") : el.value;
        });
        post(payload)
            .then(function () {
                if (window.EMSOverlay) {
                    window.EMSOverlay.close(DIALOG_ID);
                }
                reload();
            })
            .catch(function (err) {
                var body = err && err.payload;
                if (body && body.errors) {
                    showErrors(body.errors);
                    return;
                }
                setError((body && body.message) || "");
            });
    }

    DELEGATE.on("click", "[data-rcat-new]", function (event) {
        event.preventDefault();
        openDialog("");
    });

    DELEGATE.on("click", "[data-rcat-edit]", function (event, button) {
        event.preventDefault();
        openDialog(button.getAttribute("data-rcat-edit"));
    });

    DELEGATE.on("submit", "#rcatForm form", function (event) {
        event.preventDefault();
        submit();
    });

    /* Tab keçidi — bölmə swap-ı, tam səhifə yüklənməsi YOX. */
    DELEGATE.on("click", "[data-rcat-root] [data-ems-tab]", function (event, button) {
        event.preventDefault();
        if (!root() || typeof window.EMSProfileLoadSection !== "function") {
            return;
        }
        window.EMSProfileLoadSection("registrar-catalog", sectionUrl(button.getAttribute("data-ems-tab")));
    });
})(window, document);
