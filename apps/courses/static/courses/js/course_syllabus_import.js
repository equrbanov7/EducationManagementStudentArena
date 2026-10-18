/*
 * courses/js/course_syllabus_import.js — «Sillabusdan mövzuları götür» dialoqu (2026-10-18).
 *
 * Axın: dialoq açılır → kurs sillabusa bağlıdırsa birbaşa onun ön baxışı, deyilsə seçici (GET options,
 * axtarış debounce ilə) → sillabus seçilir → ön baxış (GET preview, heç nə yazılmır) → «Mövzuları əlavə et»
 * (tək POST import; server idempotentdir, təkrar klik dublikat yaratmır) → nəticə bildirişi + səhifə yenilənir.
 *
 * Təhlükəsizlik: serverdən gələn mətn yalnız `textContent` ilə yazılır. AJAX-safe: hadisələr `EMSDelegate`
 * ilə bir dəfə bağlanır, dialoq kökü hər dəfə yenidən oxunur (null-safe).
 */
(function () {
    "use strict";

    if (window.__emsSyllabusImport) {
        return;
    }
    window.__emsSyllabusImport = true;

    var state = { syllabusId: "", preview: null, timer: null, request: 0 };

    function root() {
        return document.querySelector("[data-si-root]");
    }

    function q(sel) {
        var r = root();
        return r ? r.querySelector(sel) : null;
    }

    function t(key) {
        var r = root();
        return (r && r.dataset["i18n" + key]) || "";
    }

    function fill(template, values) {
        return String(template).replace(/\{(\w+)\}/g, function (match, name) {
            return Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : match;
        });
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

    function setLoading(on) {
        var loading = q("[data-si-loading]");
        if (loading) {
            loading.hidden = !on;
        }
    }

    function showError(message) {
        var box = q("[data-si-error]");
        if (!box) {
            return;
        }
        box.textContent = message || "";
        box.classList.toggle("d-none", !message);
    }

    function showStep(name) {
        var r = root();
        if (!r) {
            return;
        }
        r.querySelectorAll("[data-si-step]").forEach(function (step) {
            step.hidden = step.getAttribute("data-si-step") !== name;
        });
        var confirm = q("[data-si-confirm]");
        if (confirm) {
            confirm.hidden = name !== "preview";
        }
    }

    function fail(err) {
        setLoading(false);
        var payload = err && err.payload;
        showError((payload && payload.error) || t("Error"));
    }

    function badge(item) {
        var node = el("span", item.status_class, item.status_label);
        return node;
    }

    // ── 1. Seçici ─────────────────────────────────────────────────────────
    function renderOptions(items) {
        var list = q("[data-si-list]");
        var empty = q("[data-si-empty]");
        if (!list) {
            return;
        }
        list.textContent = "";
        (items || []).forEach(function (item) {
            var btn = el("button", "si-option");
            btn.type = "button";
            btn.setAttribute("role", "listitem");
            btn.setAttribute("data-si-pick", item.id);
            var main = el("span", "si-option__main");
            main.appendChild(el("span", "si-option__title", item.subject));
            main.appendChild(el("span", "si-option__meta", [item.code, item.period, item.version].filter(Boolean).join(" · ")));
            btn.appendChild(main);
            var tags = el("span", "si-option__tags");
            if (item.is_linked) {
                tags.appendChild(el("span", "ems-badge ems-badge--primary", t("Linked")));
            } else if (item.is_own) {
                tags.appendChild(el("span", "ems-badge ems-badge--neutral", t("Own")));
            }
            tags.appendChild(badge(item));
            btn.appendChild(tags);
            list.appendChild(btn);
        });
        if (empty) {
            empty.hidden = (items || []).length > 0;
        }
    }

    function loadOptions(search, keepError) {
        var r = root();
        if (!r || !window.EMSCore) {
            return;
        }
        var ticket = ++state.request;
        var url = r.dataset.optionsUrl + (search ? "?q=" + encodeURIComponent(search) : "");
        setLoading(true);
        if (!keepError) {
            showError("");
        }
        window.EMSCore.fetchJSON(url)
            .then(function (payload) {
                if (ticket !== state.request) {
                    return;
                }
                setLoading(false);
                renderOptions(payload.items);
            })
            .catch(fail);
    }

    // ── 2. Ön baxış ───────────────────────────────────────────────────────
    function renderPreview(payload) {
        state.preview = payload;
        var source = payload.syllabus || {};
        var title = q("[data-si-source-title]");
        var meta = q("[data-si-source-meta]");
        var badgeSlot = q("[data-si-source-badge]");
        if (title) {
            title.textContent = source.subject || "";
        }
        if (meta) {
            meta.textContent = [source.code, source.period, source.version].filter(Boolean).join(" · ");
        }
        if (badgeSlot) {
            badgeSlot.textContent = "";
            badgeSlot.appendChild(badge(source));
        }
        var counts = payload.counts || { total: 0, new: 0, existing: 0 };
        var summary = q("[data-si-summary]");
        if (summary) {
            summary.textContent = counts.total
                ? fill(t("Summary"), { new: counts.new, existing: counts.existing })
                : t("NoRows");
        }
        var weeks = q("[data-si-weeks]");
        if (weeks) {
            weeks.textContent = "";
            (payload.rows || []).forEach(function (row) {
                var li = el("li", "si-week" + (row.exists ? " is-existing" : ""));
                li.appendChild(el("span", "si-week__num", row.week));
                var text = el("span", "si-week__text");
                text.appendChild(el("span", "si-week__title", row.title));
                if (row.hours_text) {
                    text.appendChild(el("span", "si-week__meta", row.hours_text));
                }
                li.appendChild(text);
                li.appendChild(
                    el("span", row.exists ? "ems-badge ems-badge--muted" : "ems-badge ems-badge--success", row.exists ? t("Exists") : t("New"))
                );
                weeks.appendChild(li);
            });
        }
        var link = q("[data-si-link]");
        if (link) {
            link.checked = true;
            var wrap = link.closest(".si-link");
            if (wrap) {
                wrap.hidden = Boolean(source.is_linked);
            }
        }
        showStep("preview");
        updateConfirm();
    }

    function updateConfirm() {
        var confirm = q("[data-si-confirm]");
        var label = q("[data-si-confirm-label]");
        var link = q("[data-si-link]");
        if (!confirm || !label || !state.preview) {
            return;
        }
        var fresh = (state.preview.counts || {}).new || 0;
        var canLink = link && !link.closest(".si-link").hidden && link.checked;
        var summary = q("[data-si-summary]");
        var counts = state.preview.counts || {};
        confirm.hidden = false;
        if (fresh > 0) {
            label.textContent = fill(t("Confirm"), { n: fresh });
            confirm.disabled = false;
        } else if (canLink) {
            label.textContent = t("LinkOnly");
            confirm.disabled = false;
        } else {
            // Yazılacaq heç nə yoxdur — düymə gizlənir, səbəb xülasədə yazılır.
            confirm.hidden = true;
            confirm.disabled = true;
            if (summary && counts.total) {
                summary.textContent = t("Nothing");
            }
        }
    }

    function loadPreview(syllabusId) {
        var r = root();
        if (!r || !window.EMSCore || !syllabusId) {
            return;
        }
        state.syllabusId = syllabusId;
        showError("");
        setLoading(true);
        window.EMSCore.fetchJSON(r.dataset.previewUrl + "?syllabus=" + encodeURIComponent(syllabusId))
            .then(function (payload) {
                setLoading(false);
                renderPreview(payload);
            })
            .catch(function (err) {
                // Bağlı sillabus artıq oxunmur (deaktiv / əhatədən çıxıb) və ya seçim köhnəlib — seçiciyə qayıt.
                fail(err);
                showStep("pick");
                loadOptions("", true);
            });
    }

    // ── 3. İdxal ──────────────────────────────────────────────────────────
    function submit(btn) {
        var r = root();
        var link = q("[data-si-link]");
        if (!r || !state.syllabusId || btn.disabled) {
            return;
        }
        btn.disabled = true;
        var label = q("[data-si-confirm-label]");
        if (label) {
            label.textContent = t("Saving");
        }
        showError("");
        window.EMSCore.fetchJSON(r.dataset.importUrl, {
            method: "POST",
            data: { syllabus: state.syllabusId, link: Boolean(link && link.checked) },
        })
            .then(function (payload) {
                if (typeof window.notifySuccess === "function") {
                    window.notifySuccess(payload.message);
                }
                window.setTimeout(function () {
                    window.location.reload();
                }, 700);
            })
            .catch(function (err) {
                btn.disabled = false;
                updateConfirm();
                fail(err);
            });
    }

    function open() {
        var r = root();
        if (!r) {
            return;
        }
        state.preview = null;
        state.syllabusId = "";
        var search = q("[data-si-search]");
        if (search) {
            search.value = "";
        }
        if (r.dataset.linkedId) {
            showStep("");
            loadPreview(r.dataset.linkedId);
        } else {
            showStep("pick");
            loadOptions("");
        }
    }

    document.addEventListener("show.bs.modal", function (event) {
        if (event.target && event.target.matches && event.target.matches("[data-si-root]")) {
            open();
        }
    });

    if (window.EMSDelegate) {
        window.EMSDelegate.on("click", "[data-si-pick]", function (event, btn) {
            loadPreview(btn.getAttribute("data-si-pick"));
        });
        window.EMSDelegate.on("click", "[data-si-back]", function () {
            showStep("pick");
            loadOptions((q("[data-si-search]") || {}).value || "");
        });
        window.EMSDelegate.on("click", "[data-si-confirm]", function (event, btn) {
            submit(btn);
        });
        window.EMSDelegate.on("change", "[data-si-link]", updateConfirm);
        window.EMSDelegate.on("input", "[data-si-search]", function (event, input) {
            window.clearTimeout(state.timer);
            state.timer = window.setTimeout(function () {
                loadOptions(input.value.trim());
            }, 250);
        });
    }
})();
