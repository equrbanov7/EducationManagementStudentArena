/*
 * publish_notification.js
 * Source: apps/accounts/templates/accounts/profile/sections/_publish_notification.html
 *
 * «Bildiriş göndər» compose formasının davranışı:
 *   • alıcı siyahısı — eksklüziv «hamıya» məntiqi, axtarış filtri, çiplər,
 *     canlı sayğac («N qrup seçilib»);
 *   • başlıq / mətn sayğacları, textarea avto-böyümə, keçid (URL) yoxlaması;
 *   • şəkil seçimi — ölçü/tip yoxlaması, önizləmə, silmə;
 *   • yapışqan əməl paneli — «Göndər» yalnız ≥1 alıcı + başlıq (+ düzgün
 *     keçid) olanda aktivdir; server tərəfi validasiya olduğu kimi qalır;
 *   • sağdakı «Önizləmə» kartı — hər daxiletmədə yenilənir.
 *
 * AJAX-safe: bütün hadisələr `EMSDelegate.on` ilə `document`-ə bir dəfə
 * bağlanır (eyni açar → təkrar yığılmır); ilkin sinxronizasiya `EMSReady`
 * ilə hər bölmə swap-ından sonra yenidən işləyir (root-da dataset qoruyucu).
 * Mətnlər şablondan `data-i18n-*` atributları ilə gəlir — burada literal yoxdur.
 */
(function () {
    "use strict";

    var ROOT_SEL = "[data-pn-root]";
    var MAX_IMAGE_BYTES = 5 * 1024 * 1024;
    var MAX_TEXTAREA_PX = 360;

    function byId(id) {
        return document.getElementById(id);
    }

    function rootOf(el) {
        return el && typeof el.closest === "function" ? el.closest(ROOT_SEL) : null;
    }

    function i18n(root, key, fallback) {
        var v = root ? root.getAttribute("data-i18n-" + key) : null;
        return v || fallback || "";
    }

    function fmtCount(tpl, n) {
        return String(tpl || "").replace("%d", String(n));
    }

    function fmtName(tpl, s) {
        return String(tpl || "").replace("%s", s);
    }

    function isHttpUrl(value) {
        try {
            var u = new URL(value);
            return u.protocol === "http:" || u.protocol === "https:";
        } catch (e) {
            return false;
        }
    }

    function hostOf(value) {
        try {
            return new URL(value).host || value;
        } catch (e) {
            return value;
        }
    }

    /* ── Vəziyyət ───────────────────────────────────────────────────────── */
    function readState(root) {
        var selected = [];
        root.querySelectorAll(".pn-target-cb").forEach(function (cb) {
            if (cb.checked) {
                selected.push({
                    value: cb.value,
                    label: cb.getAttribute("data-target-label") || cb.value,
                    id: cb.id
                });
            }
        });
        var titleEl = byId("notifTitle");
        var linkEl = byId("notifLink");
        var link = linkEl ? linkEl.value.trim() : "";
        return {
            selected: selected,
            title: titleEl ? titleEl.value.trim() : "",
            link: link,
            linkOk: !link || isHttpUrl(link),
            imageError: root.dataset.pnImageError === "1",
            filesError: root.dataset.pnFilesError === "1",
            filesErrorText: root.dataset.pnFilesErrorText || ""
        };
    }

    /* ── Render: çiplər ─────────────────────────────────────────────────── */
    function renderChips(root, st) {
        var wrap = byId("pnTargetChips");
        if (!wrap) { return; }
        wrap.textContent = "";
        if (!st.selected.length) {
            wrap.hidden = true;
            return;
        }
        var removeTpl = i18n(root, "chip-remove", "%s");
        st.selected.forEach(function (item) {
            var chip = document.createElement("span");
            chip.className = "ems-chip pn-chip";

            var text = document.createElement("span");
            text.className = "pn-chip__text";
            text.textContent = item.label;
            text.title = item.label;

            var x = document.createElement("button");
            x.type = "button";
            x.className = "pn-chip__x";
            x.setAttribute("data-pn-remove", item.id);
            x.setAttribute("aria-label", fmtName(removeTpl, item.label));
            var icon = document.createElement("i");
            icon.className = "fas fa-xmark";
            icon.setAttribute("aria-hidden", "true");
            x.appendChild(icon);

            chip.appendChild(text);
            chip.appendChild(x);
            wrap.appendChild(chip);
        });
        wrap.hidden = false;
    }

    /* ── Render: sayğaclar / önizləmə / əməl paneli ─────────────────────── */
    function renderTargetCount(root, st) {
        var n = st.selected.length;
        var countEl = byId("pnTargetCount");
        if (countEl) {
            countEl.textContent = n ? fmtCount(i18n(root, "count"), n) : i18n(root, "count-empty");
            countEl.classList.toggle("is-empty", n === 0);
        }
        var clearBtn = byId("pnClearTargets");
        if (clearBtn) { clearBtn.hidden = n < 2; }

        var recipients = byId("pnPreviewRecipients");
        if (recipients) {
            recipients.textContent = n
                ? st.selected.map(function (s) { return s.label; }).join(", ")
                : i18n(root, "count-empty");
        }
    }

    function renderCharCounter(input, counterEl) {
        if (!input || !counterEl) { return; }
        var max = parseInt(input.getAttribute("maxlength"), 10) || 0;
        var len = input.value.length;
        counterEl.textContent = max ? (len + " / " + max) : String(len);
        counterEl.classList.toggle("is-near", max > 0 && len >= max * 0.9 && len < max);
        counterEl.classList.toggle("is-full", max > 0 && len >= max);
    }

    function renderLinkMessage(root, st, force) {
        var linkEl = byId("notifLink");
        var msg = byId("notifLinkError");
        if (!linkEl || !msg) { return; }
        var touched = linkEl.dataset.pnTouched === "1" || force === true;
        var show = touched && !st.linkOk;
        msg.hidden = !show;
        var text = msg.querySelector("[data-pn-link-error-text]");
        if (text) { text.textContent = show ? i18n(root, "link-invalid") : ""; }
        if (show) {
            linkEl.setAttribute("aria-invalid", "true");
        } else {
            linkEl.removeAttribute("aria-invalid");
        }
    }

    function renderPreview(root, st) {
        var titleEl = byId("pnPreviewTitle");
        if (titleEl) {
            var ph = titleEl.getAttribute("data-placeholder") || "";
            titleEl.textContent = st.title || ph;
            titleEl.classList.toggle("is-placeholder", !st.title);
        }
        var msgSrc = byId("notifMessage");
        var msgEl = byId("pnPreviewMessage");
        if (msgEl) {
            var text = msgSrc ? msgSrc.value.trim() : "";
            msgEl.textContent = text || (msgEl.getAttribute("data-placeholder") || "");
            msgEl.classList.toggle("is-placeholder", !text);
        }
        var linkEl = byId("pnPreviewLink");
        if (linkEl) {
            var showLink = !!st.link && st.linkOk;
            linkEl.hidden = !showLink;
            linkEl.setAttribute("href", showLink ? st.link : "#");
            var host = linkEl.querySelector("[data-pn-link-host]");
            if (host) { host.textContent = showLink ? hostOf(st.link) : ""; }
        }
    }

    function renderFooter(root, st) {
        var btn = byId("pnSubmitBtn");
        var summary = byId("pnFootSummary");
        var count = byId("pnSubmitCount");
        var reason = "";
        if (!st.selected.length) {
            reason = i18n(root, "need-target");
        } else if (!st.title) {
            reason = i18n(root, "need-title");
        } else if (!st.linkOk) {
            reason = i18n(root, "link-invalid");
        } else if (st.imageError) {
            reason = i18n(root, "image-invalid");
        } else if (st.filesError) {
            reason = st.filesErrorText || i18n(root, "files-invalid");
        }
        var can = reason === "";
        if (btn) {
            btn.disabled = !can;
            btn.setAttribute("aria-disabled", can ? "false" : "true");
        }
        if (count) {
            count.hidden = st.selected.length === 0;
            count.textContent = String(st.selected.length);
        }
        if (summary) {
            summary.textContent = can
                ? i18n(root, "ready") + " — " + fmtCount(i18n(root, "count"), st.selected.length)
                : reason;
            summary.classList.toggle("is-ready", can);
        }
    }

    function autoGrow(textarea) {
        if (!textarea) { return; }
        textarea.style.height = "auto";
        textarea.style.height = Math.min(textarea.scrollHeight, MAX_TEXTAREA_PX) + "px";
    }

    function sync(root, opts) {
        if (!root) { return; }
        var st = readState(root);
        renderChips(root, st);
        renderTargetCount(root, st);
        renderCharCounter(byId("notifTitle"), byId("notifTitleCounter"));
        renderCharCounter(byId("notifMessage"), byId("notifMessageCounter"));
        renderLinkMessage(root, st, opts && opts.forceLink);
        renderPreview(root, st);
        renderFooter(root, st);
    }

    /* ── Alıcı siyahısı ─────────────────────────────────────────────────── */
    function applyExclusive(root, changed) {
        if (!changed.checked) { return; }
        var isExclusive = changed.classList.contains("pn-target-cb--exclusive");
        root.querySelectorAll(".pn-target-cb").forEach(function (other) {
            if (other === changed) { return; }
            var otherExclusive = other.classList.contains("pn-target-cb--exclusive");
            if (isExclusive || otherExclusive) {
                other.checked = false;
            }
        });
    }

    function filterTargets(root, query) {
        var q = (query || "").toLowerCase().trim();
        var visible = 0;
        var perCat = {};
        root.querySelectorAll(".pn-target-item").forEach(function (item) {
            var label = (item.getAttribute("data-label") || "").toLowerCase();
            var show = q === "" || label.indexOf(q) !== -1;
            item.hidden = !show;
            if (show) {
                visible++;
                var cat = item.getAttribute("data-pn-cat") || "";
                perCat[cat] = (perCat[cat] || 0) + 1;
            }
        });
        // Kateqoriya başlığı boş qalanda gizlənir.
        root.querySelectorAll(".pn-target-cat").forEach(function (head) {
            head.hidden = !perCat[head.getAttribute("data-pn-cat") || ""];
        });
        var empty = byId("pnTargetNoResults");
        if (empty) { empty.hidden = !(q !== "" && visible === 0); }
    }

    /* ── Əlavə fayllar ──────────────────────────────────────────────────── */
    var MAX_FILE_BYTES = 10 * 1024 * 1024;
    var MAX_FILES = 5;
    var FILE_EXT_RE = /\.(pdf|docx?|xlsx?|pptx?|txt|csv|zip|jpe?g|png|gif|webp)$/i;

    function fmtSize(bytes) {
        if (bytes >= 1024 * 1024) { return (bytes / (1024 * 1024)).toFixed(1) + " MB"; }
        if (bytes >= 1024) { return Math.round(bytes / 1024) + " KB"; }
        return bytes + " B";
    }

    function setFilesError(root, text) {
        var msg = byId("notifFilesError");
        var span = msg ? msg.querySelector("[data-pn-files-error-text]") : null;
        var input = byId("notifFiles");
        root.dataset.pnFilesError = text ? "1" : "0";
        root.dataset.pnFilesErrorText = text || "";
        if (msg) { msg.hidden = !text; }
        if (span) { span.textContent = text || ""; }
        if (input) {
            if (text) { input.setAttribute("aria-invalid", "true"); } else { input.removeAttribute("aria-invalid"); }
        }
    }

    function renderFileList(listEl, files) {
        if (!listEl) { return; }
        listEl.textContent = "";
        files.forEach(function (file) {
            var li = document.createElement("li");
            var icon = document.createElement("i");
            icon.className = "fas fa-paperclip";
            icon.setAttribute("aria-hidden", "true");
            var name = document.createElement("span");
            name.className = "pn-files__name";
            name.textContent = file.name;
            var size = document.createElement("span");
            size.className = "pn-files__size";
            size.textContent = fmtSize(file.size);
            li.appendChild(icon);
            li.appendChild(name);
            li.appendChild(size);
            listEl.appendChild(li);
        });
        listEl.hidden = files.length === 0;
    }

    function clearFiles(root) {
        var input = byId("notifFiles");
        if (input) { input.value = ""; }
        renderFileList(byId("notifFilesList"), []);
        renderFileList(byId("pnPreviewFiles"), []);
        var summary = byId("notifFilesSummary");
        if (summary) { summary.textContent = ""; }
        var clearBtn = byId("notifFilesClear");
        if (clearBtn) { clearBtn.hidden = true; }
        setFilesError(root, "");
    }

    function handleFilesChange(root, input) {
        var files = Array.prototype.slice.call(input.files || []);
        if (!files.length) {
            clearFiles(root);
            sync(root);
            return;
        }
        if (files.length > MAX_FILES) {
            clearFiles(root);
            setFilesError(root, i18n(root, "files-too-many"));
            sync(root);
            return;
        }
        for (var i = 0; i < files.length; i += 1) {
            if (!FILE_EXT_RE.test(files[i].name || "")) {
                clearFiles(root);
                setFilesError(root, fmtName(i18n(root, "files-invalid"), files[i].name));
                sync(root);
                return;
            }
            if (files[i].size > MAX_FILE_BYTES) {
                clearFiles(root);
                setFilesError(root, fmtName(i18n(root, "files-too-large"), files[i].name));
                sync(root);
                return;
            }
        }
        setFilesError(root, "");
        renderFileList(byId("notifFilesList"), files);
        renderFileList(byId("pnPreviewFiles"), files);
        var summary = byId("notifFilesSummary");
        if (summary) { summary.textContent = fmtCount(i18n(root, "files-count"), files.length); }
        var clearBtn = byId("notifFilesClear");
        if (clearBtn) { clearBtn.hidden = false; }
        sync(root);
    }

    /* ── Şəkil ──────────────────────────────────────────────────────────── */
    function setImageError(root, text) {
        var msg = byId("notifImageError");
        var span = msg ? msg.querySelector("[data-pn-image-error-text]") : null;
        var input = byId("notifImage");
        root.dataset.pnImageError = text ? "1" : "0";
        if (msg) { msg.hidden = !text; }
        if (span) { span.textContent = text || ""; }
        if (input) {
            if (text) { input.setAttribute("aria-invalid", "true"); } else { input.removeAttribute("aria-invalid"); }
        }
    }

    function clearImage(root) {
        var input = byId("notifImage");
        var name = byId("notifImageName");
        var clearBtn = byId("notifImageClear");
        var preview = byId("pnPreviewImage");
        if (input) { input.value = ""; }
        if (name) { name.textContent = ""; }
        if (clearBtn) { clearBtn.hidden = true; }
        if (preview) { preview.hidden = true; preview.removeAttribute("src"); }
        setImageError(root, "");
    }

    function handleImageChange(root, input) {
        var file = input.files && input.files[0];
        var name = byId("notifImageName");
        var clearBtn = byId("notifImageClear");
        var preview = byId("pnPreviewImage");
        if (!file) {
            clearImage(root);
            sync(root);
            return;
        }
        if (file.type && file.type.indexOf("image/") !== 0) {
            clearImage(root);
            setImageError(root, i18n(root, "image-invalid"));
            sync(root);
            return;
        }
        if (file.size > MAX_IMAGE_BYTES) {
            clearImage(root);
            setImageError(root, i18n(root, "image-too-large"));
            sync(root);
            return;
        }
        setImageError(root, "");
        if (name) { name.textContent = file.name; }
        if (clearBtn) { clearBtn.hidden = false; }
        if (preview && typeof FileReader !== "undefined") {
            var reader = new FileReader();
            reader.onload = function (e) {
                preview.src = e.target.result;
                preview.hidden = false;
            };
            reader.readAsDataURL(file);
        }
        sync(root);
    }

    /* ── Hadisələr (document-level, bir dəfə) ───────────────────────────── */
    if (window.EMSDelegate) {
        window.EMSDelegate.on("change", ".pn-target-cb", function (e, cb) {
            var root = rootOf(cb);
            if (!root) { return; }
            applyExclusive(root, cb);
            sync(root);
        });

        window.EMSDelegate.on("input", "#pnTargetSearch", function (e, input) {
            var root = rootOf(input);
            if (root) { filterTargets(root, input.value); }
        });

        window.EMSDelegate.on("click", "[data-pn-remove]", function (e, btn) {
            var root = rootOf(btn);
            var cb = byId(btn.getAttribute("data-pn-remove"));
            if (!root || !cb) { return; }
            cb.checked = false;
            sync(root);
            var search = byId("pnTargetSearch");
            if (search) { search.focus(); }
        });

        window.EMSDelegate.on("click", "[data-pn-clear-targets]", function (e, btn) {
            var root = rootOf(btn);
            if (!root) { return; }
            root.querySelectorAll(".pn-target-cb").forEach(function (cb) { cb.checked = false; });
            sync(root);
            var search = byId("pnTargetSearch");
            if (search) { search.focus(); }
        });

        window.EMSDelegate.on("input", "#notifTitle, #notifLink", function (e, input) {
            sync(rootOf(input));
        });

        window.EMSDelegate.on("input", "#notifMessage", function (e, ta) {
            autoGrow(ta);
            sync(rootOf(ta));
        });

        window.EMSDelegate.on("focusout", "#notifLink", function (e, input) {
            input.dataset.pnTouched = "1";
            sync(rootOf(input));
        });

        window.EMSDelegate.on("change", "#notifImage", function (e, input) {
            var root = rootOf(input);
            if (root) { handleImageChange(root, input); }
        });

        window.EMSDelegate.on("change", "#notifFiles", function (e, input) {
            var root = rootOf(input);
            if (root) { handleFilesChange(root, input); }
        });

        window.EMSDelegate.on("click", "#notifFilesClear", function (e, btn) {
            var root = rootOf(btn);
            if (!root) { return; }
            clearFiles(root);
            sync(root);
            var input = byId("notifFiles");
            if (input) { input.focus(); }
        });

        window.EMSDelegate.on("click", "#notifImageClear", function (e, btn) {
            var root = rootOf(btn);
            if (!root) { return; }
            clearImage(root);
            sync(root);
            var input = byId("notifImage");
            if (input) { input.focus(); }
        });

        window.EMSDelegate.on("reset", "#pnForm", function (e, form) {
            var root = rootOf(form);
            if (!root) { return; }
            // Brauzer dəyərləri bu hadisədən SONRA qaytarır → növbəti tick-də sinxronlaş.
            window.setTimeout(function () {
                var link = byId("notifLink");
                if (link) { delete link.dataset.pnTouched; }
                clearImage(root);
                clearFiles(root);
                filterTargets(root, "");
                autoGrow(byId("notifMessage"));
                sync(root);
            }, 0);
        });

        window.EMSDelegate.on("submit", "#pnForm", function (e, form) {
            var root = rootOf(form);
            if (!root) { return; }
            var st = readState(root);
            var ok = st.selected.length > 0 && !!st.title && st.linkOk && !st.imageError && !st.filesError;
            if (!ok) {
                e.preventDefault();
                sync(root, { forceLink: true });
                var focusTarget = !st.selected.length ? byId("pnTargetSearch")
                    : (!st.title ? byId("notifTitle") : byId("notifLink"));
                if (focusTarget) { focusTarget.focus(); }
                return;
            }
            var btn = byId("pnSubmitBtn");
            var label = btn ? btn.querySelector("[data-pn-submit-label]") : null;
            if (label) { label.textContent = i18n(root, "sending", label.textContent); }
            if (btn) { btn.setAttribute("aria-disabled", "true"); }
        });
    }

    /* ── İlkin sinxronizasiya — hər bölmə yüklənməsində ─────────────────── */
    window.EMSReady(function () {
        var root = document.querySelector(ROOT_SEL);
        if (!root) { return; }
        if (root.dataset.pnBound === "1") { return; }
        root.dataset.pnBound = "1";
        autoGrow(byId("notifMessage"));
        filterTargets(root, (byId("pnTargetSearch") || {}).value || "");
        sync(root);
    });
})();
