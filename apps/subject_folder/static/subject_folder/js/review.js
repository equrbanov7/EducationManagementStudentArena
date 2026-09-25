/* =========================================================================
   «Tapşırıq yoxlaması» — çekməcə, jurnal önizləməsi və toplu seçim.

   * `[data-sf-review="<id>"]` → çekməcəni açır, `subject_folder:review_detail`
     HTML fraqmentini (serverdə render olunub) gövdəyə yerləşdirir;
   * `[data-sf-points]` (sərbəst iş balı) → debounce ilə `review_preview`
     çağırır: «Bu bal jurnala düşəcək: …» və ya limit xətası;
   * `[data-sf-check]` / `[data-sf-check-all]` → toplu əməl panelini göstərir;
     `select[data-sf-bulk-action]` → balı/səbəbi yalnız lazım olanda açır.

   Qərar formaları `cabinet.js`-in ortaq `form[data-sf-form]` göndərişindən keçir.
   AJAX-SAFE: `EMSDelegate` + idempotent qoruyucu; inline skript yoxdur.
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSSubjectFolderReview) {
        return;
    }

    var PLACEHOLDER = "00000000-0000-0000-0000-000000000000";
    var DRAWER_ID = "sfReviewDrawer";
    var current = null;
    var previewTimer = null;

    function rootOf(node) {
        return (node && node.closest && node.closest("[data-sf-root]")) || document.querySelector("[data-sf-root]");
    }

    function urlFor(root, attr, id) {
        return String((root && root.getAttribute(attr)) || "").replace(PLACEHOLDER, encodeURIComponent(id));
    }

    function drawerBody() {
        var drawer = document.getElementById(DRAWER_ID);
        return drawer && drawer.querySelector("[data-sf-drawer-body]");
    }

    function setLoading(body, root) {
        body.textContent = "";
        var note = document.createElement("p");
        note.className = "sfc-muted";
        note.textContent = (root && root.getAttribute("data-i18n-loading")) || "";
        body.appendChild(note);
    }

    function load(id) {
        var drawer = document.getElementById(DRAWER_ID);
        var body = drawerBody();
        var root = rootOf(drawer);
        if (!drawer || !body || !id) {
            return;
        }
        current = id;
        setLoading(body, root);
        if (window.EMSOverlay && drawer.hidden) {
            window.EMSOverlay.open(drawer);
        }
        fetch(urlFor(root, "data-sf-detail-url", id), {
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" }
        })
            .then(function (response) {
                return response.json().then(function (payload) {
                    return { ok: response.ok && payload.ok !== false, payload: payload || {} };
                });
            })
            .then(function (result) {
                if (current !== id) {
                    return;
                }
                if (!result.ok) {
                    body.textContent = result.payload.message || (root && root.getAttribute("data-i18n-error")) || "";
                    return;
                }
                body.innerHTML = result.payload.html;
                var title = drawer.querySelector(".ems-drawer__title");
                if (title && result.payload.title) {
                    title.textContent = result.payload.title;
                }
                // Drawer boş alt başlıqla render olunur (`_drawer.html` onda `<p>` vermir).
                var sub = drawer.querySelector(".ems-drawer__sub");
                if (!sub && title && result.payload.subtitle) {
                    sub = document.createElement("p");
                    sub.className = "ems-drawer__sub";
                    title.insertAdjacentElement("afterend", sub);
                }
                if (sub) {
                    sub.textContent = result.payload.subtitle || "";
                }
                if (window.EMSBootstrapSelect) {
                    window.EMSBootstrapSelect.init(body);
                }
            })
            .catch(function () {
                body.textContent = (root && root.getAttribute("data-i18n-error")) || "";
            });
    }

    window.EMSDelegate.on("click", "[data-sf-review]", function (event, button) {
        event.preventDefault();
        load(button.getAttribute("data-sf-review"));
    });

    /* ---- Jurnal önizləməsi ---------------------------------------------- */

    function preview(input) {
        var root = rootOf(input);
        var form = input.form;
        var strip = form && form.querySelector("[data-sf-preview]");
        var value = String(input.value || "").trim();
        if (!strip || !value) {
            return;
        }
        var url = urlFor(root, "data-sf-preview-url", input.getAttribute("data-sf-points"));
        fetch(url + "?points=" + encodeURIComponent(value), {
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" }
        })
            .then(function (response) {
                return response.json();
            })
            .then(function (payload) {
                if (!payload || payload.ok === false) {
                    return;
                }
                // Canlı zolaq əsasdır: qovluq xətası → jurnal imtinası → «jurnala düşəcək».
                var reason = payload.journal_blocked ? String(payload.journal_reason || "") : "";
                strip.classList.toggle("sfc-preview--error", Boolean(payload.error || reason));
                strip.textContent = payload.error || reason || payload.text || "";
                var warning = form.querySelector("[data-sf-journal-warning]");
                if (warning) {
                    warning.hidden = true;
                }
            })
            .catch(function () {
                /* önizləmə yalnız köməkçidir — xəta qəbulu bloklamır */
            });
    }

    window.EMSDelegate.on("input", "[data-sf-points]", function (event, input) {
        window.clearTimeout(previewTimer);
        previewTimer = window.setTimeout(function () {
            preview(input);
        }, 350);
    });

    /* ---- Toplu seçim ----------------------------------------------------- */

    function syncBulk(form) {
        if (!form) {
            return;
        }
        var bar = form.querySelector("[data-sf-bulkbar]");
        var checked = form.querySelectorAll("[data-sf-check]:checked").length;
        if (bar) {
            bar.hidden = checked === 0;
        }
        var counter = form.querySelector("[data-sf-bulk-count]");
        var root = rootOf(form);
        if (counter) {
            counter.textContent = ((root && root.getAttribute("data-i18n-selected")) || "") + ": " + checked;
        }
    }

    window.EMSDelegate.on("change", "[data-sf-check-all]", function (event, box) {
        var form = box.form;
        if (!form) {
            return;
        }
        form.querySelectorAll("[data-sf-check]").forEach(function (item) {
            item.checked = box.checked;
        });
        syncBulk(form);
    });

    window.EMSDelegate.on("change", "[data-sf-check]", function (event, box) {
        syncBulk(box.form);
    });

    window.EMSDelegate.on("change", "select[data-sf-bulk-action]", function (event, select) {
        var form = select.form;
        if (!form) {
            return;
        }
        form.querySelectorAll("[data-sf-bulk-show]").forEach(function (node) {
            node.hidden = node.getAttribute("data-sf-bulk-show") !== select.value;
        });
    });

    window.EMSSubjectFolderReview = {
        reload: function () {
            if (current) {
                load(current);
            }
        }
    };
})(window, document);
