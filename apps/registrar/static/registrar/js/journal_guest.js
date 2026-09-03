/* «Alt qrupdan tələbə əlavə et» — jurnal siyahısının idarəsi (koordinator/dekanlıq).
 *
 * DİNAMİK DATA: xarici JS Django şablonundan KEÇMİR, ona görə bütün URL və
 * tərcümə olunmuş mətnlər modalın `data-*` atributlarından oxunur (CSP: inline
 * script yoxdur).
 *
 * BİRLƏŞMƏ: tələbə seçiləndən sonra server ÖNBAXIŞI çəkilir — tələbənin öz
 * qrupunda bu fənn üzrə aktiv jurnalı varsa (mandat fənlərdə NORMAL hal) panel
 * hansı jurnaldan, neçə işarə/qayıb və nəyin nə olacağını göstərir. Təsdiq
 * düyməsi yalnız «öz jurnalından azad et» işarələnəndən VƏ səbəb yazılandan
 * sonra açılır — eyni şərtləri server qapısı da tələb edir (səth kifayət deyil).
 *
 * KASKAD: qrup seçilməyincə tələbə seçicisi bağlıdır; qrup dəyişəndə tələbə
 * siyahısı sıfırlanır. Hər iki seçici server-backed EMSSearchableSelect-dir
 * (250ms debounce + lazy/infinite səhifələmə + skeleton + boş vəziyyət) — tam
 * siyahı heç vaxt yüklənmir. Jurnalda ARTIQ olan tələbə siyahıda görünür, amma
 * `disabled` gəlir və səbəbi yanında yazılır (server `hint` göndərir).
 *
 * YENİLƏNMƏ: əməldən sonra səhifə YENİDƏN YÜKLƏNMİR — cari URL fetch olunub
 * yalnız cədvəl gövdəsi (`[data-jgs-tbody]`) və modalın siyahısı yerində
 * dəyişdirilir, yeni sətir qısa vurğu ilə göstərilir. İSTİSNA: jurnal redaktə
 * rejimindədirsə (müəllim + koordinator eyni şəxsdir) yazılmamış qaralama
 * itməsin deyə `location.reload()` işlədilir — journal_grid.js qaralamanı
 * localStorage-dan məhz yüklənmədə bərpa edir.
 *
 * AJAX-SAFE: `window.EMSReady` + null-safe qarmaqlar; ikiqat init `data-jgs-ready`
 * bayrağı ilə kəsilir (modal partial swap olunsa da hadisələr təkrarlanmır).
 */
(function () {
    "use strict";

    var BUSY = "is-busy";
    var FOCUS = "is-focused";
    var CONFIRM = "is-confirm";
    var FLASH = "jgs-flash";
    var FOCUSABLE =
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

    var lastFocused = null;
    /* Server önbaxışı: tələbənin öz qrupunda bu fənn üzrə aktiv jurnalı varmı,
     * varsa nə qədər iş var və azad etmək mümkündürmü. Təsdiq düyməsi bundan
     * asılıdır — istifadəçi rəqəmləri görmədən birləşməni təsdiqləyə bilməz. */
    var merge = { conflict: false, blocked: "", token: 0 };

    function modalEl() {
        return document.querySelector("[data-jgs-modal]");
    }

    function attr(modal, name) {
        return (modal && modal.getAttribute(name)) || "";
    }

    function show(el) {
        if (el) el.hidden = false;
    }

    function hide(el) {
        if (el) el.hidden = true;
    }

    function toast(message, level) {
        if (message && window.EMSToast) window.EMSToast.show(message, level);
    }

    function setError(modal, message) {
        var box = modal.querySelector("[data-jgs-error]");
        if (!box) return;
        if (message) {
            box.textContent = message;
            show(box);
            // Səssiz uğursuzluq OLMASIN: səbəb həm modalda, həm toast-da.
            toast(message, "error");
        } else {
            box.textContent = "";
            hide(box);
        }
    }

    function errorText(err) {
        var payload = err && err.payload;
        if (payload && typeof payload === "object" && payload.error) return payload.error;
        return attr(modalEl(), "data-generic-error");
    }

    /* ── Fokus tələsi (a11y) ───────────────────────────────────────────────── */

    function focusables(modal) {
        var card = modal.querySelector(".jgs-card") || modal;
        return Array.prototype.filter.call(card.querySelectorAll(FOCUSABLE), function (el) {
            return el.offsetParent !== null || el === document.activeElement;
        });
    }

    /** Tab modaldan çıxmasın — ilk/son element arasında dövr etsin. */
    function trapTab(modal, event) {
        if (event.key !== "Tab") return;
        var list = focusables(modal);
        if (!list.length) return;
        var first = list[0];
        var last = list[list.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    }

    /* ── Modalın açılıb/bağlanması ─────────────────────────────────────────── */

    function openModal(focusEnrollmentId) {
        var modal = modalEl();
        if (!modal) return;
        // Bağlananda fokus GERİ qaytarılsın (çağıran düymə/çip).
        lastFocused = document.activeElement;
        setError(modal, "");
        modal.hidden = false;
        resetConfirms(modal);
        resetMerge(modal);
        if (focusEnrollmentId) {
            // Sətir çipindən gəlib: idarəetmə siyahısındakı həmin sətri işıqlandır.
            var item = modal.querySelector('[data-jgs-item="' + focusEnrollmentId + '"]');
            Array.prototype.forEach.call(modal.querySelectorAll("[data-jgs-item]"), function (row) {
                row.classList.remove(FOCUS);
            });
            if (item) {
                item.classList.add(FOCUS);
                if (item.scrollIntoView) item.scrollIntoView({ block: "nearest" });
                var removeBtn = item.querySelector("[data-jgs-remove]");
                if (removeBtn) removeBtn.focus();
                return;
            }
        }
        var input = modal.querySelector(".js-jgs-group input");
        if (input) input.focus();
    }

    /** İki addımlı təsdiq: birinci klik xəbərdarlıq edir, ikincisi silir. */
    function resetConfirms(modal) {
        Array.prototype.forEach.call(modal.querySelectorAll("[data-jgs-remove]"), function (button) {
            if (button.dataset.jgsLabel) {
                button.innerHTML = button.dataset.jgsLabel;
                delete button.dataset.jgsLabel;
            }
            button.classList.remove(CONFIRM);
        });
    }

    function armConfirm(modal, button) {
        resetConfirms(modal);
        button.dataset.jgsLabel = button.innerHTML;
        button.textContent = attr(modal, "data-confirm-label") || "?";
        button.classList.add(CONFIRM);
    }

    function closeModal() {
        var modal = modalEl();
        if (!modal) return;
        modal.hidden = true;
        setError(modal, "");
        resetConfirms(modal);
        if (lastFocused && document.contains(lastFocused) && lastFocused.focus) {
            lastFocused.focus();
        }
        lastFocused = null;
    }

    /* ── Seçicilər (qrup → tələbə kaskadı) ─────────────────────────────────── */

    function buildPickers(modal) {
        if (!window.EMSSearchableSelect) return null;
        var groupEl = modal.querySelector(".js-jgs-group");
        var studentEl = modal.querySelector(".js-jgs-student");
        if (!groupEl || !studentEl) return null;

        var group = window.EMSSearchableSelect.create(groupEl, {
            url: attr(modal, "data-group-url"),
            skeleton: true,
            emptyText: attr(modal, "data-group-empty"),
        });
        var student = window.EMSSearchableSelect.create(studentEl, {
            url: attr(modal, "data-student-url"),
            skeleton: true,
            emptyText: attr(modal, "data-student-empty"),
            dependParam: "group",
            getDependValue: function () {
                return group ? group.value() : "";
            },
        });
        if (!group || !student) return null;

        var studentField = modal.querySelector("[data-jgs-student-field]");
        group.on("change", function () {
            student.reset();
            resetMerge(modal);
            var picked = !!group.value();
            if (studentField) {
                studentField.classList.toggle("is-disabled", !picked);
            }
            // Göstəriş mərhələ ilə dəyişsin — qrup seçiləndən sonra «Əvvəlcə qrup
            // seçin…» qalsaydı, istifadəçini yanlış istiqamətləndirərdi.
            if (student.setPlaceholder) {
                student.setPlaceholder(
                    attr(modal, picked ? "data-student-placeholder-ready" : "data-student-placeholder-idle")
                );
            }
            syncSubmit(modal, group, student);
            setError(modal, "");
        });
        student.on("change", function () {
            resetMerge(modal);
            syncSubmit(modal, group, student);
            loadPreview(modal, group, student);
        });
        return { group: group, student: student };
    }

    /* ── Birləşmə önbaxışı ─────────────────────────────────────────────────── */

    function mergeBox(modal) {
        return modal.querySelector("[data-jgs-merge]");
    }

    function releaseChecked(modal) {
        var box = modal.querySelector("[data-jgs-release]");
        return !!(box && box.checked && !box.disabled);
    }

    /** Seçim dəyişəndə köhnə önbaxış İDDİASI qalmasın (yalan rəqəm göstərməsin). */
    function resetMerge(modal) {
        merge.conflict = false;
        merge.blocked = "";
        merge.token += 1;
        var box = mergeBox(modal);
        if (!box) return;
        box.hidden = true;
        var check = box.querySelector("[data-jgs-release]");
        if (check) {
            check.checked = false;
            check.disabled = false;
        }
        var blocked = box.querySelector("[data-jgs-merge-blocked]");
        if (blocked) {
            blocked.textContent = "";
            blocked.hidden = true;
        }
    }

    function statRow(list, label, value) {
        var dt = document.createElement("dt");
        dt.textContent = label;
        var dd = document.createElement("dd");
        dd.textContent = value;
        list.appendChild(dt);
        list.appendChild(dd);
    }

    /** Önbaxışı çək və paneli doldur — köhnəlmiş cavab (token) atılır. */
    function loadPreview(modal, group, student) {
        var url = attr(modal, "data-preview-url");
        if (!url || !group.value() || !student.value()) return;
        var token = ++merge.token;
        var query = url + "?group=" + encodeURIComponent(group.value()) + "&student=" + encodeURIComponent(student.value());
        window.EMSCore.fetchJSON(query)
            .then(function (payload) {
                if (token !== merge.token) return; // istifadəçi seçimi dəyişib
                renderPreview(modal, payload);
                syncSubmit(modal, group, student);
            })
            .catch(function () {
                if (token !== merge.token) return;
                // Önbaxış alınmadısa səssiz keçmirik: server qapısı onsuz da
                // birləşməni rədd edəcək, amma istifadəçi səbəbi görməlidir.
                setError(modal, attr(modal, "data-generic-error"));
            });
    }

    function renderPreview(modal, payload) {
        var box = mergeBox(modal);
        if (!box || !payload || !payload.conflict) return;
        merge.conflict = true;
        merge.blocked = payload.blocked || "";
        var stats = box.querySelector("[data-jgs-merge-stats]");
        if (stats) {
            stats.innerHTML = "";
            var source = (payload.sources || [])[0];
            if (source) {
                statRow(stats, attr(modal, "data-merge-label-source"), source.group || source.subject || "—");
                statRow(stats, attr(modal, "data-merge-label-marks"), source.marks + " / " + source.scored);
                statRow(
                    stats,
                    attr(modal, "data-merge-label-absence"),
                    source.absence_count + " q/b · " + source.absence_hours + " " + attr(modal, "data-merge-unit-hours")
                );
                statRow(
                    stats,
                    attr(modal, "data-merge-label-entry"),
                    source.entry_score + " / " + source.entry_score_max
                );
            }
        }
        var check = box.querySelector("[data-jgs-release]");
        var blocked = box.querySelector("[data-jgs-merge-blocked]");
        if (merge.blocked) {
            if (check) {
                check.checked = false;
                check.disabled = true;
            }
            if (blocked) {
                blocked.textContent = merge.blocked;
                blocked.hidden = false;
            }
        }
        box.hidden = false;
    }

    /** Düymənin aktivliyi + təsdiq xülasəsi (kim, haradan, hara). */
    function syncSubmit(modal, group, student) {
        var button = modal.querySelector("[data-jgs-submit]");
        var summary = modal.querySelector("[data-jgs-summary]");
        var hintbox = modal.querySelector("[data-jgs-hintbox]");
        var ready = !!(group.value() && student.value());
        // Münaqişə varsa təsdiq YALNIZ «azad et» işarələnəndən + səbəb
        // yazılandan sonra açılır (server qapısı da eynisini tələb edir).
        if (ready && merge.conflict) {
            var reasonEl = modal.querySelector("[data-jgs-reason]");
            var reasonText = reasonEl ? (reasonEl.value || "").trim() : "";
            ready = releaseChecked(modal) && reasonText.length >= 5;
        }
        if (button) button.disabled = !ready;
        if (hintbox) hintbox.hidden = !!group.value();
        if (!summary) return;
        if (!ready) {
            summary.hidden = true;
            return;
        }
        setText(modal, "[data-jgs-sum-student]", student.text());
        setText(modal, "[data-jgs-sum-group]", group.text());
        setText(modal, "[data-jgs-sum-target]", attr(modal, "data-subject-name") + " · " + attr(modal, "data-target-group"));
        summary.hidden = false;
    }

    function setText(root, selector, value) {
        var el = root.querySelector(selector);
        if (el) el.textContent = value || "";
    }

    /* ── Yerində yenilənmə ─────────────────────────────────────────────────── */

    /** Redaktə rejimi: yazılmamış qaralama var — tam yüklənmə daha təhlükəsizdir. */
    function gridIsEditable() {
        return !!document.querySelector("[data-jd-att], [data-jd-semselect], [data-jd-chip]");
    }

    /**
     * Cari səhifəni yenidən çəkib YALNIZ cədvəl gövdəsini və modalın siyahısını
     * dəyişdir. Tam səhifə yüklənməsi olmur: sürüşmə mövqeyi, açıq modal və
     * digər vəziyyət qorunur.
     */
    function refreshInPlace(modal, highlightId, doneMessage) {
        if (gridIsEditable()) {
            window.location.reload();
            return;
        }
        fetch(window.location.href, { headers: { "X-Requested-With": "XMLHttpRequest" } })
            .then(function (response) {
                if (!response.ok) throw new Error("bad status");
                return response.text();
            })
            .then(function (html) {
                var doc = new DOMParser().parseFromString(html, "text/html");
                var freshBody = doc.querySelector("[data-jgs-tbody]");
                var liveBody = document.querySelector("[data-jgs-tbody]");
                if (!freshBody || !liveBody) throw new Error("no grid");
                liveBody.innerHTML = freshBody.innerHTML;

                // Modalın «cari əlavələr» siyahısı + sayğaclar.
                swapNode(doc, modal, "[data-jgs-current]");
                var freshCount = doc.querySelector("[data-jgs-count]");
                var liveCount = modal.querySelector("[data-jgs-count]");
                if (freshCount && liveCount) liveCount.textContent = freshCount.textContent;
                syncButtonCount(doc);

                flashRow(highlightId);
                toast(doneMessage, "success");
            })
            .catch(function () {
                // Əməl SERVERDƏ alındı — yalnız təzələmə uğursuz oldu. Səssiz
                // qalmaq yanlış olardı: istifadəçiyə nə etməli olduğunu de.
                toast(attr(modal, "data-refresh-failed"), "warning");
            });
    }

    function swapNode(doc, modal, selector) {
        var fresh = doc.querySelector(selector);
        var live = modal.querySelector(selector);
        if (!fresh || !live) return;
        live.innerHTML = fresh.innerHTML;
        live.hidden = fresh.hidden;
    }

    /** Tabsbar düyməsindəki «neçə nəfər» nişanı. */
    function syncButtonCount(doc) {
        var fresh = doc.querySelector(".jd2-guest-btn__count");
        Array.prototype.forEach.call(document.querySelectorAll(".jd2-guest-btn"), function (button) {
            var live = button.querySelector(".jd2-guest-btn__count");
            if (fresh && live) {
                live.textContent = fresh.textContent;
            } else if (fresh && !live) {
                var span = document.createElement("span");
                span.className = "jd2-guest-btn__count";
                span.textContent = fresh.textContent;
                button.appendChild(span);
            } else if (!fresh && live) {
                live.remove();
            }
        });
    }

    /** Yeni sətir qısa vurğu ilə görünsün (harada dəyişiklik olduğu bilinsin). */
    function flashRow(enrollmentId) {
        if (!enrollmentId) return;
        var row = document.querySelector('[data-jd-enrollment="' + enrollmentId + '"]');
        if (!row) return;
        row.classList.add(FLASH);
        if (row.scrollIntoView) row.scrollIntoView({ block: "center", behavior: "smooth" });
        window.setTimeout(function () {
            row.classList.remove(FLASH);
        }, 2600);
    }

    /* ── Əməllər ───────────────────────────────────────────────────────────── */

    function submitAdd(modal, pickers) {
        var button = modal.querySelector("[data-jgs-submit]");
        var skeleton = modal.querySelector("[data-jgs-skeleton]");
        var reason = modal.querySelector("[data-jgs-reason]");
        if (!button || button.disabled) return;
        button.disabled = true;
        show(skeleton);
        setError(modal, "");
        window.EMSCore.fetchJSON(attr(modal, "data-add-url"), {
            method: "POST",
            data: {
                group: pickers.group.value(),
                student: pickers.student.value(),
                reason: reason ? reason.value : "",
                release_source: releaseChecked(modal),
            },
        })
            .then(function (payload) {
                hide(skeleton);
                if (reason) reason.value = "";
                resetMerge(modal);
                pickers.student.reset();
                syncSubmit(modal, pickers.group, pickers.student);
                closeModal();
                refreshInPlace(modal, payload && payload.enrollment_id, payload && payload.message);
            })
            .catch(function (err) {
                hide(skeleton);
                button.disabled = false;
                setError(modal, errorText(err));
            });
    }

    function submitRemove(modal, enrollmentId, trigger) {
        if (!enrollmentId) return;
        var item = modal.querySelector('[data-jgs-item="' + enrollmentId + '"]');
        if (item) item.classList.add(BUSY);
        if (trigger) trigger.disabled = true;
        setError(modal, "");
        window.EMSCore.fetchJSON(attr(modal, "data-remove-url"), {
            method: "POST",
            data: { enrollment: enrollmentId },
        })
            .then(function (payload) {
                refreshInPlace(modal, null, (payload && payload.message) || attr(modal, "data-removed-message"));
            })
            .catch(function (err) {
                if (item) item.classList.remove(BUSY);
                if (trigger) trigger.disabled = false;
                modal.hidden = false;
                setError(modal, errorText(err));
            });
    }

    /* ── Bağlanma ──────────────────────────────────────────────────────────── */

    function init() {
        var modal = modalEl();
        if (!modal || modal.getAttribute("data-jgs-ready") === "1") return;
        modal.setAttribute("data-jgs-ready", "1");

        var pickers = buildPickers(modal);

        // Birləşmə şərtləri (səbəb + «azad et») dəyişəndə təsdiq düyməsi yenilənsin.
        function resync() {
            if (pickers) syncSubmit(modal, pickers.group, pickers.student);
        }
        modal.addEventListener("input", function (event) {
            if (event.target && event.target.closest("[data-jgs-reason]")) resync();
        });
        modal.addEventListener("change", function (event) {
            if (event.target && event.target.closest("[data-jgs-release]")) {
                setError(modal, "");
                resync();
            }
        });

        document.addEventListener("click", function (event) {
            var target = event.target;
            if (!(target instanceof Element)) return;

            if (target.closest("[data-jgs-open]")) {
                event.preventDefault();
                openModal(null);
                return;
            }
            var chip = target.closest("[data-jgs-focus]");
            if (chip) {
                event.preventDefault();
                openModal(chip.getAttribute("data-jgs-focus"));
                return;
            }
            if (target.closest("[data-jgs-close]")) {
                event.preventDefault();
                closeModal();
                return;
            }
            if (target.closest("[data-jgs-submit]")) {
                event.preventDefault();
                if (pickers) submitAdd(modal, pickers);
                return;
            }
            var remover = target.closest("[data-jgs-remove]");
            if (remover) {
                event.preventDefault();
                if (!remover.classList.contains(CONFIRM)) {
                    armConfirm(modal, remover);
                    return;
                }
                submitRemove(modal, remover.getAttribute("data-jgs-remove"), remover);
            }
        });

        document.addEventListener("keydown", function (event) {
            var live = modalEl();
            if (!live || live.hidden) return;
            if (event.key === "Escape") {
                closeModal();
                return;
            }
            trapTab(live, event);
        });
    }

    if (window.EMSReady) {
        window.EMSReady(init);
    } else {
        document.addEventListener("DOMContentLoaded", init);
    }
})();
