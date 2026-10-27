/* «Alt qrupa tələbə əlavə et» (sahib 2026-10-18) — KONTROLLER. Şablon: sections/subgroup_placement/_content.html.
 *
 * AJAX-safe: hadisələr sənəd səviyyəsində BİR DƏFƏ (EMSDelegate) qeyd olunur; panel hər swap-dan sonra
 * EMSReady ilə yenidən qurulur (vəziyyət kök elementin özündə saxlanılır).
 * Axın: tələbə (xülasə: kredit, kəsilmiş fənlər, tarixçə) → fənn → jurnal kartı → önbaxış (GET, heç nə yazmır)
 * → sənəd + səbəb → «Alt qrupa yerləşdir» (multipart POST) → nəticə + siyahıların yenilənməsi.
 * Şəbəkə: EMSCore.fetchJSON (CSRF avtomatik). DOM render: subgroup_placement_render.js.
 */
(function (window, document) {
    "use strict";

    if (window.EMSSubgroupPlacement) {
        return;
    }
    window.EMSSubgroupPlacement = true;

    var STATE = "__emsSubgroupPlacement";
    var MIN_REASON = 10;

    function R() {
        return window.EMSSubgroupPlacementRender;
    }

    function rootOf(node) {
        return node && node.closest ? node.closest("[data-sgp-root]") : null;
    }

    function state(root) {
        if (!root[STATE]) {
            root[STATE] = { student: "", subject: "", offering: "", preview: null, offerings: [], recentOffset: 0, seq: 0 };
        }
        return root[STATE];
    }

    function strings(root) {
        var st = state(root);
        if (!st.i18n) {
            var node = root.querySelector("#sgp-i18n");
            try {
                st.i18n = node ? JSON.parse(node.textContent || "{}") : {};
            } catch (err) {
                st.i18n = {};
            }
        }
        return st.i18n;
    }

    function canWrite(root) {
        return root.getAttribute("data-can-write") === "1";
    }

    function q(root, selector) {
        return root.querySelector(selector);
    }

    function toast(message, kind) {
        if (window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, kind || "info");
        }
    }

    function errorMessage(root, err) {
        return (err && err.payload && err.payload.message) || strings(root).error;
    }

    function withParams(url, params) {
        var parts = [];
        Object.keys(params).forEach(function (key) {
            if (params[key] !== undefined && params[key] !== null && params[key] !== "") {
                parts.push(encodeURIComponent(key) + "=" + encodeURIComponent(params[key]));
            }
        });
        return url + (parts.length ? (url.indexOf("?") === -1 ? "?" : "&") + parts.join("&") : "");
    }

    /* ── Addım işarələri ─────────────────────────────────────────────────── */

    function setStep(root, current) {
        [1, 2, 3].forEach(function (n) {
            var mark = q(root, '[data-sgp-step-mark="' + n + '"]');
            var card = q(root, '[data-sgp-step="' + n + '"]');
            if (mark) {
                mark.classList.toggle("ems-step--done", n < current);
                mark.classList.toggle("ems-step--current", n === current);
            }
            if (card) {
                card.classList.toggle("is-disabled", n > current);
            }
        });
    }

    /* ── Addım 1: tələbə ─────────────────────────────────────────────────── */

    function loadSummary(root) {
        var st = state(root);
        var box = q(root, "[data-sgp-summary]");
        if (!st.student || !box) {
            return;
        }
        var url = root.getAttribute("data-student-url").replace(/\/0\/$/, "/" + encodeURIComponent(st.student) + "/");
        box.hidden = false;
        box.textContent = strings(root).loading;
        window.EMSCore.fetchJSON(url)
            .then(function (data) {
                R().summary(box, data, strings(root), canWrite(root));
            })
            .catch(function (err) {
                box.textContent = errorMessage(root, err);
            });
    }

    function resetFrom(root, step) {
        var st = state(root);
        if (step <= 2) {
            st.subject = "";
            if (st.subjectPicker) {
                st.subjectPicker.reset();
            }
            R().clear(q(root, "[data-sgp-offerings]"));
            st.offerings = [];
        }
        st.offering = "";
        st.preview = null;
        R().clear(q(root, "[data-sgp-checks]"));
        var result = q(root, "[data-sgp-result]");
        if (result) {
            result.hidden = true;
        }
        syncForm(root);
    }

    function onStudent(root) {
        var st = state(root);
        st.student = st.studentPicker ? st.studentPicker.value() : "";
        resetFrom(root, 2);
        var box = q(root, "[data-sgp-summary]");
        if (st.subjectPicker) {
            st.subjectPicker.setPlaceholder(st.student ? strings(root).subject_ready : strings(root).subject_idle);
        }
        if (!st.student) {
            if (box) {
                box.hidden = true;
            }
            setStep(root, 1);
            return;
        }
        setStep(root, 2);
        loadSummary(root);
    }

    /* ── Addım 2: fənn + jurnal ──────────────────────────────────────────── */

    function loadOfferings(root) {
        var st = state(root);
        var box = q(root, "[data-sgp-offerings]");
        if (!st.student || !st.subject || !box) {
            return;
        }
        box.textContent = strings(root).loading;
        var url = withParams(root.getAttribute("data-offerings-url"), { student: st.student, subject: st.subject });
        window.EMSCore.fetchJSON(url)
            .then(function (data) {
                st.offerings = data.offerings || [];
                R().offerings(box, st.offerings, strings(root), st.offering);
            })
            .catch(function (err) {
                box.textContent = errorMessage(root, err);
            });
    }

    function onSubject(root) {
        var st = state(root);
        st.subject = st.subjectPicker ? st.subjectPicker.value() : "";
        resetFrom(root, 3);
        setStep(root, 2);
        loadOfferings(root);
    }

    function offeringRow(root, id) {
        var rows = state(root).offerings || [];
        for (var i = 0; i < rows.length; i += 1) {
            if (rows[i].id === id) {
                return rows[i];
            }
        }
        return null;
    }

    function selectOffering(root, id) {
        var st = state(root);
        st.offering = id;
        R().offerings(q(root, "[data-sgp-offerings]"), st.offerings, strings(root), id);
        var row = offeringRow(root, id);
        var releaseRow = q(root, "[data-sgp-release-row]");
        var release = q(root, "[data-sgp-release]");
        if (releaseRow) {
            releaseRow.hidden = !(row && row.releases_own);
        }
        if (release && !(row && row.releases_own)) {
            release.checked = false;
        }
        setStep(root, 3);
        loadPreview(root);
    }

    /* ── Addım 3: önbaxış + forma ────────────────────────────────────────── */

    function loadPreview(root) {
        var st = state(root);
        var box = q(root, "[data-sgp-checks]");
        if (!st.offering || !box) {
            return;
        }
        var release = q(root, "[data-sgp-release]");
        var seq = (st.seq += 1);
        box.textContent = strings(root).loading;
        var url = withParams(root.getAttribute("data-preview-url"), {
            student: st.student,
            offering: st.offering,
            release: release && release.checked ? "1" : "",
        });
        window.EMSCore.fetchJSON(url)
            .then(function (data) {
                if (seq !== st.seq) {
                    return;
                }
                st.preview = data;
                R().checks(box, data, strings(root));
                var clashRow = q(root, "[data-sgp-clash-row]");
                if (clashRow) {
                    clashRow.hidden = !(data.ok && data.clashes && data.clashes.length);
                }
                syncForm(root);
            })
            .catch(function (err) {
                st.preview = null;
                box.textContent = errorMessage(root, err);
                syncForm(root);
            });
    }

    function formProblem(root) {
        var s = strings(root);
        var st = state(root);
        var file = q(root, "#sgp-document");
        var number = (q(root, "#sgp-order-number") || {}).value || "";
        var date = (q(root, "#sgp-order-date") || {}).value || "";
        var reason = ((q(root, "#sgp-reason") || {}).value || "").trim();
        // Superadmin (sahib 2026-10-27): sənəd və səbəb istəyə bağlıdır — server avtomatik qeyd yazır.
        var docOptional = root.getAttribute("data-doc-optional") === "1";
        if (!docOptional && !(file && file.files && file.files.length) && !(number.trim() && date)) {
            return s.doc_required;
        }
        if (!docOptional && reason.length < MIN_REASON) {
            return s.reason_required;
        }
        var clash = q(root, "[data-sgp-clash-accept]");
        if (st.preview && st.preview.clashes && st.preview.clashes.length && clash && !clash.checked) {
            return s.clash_confirm;
        }
        return "";
    }

    function syncForm(root) {
        var st = state(root);
        var submit = q(root, "[data-sgp-submit]");
        if (submit) {
            submit.disabled = !(canWrite(root) && st.preview && st.preview.ok && !formProblem(root));
        }
    }

    function showFormError(root, message) {
        var node = q(root, "[data-sgp-form-error]");
        if (node) {
            node.textContent = message || "";
            node.hidden = !message;
        }
    }

    function submit(root) {
        var st = state(root);
        var problem = formProblem(root);
        if (problem) {
            showFormError(root, problem);
            return;
        }
        showFormError(root, "");
        var form = q(root, "[data-sgp-form]");
        var body = new window.FormData(form);
        body.append("student", st.student);
        body.append("offering", st.offering);
        var button = q(root, "[data-sgp-submit]");
        if (button) {
            button.disabled = true;
        }
        window.EMSCore.fetchJSON(root.getAttribute("data-place-url"), { method: "POST", body: body })
            .then(function (data) {
                R().result(q(root, "[data-sgp-result]"), data, strings(root));
                toast(data.message, "success");
                form.reset();
                q(root, "[data-sgp-clash-row]").hidden = true;
                loadSummary(root);
                loadOfferings(root);
                loadRecent(root, false);
                st.offering = "";
                st.preview = null;
                R().clear(q(root, "[data-sgp-checks]"));
                setStep(root, 2);
            })
            .catch(function (err) {
                showFormError(root, errorMessage(root, err));
                if (err && err.payload && err.payload.error === "clash_confirm_required") {
                    q(root, "[data-sgp-clash-row]").hidden = false;
                }
            })
            .finally(function () {
                syncForm(root);
            });
    }

    /* ── Son yerləşdirmələr + geri götürmə ───────────────────────────────── */

    function loadRecent(root, append) {
        var st = state(root);
        var list = q(root, "[data-sgp-recent]");
        if (!list) {
            return;
        }
        if (!append) {
            st.recentOffset = 0;
        }
        var search = q(root, "[data-sgp-recent-q]");
        var url = withParams(root.getAttribute("data-recent-url"), {
            q: search ? search.value.trim() : "",
            offset: st.recentOffset,
        });
        window.EMSCore.fetchJSON(url)
            .then(function (data) {
                var rows = data.results || [];
                st.recentOffset += rows.length;
                R().history(list, rows, strings(root), { append: append, canWrite: canWrite(root) });
                var more = q(root, "[data-sgp-more]");
                if (more) {
                    more.hidden = !data.has_more;
                }
            })
            .catch(function (err) {
                list.textContent = errorMessage(root, err);
            });
    }

    function openUndo(root, button) {
        var dialog = document.getElementById("sgp-undo-dialog");
        if (!dialog || !window.EMSOverlay) {
            return;
        }
        dialog.setAttribute("data-sgp-event", button.getAttribute("data-sgp-undo"));
        dialog.__sgpRoot = root;
        var target = dialog.querySelector("[data-sgp-undo-target]");
        if (target) {
            target.textContent = button.getAttribute("data-sgp-undo-label") || "";
        }
        var reason = dialog.querySelector("[data-sgp-undo-reason]");
        if (reason) {
            reason.value = "";
        }
        var error = dialog.querySelector("[data-sgp-undo-error]");
        if (error) {
            error.hidden = true;
        }
        window.EMSOverlay.open("sgp-undo-dialog");
    }

    function confirmUndo(dialog) {
        var root = dialog.__sgpRoot || document.querySelector("[data-sgp-root]");
        if (!root) {
            return;
        }
        var reason = (dialog.querySelector("[data-sgp-undo-reason]") || {}).value || "";
        var error = dialog.querySelector("[data-sgp-undo-error]");
        if (reason.trim().length < MIN_REASON) {
            error.textContent = strings(root).reason_required;
            error.hidden = false;
            return;
        }
        window.EMSCore.fetchJSON(root.getAttribute("data-undo-url"), {
            method: "POST",
            data: { event: dialog.getAttribute("data-sgp-event"), reason: reason.trim() },
        })
            .then(function (data) {
                window.EMSOverlay.close(dialog);
                toast(data.message, "success");
                loadRecent(root, false);
                loadSummary(root);
                loadOfferings(root);
            })
            .catch(function (err) {
                error.textContent = errorMessage(root, err);
                error.hidden = false;
            });
    }

    /* ── Qurulma ─────────────────────────────────────────────────────────── */

    function buildPickers(root) {
        var st = state(root);
        var s = strings(root);
        var studentEl = q(root, ".js-sgp-student");
        var subjectEl = q(root, ".js-sgp-subject");
        if (!window.EMSSearchableSelect || !studentEl || !subjectEl) {
            return false;
        }
        st.studentPicker = window.EMSSearchableSelect.create(studentEl, {
            url: root.getAttribute("data-students-url"),
            skeleton: true,
            emptyText: s.student_empty,
        });
        st.subjectPicker = window.EMSSearchableSelect.create(subjectEl, {
            url: root.getAttribute("data-subjects-url"),
            skeleton: true,
            emptyText: s.subject_empty,
            dependParam: "student",
            getDependValue: function () {
                return st.student;
            },
        });
        st.studentPicker.on("change", function () {
            onStudent(root);
        });
        st.subjectPicker.on("change", function () {
            onSubject(root);
        });
        return true;
    }

    function init(root, attempt) {
        if (!root || root.getAttribute("data-sgp-ready") === "1") {
            return;
        }
        if (!R() || !window.EMSCore || !buildPickers(root)) {
            if ((attempt || 0) < 40) {
                window.setTimeout(function () {
                    init(root, (attempt || 0) + 1);
                }, 50);
            }
            return;
        }
        root.setAttribute("data-sgp-ready", "1");
        setStep(root, 1);
        loadRecent(root, false);
        var initial = root.getAttribute("data-initial-student");
        if (initial) {
            state(root).studentPicker.setValue(initial, root.getAttribute("data-initial-student-text") || initial);
        }
    }

    window.EMSReady(function () {
        init(document.querySelector("[data-sgp-root]"), 0);
    });

    window.EMSDelegate.on("click", "[data-sgp-offering]", function (event, button) {
        var root = rootOf(button);
        if (root && !button.disabled) {
            selectOffering(root, button.getAttribute("data-sgp-offering"));
        }
    });

    window.EMSDelegate.on("click", "[data-sgp-pick-subject]", function (event, chip) {
        var root = rootOf(chip);
        var st = root ? state(root) : null;
        if (st && st.subjectPicker) {
            st.subjectPicker.setValue(chip.getAttribute("data-sgp-pick-subject"), chip.getAttribute("data-sgp-pick-text"));
        }
    });

    window.EMSDelegate.on("change", "[data-sgp-release]", function (event, input) {
        var root = rootOf(input);
        if (root) {
            loadPreview(root);
        }
    });

    ["input", "change"].forEach(function (type) {
        window.EMSDelegate.on(type, "[data-sgp-form] input, [data-sgp-form] textarea", function (event, input) {
            var root = rootOf(input);
            if (root) {
                showFormError(root, "");
                syncForm(root);
            }
        });
    });

    window.EMSDelegate.on("submit", "[data-sgp-form]", function (event, form) {
        event.preventDefault();
        var root = rootOf(form);
        if (root) {
            submit(root);
        }
    });

    window.EMSDelegate.on("click", "[data-sgp-more]", function (event, button) {
        var root = rootOf(button);
        if (root) {
            loadRecent(root, true);
        }
    });

    window.EMSDelegate.on("input", "[data-sgp-recent-q]", function (event, input) {
        var root = rootOf(input);
        if (!root) {
            return;
        }
        var st = state(root);
        window.clearTimeout(st.recentTimer);
        st.recentTimer = window.setTimeout(function () {
            loadRecent(root, false);
        }, 400);
    });

    window.EMSDelegate.on("click", "[data-sgp-undo]", function (event, button) {
        var root = rootOf(button);
        if (root) {
            openUndo(root, button);
        }
    });

    window.EMSDelegate.on("click", "[data-sgp-undo-confirm]", function (event, button) {
        var dialog = button.closest("#sgp-undo-dialog");
        if (dialog) {
            confirmUndo(dialog);
        }
    });
})(window, document);
