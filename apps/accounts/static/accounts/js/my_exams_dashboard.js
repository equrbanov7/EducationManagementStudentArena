/* =========================================================================
   my_exams_dashboard.js — Müəllim paneli ("İmtahanlarım") interaktivliyi.

   AJAX-safe: bütün hadisələr `EMSDelegate` (document-səviyyə deleqasiya) ilə
   bağlanır, ilkin qurğu isə `EMSReady` ilə həm ilk yüklənmədə, həm də profil
   bölməsi AJAX ilə dəyişdikdə yenidən işləyir. Filtr vəziyyəti DOM-da (root
   dataset) saxlanır ki, swap-dan sonra closure problemi olmasın.

   Funksiyalar: KPI status filtri · kateqoriya çipləri · instant axtarış ·
   bölmə qatlama · grid/list keçidi (localStorage) · kebab menyu · kod kopyala ·
   silmə təsdiq modalı · arxiv/dublikat POST.
   ========================================================================= */
(function () {
    "use strict";

    if (window._EMS_MY_EXAMS_DASHBOARD_INIT) {
        return;
    }
    window._EMS_MY_EXAMS_DASHBOARD_INIT = true;

    var VIEW_STORAGE_KEY = "emsMyExamsView";

    function i18n(key, fallback) {
        var dict = window.MY_EXAMS_I18N || {};
        return dict[key] || fallback;
    }

    /* ---- view (grid / list) -------------------------------------------- */
    function setView(root, view) {
        var isList = view === "list";
        root.classList.toggle("is-list", isList);
        root.querySelectorAll("[data-tx-viewtoggle] button").forEach(function (btn) {
            btn.classList.toggle("is-on", btn.getAttribute("data-view") === view);
        });
    }

    /* ---- filtering ------------------------------------------------------ */
    function updateCategoryCounts(root) {
        var status = root.dataset.txStatus || "";
        var type = root.dataset.txType || "all";
        var query = (root.dataset.txSearch || "").trim().toLowerCase();
        var counts = { all: 0 };

        root.querySelectorAll("[data-tx-catfilter] [data-cat]").forEach(function (chip) {
            var key = chip.getAttribute("data-cat") || "all";
            if (key !== "all") {
                counts[key] = 0;
            }
        });

        root.querySelectorAll("[data-exam-card]").forEach(function (card) {
            if (status && card.getAttribute("data-status") !== status) {
                return;
            }
            if (type !== "all" && card.getAttribute("data-type") !== type) {
                return;
            }
            if (query && (card.getAttribute("data-name") || "").indexOf(query) === -1) {
                return;
            }

            counts.all += 1;
            var category = card.getAttribute("data-category") || "";
            if (Object.prototype.hasOwnProperty.call(counts, category)) {
                counts[category] += 1;
            }
        });

        // Səhifələnəndə server sayları AVTORİTETDİR: onlar tam dəst üzərində
        // aqreqat sorğu ilə hesablanır, buradakı say isə yalnız DOM-dakı 12
        // kartı görür. Üzərinə yazsaq eyni səhifədə «25» və «12» görünür.
        if (isPaginated(root)) {
            return;
        }
        root.querySelectorAll("[data-tx-catfilter] [data-cat]").forEach(function (chip) {
            var key = chip.getAttribute("data-cat") || "all";
            var countEl = chip.querySelector(".tx-cat-n");
            if (countEl) {
                countEl.textContent = String(counts[key] || 0);
            }
        });
    }


    // ── Səhifələmə rejimi ────────────────────────────────────────────────────
    // Siyahı səhifələnəndə DOM-da yalnız cari səhifənin kartları olur. Klient
    // tərəfdə filtr etmək o deməkdir ki, axtarış qalan sətirləri HEÇ VAXT
    // görmür — mövcud imtahan üçün «tapılmadı» yazılır. Bu rejimdə filtrləri
    // serverə göndəririk (toolbar əsl GET formudur).
    function isPaginated(root) {
        return root && root.getAttribute("data-tx-paginated") === "1";
    }

    function submitToolbar(root) {
        var form = root.querySelector("[data-tx-toolbar]");
        if (!form) {
            return false;
        }
        var statusField = form.querySelector("[data-tx-status-field]");
        if (statusField) {
            statusField.value = root.dataset.txStatus || "";
        }
        // `exam_page` ötürülmür: filtr dəyişəndə 1-ci səhifəyə qayıtmaq düzgündür.
        form.submit();
        return true;
    }

    function applyFilters(root) {
        var status = root.dataset.txStatus || "";
        var type = root.dataset.txType || "all";
        var category = root.dataset.txCat || "all";
        var query = (root.dataset.txSearch || "").trim().toLowerCase();
        var anyVisible = false;

        updateCategoryCounts(root);

        root.querySelectorAll("[data-exam-card]").forEach(function (card) {
            var ok = true;
            if (status && card.getAttribute("data-status") !== status) {
                ok = false;
            }
            if (ok && type !== "all" && card.getAttribute("data-type") !== type) {
                ok = false;
            }
            if (ok && category !== "all" && card.getAttribute("data-category") !== category) {
                ok = false;
            }
            if (ok && query && (card.getAttribute("data-name") || "").indexOf(query) === -1) {
                ok = false;
            }
            card.classList.toggle("is-hidden", !ok);
            if (ok) {
                anyVisible = true;
            }
        });

        root.querySelectorAll("[data-tx-section]").forEach(function (section) {
            var hideByStatus = status && section.getAttribute("data-status") !== status;
            var visibleCards = section.querySelectorAll("[data-exam-card]:not(.is-hidden)").length;
            section.hidden = Boolean(hideByStatus) || visibleCards === 0;
        });

        var noResult = root.querySelector("[data-tx-noresult]");
        if (noResult) {
            noResult.hidden = anyVisible;
        }
        applyClamp(root);
    }

    // Hər bölmədə ilk 6 kartı göstər; "Daha çox" hər klikdə ən çox 8 kart artırır.
    // Performans: artıq kartlar display:none — render olunmur, yalnız DOM-dadır.
    var SECTION_INITIAL_LIMIT = 6;
    var SECTION_LOAD_STEP = 8;

    function getSectionVisibleLimit(section) {
        var value = Number(section.dataset.txVisibleLimit || SECTION_INITIAL_LIMIT);
        if (!Number.isFinite(value) || value < SECTION_INITIAL_LIMIT) {
            return SECTION_INITIAL_LIMIT;
        }
        return value;
    }

    function applyClamp(root) {
        root.querySelectorAll("[data-tx-section]").forEach(function (section) {
            var visibleLimit = getSectionVisibleLimit(section);
            var shown = 0;
            var clamped = 0;
            section.querySelectorAll("[data-exam-card]").forEach(function (card) {
                if (card.classList.contains("is-hidden")) {
                    card.classList.remove("is-clamped");
                    return;
                }
                var doClamp = shown >= visibleLimit;
                card.classList.toggle("is-clamped", doClamp);
                if (doClamp) {
                    clamped++;
                } else {
                    shown++;
                }
            });
            var btn = section.querySelector("[data-tx-showmore]");
            if (btn) {
                btn.hidden = clamped === 0;
                var countEl = section.querySelector("[data-tx-more-count]");
                if (countEl) {
                    countEl.textContent = String(Math.min(clamped, SECTION_LOAD_STEP));
                }
            }
        });
    }

    // Axtarış zamanı qısa skeleton (debounce ilə) — UX üçün "yüklənir" hissi.
    function showSkeleton(root, on) {
        var skeleton = root.querySelector("[data-tx-skeleton]");
        var sections = root.querySelector("[data-tx-sections]");
        if (skeleton) {
            skeleton.hidden = !on;
        }
        if (sections) {
            sections.style.display = on ? "none" : "";
        }
        if (on) {
            var noResult = root.querySelector("[data-tx-noresult]");
            if (noResult) {
                noResult.hidden = true;
            }
        }
    }

    function closeAllMenus(scope) {
        (scope || document).querySelectorAll(".tx-menu-wrap.is-open").forEach(function (wrap) {
            wrap.classList.remove("is-open");
            var toggle = wrap.querySelector("[data-tx-menu-toggle]");
            if (toggle) {
                toggle.setAttribute("aria-expanded", "false");
            }
        });
    }

    function copyText(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(text);
        }
        return new Promise(function (resolve) {
            var ta = document.createElement("textarea");
            ta.value = text;
            ta.setAttribute("readonly", "");
            ta.style.position = "absolute";
            ta.style.left = "-9999px";
            document.body.appendChild(ta);
            ta.select();
            try {
                document.execCommand("copy");
            } catch (e) {
                /* ignore */
            }
            document.body.removeChild(ta);
            resolve();
        });
    }

    function showToast(message) {
        var toast = document.createElement("div");
        toast.className = "tx-toast";
        var check = document.createElement("span");
        check.className = "tx-toast-ck";
        check.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i>';
        toast.appendChild(check);
        toast.appendChild(document.createTextNode(" " + message));
        document.body.appendChild(toast);
        setTimeout(function () {
            toast.classList.add("is-out");
            setTimeout(function () {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 260);
        }, 2400);
    }

    /* ---- delegated handlers (survive AJAX swaps) ------------------------ */
    var D = window.EMSDelegate;
    if (D && typeof D.on === "function") {
        D.on("click", "[data-tx-kpi]", function (event, btn) {
            var root = btn.closest("[data-my-exams-root]");
            if (!root) {
                return;
            }
            var status = btn.getAttribute("data-status");
            var next = (root.dataset.txStatus || "") === status ? "" : status;
            root.dataset.txStatus = next;
            root.querySelectorAll("[data-tx-kpi]").forEach(function (kpi) {
                var on = next !== "" && kpi.getAttribute("data-status") === next;
                kpi.classList.toggle("is-on", on);
                kpi.setAttribute("aria-pressed", on ? "true" : "false");
            });
            if (next) {
                // Seçilmiş statusun bölməsi qatlanmışsa (məs. Arxiv) — açaq.
                var target = root.querySelector('[data-tx-section][data-status="' + next + '"]');
                if (target) {
                    target.classList.remove("is-collapsed");
                }
            }
            if (isPaginated(root) && submitToolbar(root)) {
                return;
            }
            applyFilters(root);
        });

        D.on("click", "[data-tx-catfilter] [data-cat]", function (event, btn) {
            var root = btn.closest("[data-my-exams-root]");
            if (!root) {
                return;
            }
            var category = btn.getAttribute("data-cat");
            root.dataset.txCat = category;
            root.querySelectorAll("[data-tx-catfilter] [data-cat]").forEach(function (chip) {
                chip.classList.toggle("is-on", chip.getAttribute("data-cat") === category);
            });
            applyFilters(root);
        });

        var searchTimer = null;
        D.on("input", "[data-tx-search]", function (event, input) {
            var root = input.closest("[data-my-exams-root]");
            if (!root) {
                return;
            }
            root.dataset.txSearch = input.value || "";
            showSkeleton(root, true);
            clearTimeout(searchTimer);
            searchTimer = setTimeout(function () {
                if (isPaginated(root) && submitToolbar(root)) {
                    return;  // skeleton qalır — səhifə yenilənir
                }
                applyFilters(root);
                showSkeleton(root, false);
            }, 400);
        });

        // növ filtri (seqment) — klient-tərəf instant + gizli select sinxron
        D.on("click", "[data-tx-typeseg] [data-type]", function (event, btn) {
            var root = btn.closest("[data-my-exams-root]");
            if (!root) {
                return;
            }
            var type = btn.getAttribute("data-type");
            root.dataset.txType = type;
            root.querySelectorAll("[data-tx-typeseg] [data-type]").forEach(function (b) {
                b.classList.toggle("is-on", b.getAttribute("data-type") === type);
            });
            var native = root.querySelector("[data-tx-type-native]");
            if (native) {
                native.value = type === "all" ? "" : type;
            }
            if (isPaginated(root) && submitToolbar(root)) {
                return;
            }
            applyFilters(root);
        });

        // karta klik → detal səhifəsi (interaktiv elementlər istisna)
        D.on("click", "[data-exam-card]", function (event, card) {
            if (event.target.closest("a, button, input, select, label, [data-tx-menu]")) {
                return;
            }
            var href = card.getAttribute("data-card-href");
            if (href) {
                window.location.href = href;
            }
        });

        // Toolbar submit: filtr klient-tərəf olanda reload etməsin. SƏHİFƏLƏNƏNDƏ
        // isə əksinə — serverə getməlidir, çünki DOM-da bütün siyahı yoxdur.
        D.on("submit", "[data-tx-toolbar]", function (event, form) {
            var root = form.closest("[data-my-exams-root]");
            if (isPaginated(root)) {
                var statusField = form.querySelector("[data-tx-status-field]");
                if (statusField) {
                    statusField.value = (root && root.dataset.txStatus) || "";
                }
                return;  // normal GET submit
            }
            event.preventDefault();
        });

        D.on("click", "[data-tx-viewtoggle] button", function (event, btn) {
            var root = btn.closest("[data-my-exams-root]");
            if (!root) {
                return;
            }
            var view = btn.getAttribute("data-view");
            setView(root, view);
            try {
                localStorage.setItem(VIEW_STORAGE_KEY, view);
            } catch (e) {
                /* storage unavailable — view still applies for the session */
            }
        });

        D.on("click", "[data-tx-section-toggle]", function (event, head) {
            var section = head.closest("[data-tx-section]");
            if (!section) {
                return;
            }
            var collapsed = section.classList.toggle("is-collapsed");
            head.setAttribute("aria-expanded", collapsed ? "false" : "true");
        });

        D.on("click", "[data-tx-showmore]", function (event, btn) {
            var section = btn.closest("[data-tx-section]");
            var root = btn.closest("[data-my-exams-root]");
            if (!section || !root) {
                return;
            }
            section.dataset.txVisibleLimit = String(getSectionVisibleLimit(section) + SECTION_LOAD_STEP);
            applyClamp(root);
        });

        D.on("keydown", "[data-tx-section-toggle]", function (event, head) {
            if (event.key !== "Enter" && event.key !== " ") {
                return;
            }
            event.preventDefault();
            head.click();
        });

        D.on("click", "[data-tx-menu-toggle]", function (event, btn) {
            event.stopPropagation();
            var wrap = btn.closest("[data-tx-menu]");
            if (!wrap) {
                return;
            }
            var willOpen = !wrap.classList.contains("is-open");
            closeAllMenus();
            wrap.classList.toggle("is-open", willOpen);
            btn.setAttribute("aria-expanded", willOpen ? "true" : "false");
        });

        D.on("click", ".js-tx-copy-code", function (event, btn) {
            closeAllMenus();
            var code = btn.getAttribute("data-code") || "";
            copyText(code).then(function () {
                showToast(i18n("codeCopied", gettext("Kod kopyalandı")) + ": " + code);
            });
        });

        D.on("click", ".js-tx-post-action", function (event, btn) {
            closeAllMenus();
            var root = btn.closest("[data-my-exams-root]");
            if (!root) {
                return;
            }
            var form = root.querySelector("[data-tx-action-form]");
            if (!form) {
                return;
            }
            form.setAttribute("action", btn.getAttribute("data-action-url"));
            form.submit();
        });

        D.on("click", ".js-tx-delete", function (event, btn) {
            closeAllMenus();
            var root = btn.closest("[data-my-exams-root]");
            if (!root) {
                return;
            }
            var modalEl = root.querySelector("[data-tx-delete-modal]");
            if (!modalEl) {
                return;
            }
            var form = modalEl.querySelector("[data-tx-delete-form]");
            var nameEl = modalEl.querySelector("[data-tx-delete-name]");
            if (form) {
                form.setAttribute("action", btn.getAttribute("data-delete-url"));
            }
            if (nameEl) {
                nameEl.textContent = btn.getAttribute("data-exam-name") || "";
            }
            if (window.bootstrap && window.bootstrap.Modal) {
                window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
            } else if (form) {
                // Bootstrap yoxdursa, ən azı təhlükəsiz fallback — birbaşa təsdiq.
                form.submit();
            }
        });
    }

    /* ---- once-only document listeners ---------------------------------- */
    if (window.EMSReady && typeof window.EMSReady.once === "function") {
        window.EMSReady.once("tx-doc-listeners", function () {
            document.addEventListener("click", function (event) {
                if (!event.target.closest("[data-tx-menu]")) {
                    closeAllMenus();
                }
            });
            document.addEventListener("keydown", function (event) {
                if (event.key === "Escape") {
                    closeAllMenus();
                }
            });
            window.addEventListener("resize", function () {
                closeAllMenus();
            });
            window.addEventListener(
                "scroll",
                function () {
                    closeAllMenus();
                },
                true
            );
        });
    }

    /* ---- per-section init (initial load + every AJAX swap) ------------- */
    function init() {
        var root = document.querySelector("[data-my-exams-root]");
        if (!root) {
            return;
        }
        if (!root.dataset.txCat) {
            root.dataset.txCat = "all";
        }
        var activeType = root.querySelector("[data-tx-typeseg] [data-type].is-on");
        root.dataset.txType = activeType ? activeType.getAttribute("data-type") : "all";
        var savedView = "grid";
        try {
            savedView = localStorage.getItem(VIEW_STORAGE_KEY) || "grid";
        } catch (e) {
            savedView = "grid";
        }
        setView(root, savedView);
        applyFilters(root);
    }

    if (window.EMSReady) {
        window.EMSReady(init);
    } else {
        document.addEventListener("DOMContentLoaded", init);
    }
})();
