/* Jurnal iş sahəsi (mockup dizaynı): üç-vəziyyətli davamiyyət çipləri, sütun
   üzrə toplu i/e-q/b, sərbəst iş 1/0 çipləri + bal seçimləri, yeni-dərs / dərs-redaktə modalı
   (cədvəl slotundan saat seçimi + həftə pariteti), stepper↔tab sinxronu,
   kurs işi formu və qrup-siyahısı sətir kliki. Server qaydaları (bu-gün,
   2 saat pəncərəsi, tavanlar) hər halda yenidən yoxlanır — bu fayl yalnız UX-dir.

   BÖLGÜ (2026-09-21, modul ölçü büdcəsi ≤ 550 sətir) — 2 fayl, sıra ilə yüklənir:
     1) journal_grid.js              — çiplər, stepper, qaralama, təsdiq modalları (bu fayl);
                                       `window.EMSJournalGrid` ad sahəsini yaradır
     2) journal_grid_lesson_modal.js — yeni dərs / redaktə modalı; `openModal`-ı ad
                                       sahəsinə qeyd edir (stepper «Yeni dərs» addımı
                                       oradan çağırır — klik anında həll olunur). */
(function () {
    "use strict";

    var G = (window.EMSJournalGrid = window.EMSJournalGrid || {});

    // Vidcet (data-bootstrap-select) görünüşünü sinxronlayan ümumi köməkçi —
    // həm çip/bulk (bu fayl), həm də dərs modalı (2-ci fayl) işlədir.
    function setSelectValue(select, value) {
        if (!select) return;
        select.value = value || "";
        // data-bootstrap-select vidcetinin görünüşünü sinxronla.
        select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    // Modal açıqkən səhifə fonu sürüşməsin. Səhifənin scroll konteyneri <html>-dir
    // (body DEYİL — main.css), ona görə tək body.overflow işləmirdi; HƏM
    // documentElement HƏM body kilidlənir. Modal position:fixed olduğundan öz
    // daxili scroll-u (jd-modal-card: overflow:auto) təsirlənmir.
    function lockPageScroll() {
        document.documentElement.style.overflow = "hidden";
        document.body.style.overflow = "hidden";
    }
    function unlockPageScroll() {
        document.documentElement.style.overflow = "";
        document.body.style.overflow = "";
    }

    // ── Davamiyyət çipi: — → i/e → q/b → — ────────────────────────────────
    var CYCLE = { "": "present", present: "absent", absent: "" };
    var LABEL = { "": "—", present: "i/e", absent: "q/b" };

    function paintChip(chip, value) {
        chip.textContent = LABEL[value];
        chip.classList.toggle("att-chip--ie", value === "present");
        chip.classList.toggle("att-chip--qb", value === "absent");
        chip.classList.toggle("att-chip--empty", value === "");
    }

    function setCell(chip, value) {
        var input = chip.parentElement.querySelector("[data-jd-att]");
        if (!input) return;
        input.value = value;
        paintChip(chip, value);
        markDirty();
    }

    // ── Seminar/lab xanası: tək bootstrap-select (q/b · i/e · bal 0–10). ──
    // Seçim gizli att/score sahələrini sinxronlayır; bal seçilsə i/e avtomatik.
    function applySemSelect(select) {
        var td = select.closest("td");
        if (!td) return;
        var att = td.querySelector("[data-jd-sem-att]");
        var score = td.querySelector("[data-jd-sem-score]");
        var v = select.value;
        // q/b həmişə qırmızı görünsün deyə wrapper-ə vəziyyət işarəsi qoy (CSS oxuyur).
        var w = select.closest(".jd2-semselect");
        if (w) w.setAttribute("data-mark", v === "qb" ? "qb" : v === "ie" ? "ie" : v ? "score" : "empty");
        if (v === "qb") {
            if (att) att.value = "absent";
            if (score) score.value = "";
        } else if (v === "ie") {
            if (att) att.value = "present";
            if (score) score.value = "";
        } else if (v === "") {
            if (att) att.value = "";
            if (score) score.value = "";
        } else {
            // rəqəmsal bal → iştirak avtomatik i/e (present)
            if (att) att.value = "present";
            if (score) score.value = v;
        }
    }

    // Cədvəl başlığı bulk düyməsi: q/b → "qb", i/e → "ie" (bal saxlanılmır).
    function bulkSemSelect(select, mode) {
        setSelectValue(select, mode === "absent" ? "qb" : "ie");
    }

    // ── Stepper ↔ tab sinxronu ────────────────────────────────────────────
    function setStep(n) {
        var stepper = document.querySelector("[data-jd-stepper]");
        if (!stepper) return;
        stepper.querySelectorAll("[data-jd-step]").forEach(function (step) {
            var num = parseInt(step.getAttribute("data-jd-step"), 10);
            var no = step.querySelector(".jd2-step-no");
            var label = step.querySelector(".jd2-step-label");
            [no, label].forEach(function (el) {
                if (!el) return;
                el.classList.toggle("is-active", num === n);
                el.classList.toggle("is-done", num < n);
            });
        });
    }

    function stepOfActiveTab() {
        var active = document.querySelector("[data-journal-tabs] [data-jtab].is-active");
        var mapped = active && active.getAttribute("data-jd-step-of");
        return mapped ? parseInt(mapped, 10) : null;
    }

    // ── Kurs işi formu: sətirdən doldurma / sıfırlama ─────────────────────
    function fillCourseworkForm(btn) {
        var form = document.querySelector("[data-jd-cw-form]");
        if (!form) return;
        var studentSelect = form.querySelector("[data-jd-cw-student]");
        studentSelect.value = btn.getAttribute("data-enrollment") || "";
        studentSelect.dispatchEvent(new Event("change", { bubbles: true })); // vidcet sinxronu
        form.querySelector("[data-jd-cw-topic]").value = btn.getAttribute("data-topic") || "";
        form.querySelector("[data-jd-cw-score]").value = btn.getAttribute("data-score") || "";
        form.querySelector("[data-jd-cw-date]").value = btn.getAttribute("data-date") || "";
        var title = document.querySelector("[data-jd-cw-formtitle]");
        if (title && btn.getAttribute("data-student")) {
            title.textContent = interpolate(gettext("%(student)s — kurs işi"), { student: btn.getAttribute("data-student") }, true);
        }
        form.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    document.addEventListener("click", function (event) {
        var chip = event.target.closest("[data-jd-chip]");
        if (chip) {
            var input = chip.parentElement.querySelector("[data-jd-att]");
            setCell(chip, CYCLE[input ? input.value : ""]);
            return;
        }

        var bulk = event.target.closest("[data-jd-bulk]");
        if (bulk) {
            var lessonId = bulk.getAttribute("data-lesson");
            var value = bulk.getAttribute("data-jd-bulk");
            document
                .querySelectorAll('[data-jd-chip][data-lesson="' + lessonId + '"]')
                .forEach(function (cellChip) {
                    setCell(cellChip, value);
                });
            document
                .querySelectorAll('[data-jd-semselect][data-lesson="' + lessonId + '"]')
                .forEach(function (sel) {
                    bulkSemSelect(sel, value);
                });
            return;
        }

        var swChip = event.target.closest("[data-jd-sw-chip]");
        if (swChip) {
            var swInput = swChip.parentElement.querySelector("[data-jd-sw]");
            var next = swInput.value === "1" ? "0" : "1";
            swInput.value = next;
            swChip.textContent = next;
            swChip.classList.toggle("sw-chip--on", next === "1");
            swChip.classList.toggle("sw-chip--off", next === "0");
            recomputeSelfworkTotal(swChip.closest("[data-jd-sw-row]"));
            markDirty();
            return;
        }

        // ✕ — yadda saxlanılmamış dəyişiklik varsa modern təsdiq modalı.
        var winClose = event.target.closest(".jd2-winclose");
        if (winClose && isDirty()) {
            event.preventDefault();
            var leaveModal = document.querySelector("[data-jd-leave-modal]");
            if (leaveModal) {
                leaveModal.querySelector("[data-jd-leave-go]").setAttribute("href", winClose.getAttribute("href"));
                leaveModal.hidden = false;
                lockPageScroll();
            }
            return;
        }
        if (event.target.closest("[data-jd-leave-stay]")) {
            var lm = document.querySelector("[data-jd-leave-modal]");
            if (lm) { lm.hidden = true; unlockPageScroll(); }
            return;
        }

        // Qrup seçimi cədvəlində sətir kliki (düymənin özü istisna).
        var listRow = event.target.closest("[data-jl-href]");
        if (listRow && !event.target.closest("a, button, input, select")) {
            window.location.href = listRow.getAttribute("data-jl-href");
            return;
        }

        // Dərs tipi pilləri: submit-i açıq şəkildə göndər (submitter dəyəri ilə).
        var kindPill = event.target.closest(".jd2-kindpill");
        if (kindPill) {
            var filterForm = kindPill.closest("form");
            if (filterForm) {
                event.preventDefault();
                if (filterForm.requestSubmit) {
                    filterForm.requestSubmit(kindPill);
                } else {
                    filterForm.submit();
                }
            }
            return;
        }

        // Stepper: tab addımları + modal addımı.
        var stepTab = event.target.closest("[data-jd-step-tab]");
        if (stepTab && !stepTab.disabled) {
            var tabBtn = document.querySelector('[data-journal-tabs] [data-jtab="' + stepTab.getAttribute("data-jd-step-tab") + '"]');
            if (tabBtn) tabBtn.click();
            return;
        }
        var stepModal = event.target.closest("[data-jd-step-modal]");
        if (stepModal && !stepModal.disabled) {
            if (typeof G.openModal === "function") G.openModal(null);
            return;
        }

        // Tab kliki → stepper yenilə (journal_detail.js paneli dəyişir).
        var tabClick = event.target.closest("[data-journal-tabs] [data-jtab]");
        if (tabClick) {
            window.setTimeout(function () {
                var mapped = stepOfActiveTab();
                if (mapped) setStep(mapped);
            }, 0);
            return;
        }

        var cwEdit = event.target.closest("[data-jd-cw-edit]");
        if (cwEdit) {
            fillCourseworkForm(cwEdit);
            return;
        }
    });

    // İlkin stepper vəziyyəti (sessionStorage-dən bərpa olunan tab ola bilər).
    window.setTimeout(function () {
        var mapped = stepOfActiveTab();
        if (mapped) setStep(mapped);
    }, 0);

    // Yekun qiymət progress barları (CSP-safe: inline style yox, JS yazır).
    document.querySelectorAll("[data-jd-width]").forEach(function (bar) {
        bar.style.width = bar.getAttribute("data-jd-width") + "%";
    });

    // ── Sərbəst iş CƏMİ (canlı — 1/0 çipləri + bal seçimləri) ──────────────
    // Çeklist boşdursa CƏMİ köçürülmüş "arxiv" balını göstərir — selfwork_board.effective_total
    // güzgüsü; cəm 10 ilə kəsilir (selfwork_points.cap_total). Bal: [data-jd-swp] seçimi /
    // [data-jd-swp-ro] oxu-only (fənn qovluğu, kilidli xana).
    function recomputeSelfworkTotal(row) {
        if (!row) return;
        var total = 0;
        row.querySelectorAll("[data-jd-sw], [data-jd-sw-ro]").forEach(function (el) {
            var v = el.value !== undefined ? el.value : el.getAttribute("data-jd-sw-ro");
            if (v === "1") total += 1;
        });
        row.querySelectorAll("[data-jd-swp], [data-jd-swp-ro]").forEach(function (el) {
            var raw = el.hasAttribute("data-jd-swp-ro") ? el.getAttribute("data-jd-swp-ro") : el.value;
            var num = parseFloat(String(raw || "").replace(",", "."));
            if (!isNaN(num)) total += num;
        });
        total = Math.min(10, Math.round(total * 10) / 10);
        var out = row.querySelector("[data-jd-sw-total]");
        var archive = row.getAttribute("data-jd-sw-archive");
        if (out) out.textContent = total === 0 && archive !== null ? archive : String(total);
    }

    // ── Kollokvium CƏMİ (canlı — K1+K2+K3) ────────────────────────────────
    function refreshKollokviumSums() {
        document.querySelectorAll(".jd-kollokvium-form tbody tr").forEach(function (row) {
            var total = 0;
            var any = false;
            // Kollokvium xanaları: bootstrap-select (name=kscore__…) və ya kilidli
            // read-only span. Boş buraxılan bal 0 sayılır — CƏMİ həmişə rəqəmdir.
            row.querySelectorAll('select[name^="kscore__"], input[name^="kscore__"], .jd2-ro').forEach(function (el) {
                any = true;
                var raw = el.value !== undefined ? el.value : el.textContent;
                var num = parseFloat(String(raw).replace(",", "."));
                if (!isNaN(num)) total += num;
            });
            var out = row.querySelector("[data-jd-ksum]");
            if (out) out.textContent = any ? String(Math.round(total * 10) / 10) : "—";
        });
    }

    // ── Qaralama (localStorage) + dirty izləmə ────────────────────────────
    // [data-jd-draft] formlarındakı hər dəyişiklik brauzerdə saxlanılır —
    // səhifə yenilənsə də itmir; submit-də təmizlənir. Server qaydaları
    // (2 saat pəncərəsi, bu-gün) bərpadan sonra da öz yerindədir.
    var page = document.querySelector(".jd-page");
    var draftKey = "jdDraft:" + (page ? page.getAttribute("data-offering-id") || "" : "");
    var dirty = false;

    function markDirty() {
        dirty = true;
        saveDraft();
    }

    function isDirty() {
        return dirty;
    }

    function draftForms() {
        return Array.prototype.slice.call(document.querySelectorAll("form[data-jd-draft]"));
    }

    function saveDraft() {
        try {
            var data = {};
            draftForms().forEach(function (form) {
                form.querySelectorAll("input[name], select[name]").forEach(function (field) {
                    if (field.type === "hidden" && field.name === "csrfmiddlewaretoken") return;
                    if (field.name === "action") return;
                    data[field.name] = field.value;
                });
            });
            window.localStorage.setItem(draftKey, JSON.stringify(data));
        } catch (err) { /* localStorage bağlı ola bilər */ }
    }

    function restoreDraft() {
        var raw = null;
        try {
            raw = window.localStorage.getItem(draftKey);
        } catch (err) { /* ignore */ }
        if (!raw) return;
        var data;
        try {
            data = JSON.parse(raw);
        } catch (err) {
            return;
        }
        var changed = false;
        draftForms().forEach(function (form) {
            form.querySelectorAll("input[name], select[name]").forEach(function (field) {
                if (!(field.name in data)) return;
                if (field.type === "hidden" && field.name === "csrfmiddlewaretoken") return;
                if (field.name === "action") return;
                if (field.value !== data[field.name]) {
                    field.value = data[field.name];
                    changed = true;
                }
            });
        });
        if (changed) {
            dirty = true;
            repaintFromState();
        }
    }

    function clearDraft() {
        dirty = false;
        try {
            window.localStorage.removeItem(draftKey);
        } catch (err) { /* ignore */ }
    }

    // Bərpadan sonra çip/xana görünüşlərini gizli dəyərlərə uyğunlaşdır.
    function repaintFromState() {
        document.querySelectorAll("[data-jd-chip]").forEach(function (chip) {
            var input = chip.parentElement.querySelector("[data-jd-att]");
            if (input) paintChip(chip, input.value);
        });
        // Seminar select-ləri: gizli att/score dəyərlərinə uyğun seçimi bərpa et.
        document.querySelectorAll("[data-jd-semselect]").forEach(function (sel) {
            var td = sel.closest("td");
            var att = td.querySelector("[data-jd-sem-att]");
            var score = td.querySelector("[data-jd-sem-score]");
            var v = "";
            if (att && att.value === "absent") v = "qb";
            else if (score && score.value !== "") v = score.value;
            else if (att && att.value === "present") v = "ie";
            setSelectValue(sel, v);
            applySemSelect(sel); // ilkin yüklənmədə q/b rəngini (data-mark) də təyin edir
        });
        document.querySelectorAll("[data-jd-sw]").forEach(function (input) {
            var chip = input.parentElement.querySelector("[data-jd-sw-chip]");
            if (!chip) return;
            chip.textContent = input.value;
            chip.classList.toggle("sw-chip--on", input.value === "1");
            chip.classList.toggle("sw-chip--off", input.value !== "1");
        });
        document.querySelectorAll("[data-jd-swp]").forEach(function (sel) {
            setSelectValue(sel, sel.value); // bərpa olunmuş bal vidcetdə də görünsün
        });
        document.querySelectorAll("[data-jd-sw-row]").forEach(recomputeSelfworkTotal);
        refreshKollokviumSums();
    }

    document.addEventListener("input", function (event) {
        var field = event.target;
        if (field.name && field.name.indexOf("kscore__") === 0) refreshKollokviumSums();
        if (field.closest && field.closest("form[data-jd-draft]")) markDirty();
    });

    // Seminar select (bootstrap vidcet native "change" göndərir) → att/score sync.
    document.addEventListener("change", function (event) {
        var sel = event.target.closest && event.target.closest("[data-jd-semselect]");
        if (sel) {
            applySemSelect(sel);
            markDirty();
        }
        var ksel = event.target.closest && event.target.closest("[data-jd-kscore]");
        if (ksel) {
            refreshKollokviumSums();
            markDirty();
        }
        var swp = event.target.closest && event.target.closest("[data-jd-swp]");
        if (swp) {
            recomputeSelfworkTotal(swp.closest("[data-jd-sw-row]"));
            markDirty();
        }
    });

    document.addEventListener("submit", function (event) {
        if (event.target.matches && event.target.matches("form[data-jd-draft]")) clearDraft();
    });

    restoreDraft();
    refreshKollokviumSums();

    // ── Sərbəst iş mövzusu silmə: təsdiq modalı (bal itkisi xəbərdarlığı) ──
    function escapeHtml(s) {
        var d = document.createElement("div");
        d.textContent = s == null ? "" : String(s);
        return d.innerHTML;
    }

    function showSelfworkDeleteModal(delForm) {
        var title = (delForm.getAttribute("data-topic-title") || "").trim();
        var existing = document.querySelector(".jd-sw-del-overlay");
        if (existing) { existing.parentNode.removeChild(existing); }
        var overlay = document.createElement("div");
        overlay.className = "jd-sw-del-overlay";
        overlay.innerHTML =
            '<div class="jd-sw-del__box" role="alertdialog" aria-modal="true">' +
            '<div class="jd-sw-del__icon"><i class="fas fa-triangle-exclamation"></i></div>' +
            '<h3 class="jd-sw-del__title">' + gettext("Mövzunu silmək?") + '</h3>' +
            (title ? '<div class="jd-sw-del__topic">“' + escapeHtml(title) + '”</div>' : '') +
            '<p class="jd-sw-del__body">' + gettext("Bu mövzu silinəcək və") + ' <b>' + gettext("tələbələrin bu mövzu üzrə balları da silinəcək") + '</b>. ' + gettext("Bu əməliyyat geri qaytarıla bilməz.") + '</p>' +
            '<div class="jd-sw-del__actions">' +
            '<button type="button" class="jd-sw-del__cancel">' + gettext("Ləğv et") + '</button>' +
            '<button type="button" class="jd-sw-del__ok">' + gettext("Sil") + '</button>' +
            '</div></div>';
        function close() { if (overlay.parentNode) { overlay.parentNode.removeChild(overlay); } }
        overlay.addEventListener("click", function (e) { if (e.target === overlay) { close(); } });
        overlay.querySelector(".jd-sw-del__cancel").addEventListener("click", close);
        overlay.querySelector(".jd-sw-del__ok").addEventListener("click", function () {
            delForm.setAttribute("data-sw-del-ok", "1");
            close();
            delForm.submit();
        });
        document.addEventListener("keydown", function esc(e) {
            if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc); }
        });
        document.body.appendChild(overlay);
        overlay.querySelector(".jd-sw-del__ok").focus();
    }

    document.addEventListener("submit", function (event) {
        var delForm = event.target;
        if (!delForm.matches || !delForm.matches("[data-jd-sw-del]")) { return; }
        if (delForm.getAttribute("data-sw-del-ok") === "1") { return; } // təsdiqlənib
        event.preventDefault();
        showSelfworkDeleteModal(delForm);
    }, true);

    // ── Ümumi təsdiq modalı (info + təsdiq) — [data-jd-confirm] formları üçün ──
    // Native confirm() əvəzinə səliqəli modal (məs. dərs sütununu silmə). Başlıq/
    // mətn/düymə mətni forma data-confirm-* atributlarından oxunur. z-index 2000 →
    // dərs modalının (1080) üstündə görünür.
    function showJdConfirm(triggerForm, onOk) {
        var title = triggerForm.getAttribute("data-confirm-title") || gettext("Təsdiq");
        var body = triggerForm.getAttribute("data-confirm-body") || "";
        var detail = triggerForm.getAttribute("data-confirm-detail") || "";
        var okLabel = triggerForm.getAttribute("data-confirm-ok") || gettext("Təsdiqlə");
        var existing = document.querySelector(".jd-sw-del-overlay");
        if (existing) { existing.parentNode.removeChild(existing); }
        var overlay = document.createElement("div");
        overlay.className = "jd-sw-del-overlay";
        overlay.innerHTML =
            '<div class="jd-sw-del__box" role="alertdialog" aria-modal="true">' +
            '<div class="jd-sw-del__icon"><i class="fas fa-triangle-exclamation"></i></div>' +
            '<h3 class="jd-sw-del__title">' + escapeHtml(title) + '</h3>' +
            (detail ? '<div class="jd-sw-del__topic">' + escapeHtml(detail) + '</div>' : '') +
            (body ? '<p class="jd-sw-del__body">' + escapeHtml(body) + '</p>' : '') +
            '<div class="jd-sw-del__actions">' +
            '<button type="button" class="jd-sw-del__cancel">' + gettext("Ləğv et") + '</button>' +
            '<button type="button" class="jd-sw-del__ok">' + escapeHtml(okLabel) + '</button>' +
            '</div></div>';
        function close() { if (overlay.parentNode) { overlay.parentNode.removeChild(overlay); } }
        overlay.addEventListener("click", function (e) { if (e.target === overlay) { close(); } });
        overlay.querySelector(".jd-sw-del__cancel").addEventListener("click", close);
        overlay.querySelector(".jd-sw-del__ok").addEventListener("click", function () {
            close();
            if (typeof onOk === "function") {
                onOk();
            } else {
                triggerForm.setAttribute("data-jd-confirm-ok", "1");
                triggerForm.submit();
            }
        });
        document.addEventListener("keydown", function esc(e) {
            if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc); }
        });
        document.body.appendChild(overlay);
        overlay.querySelector(".jd-sw-del__ok").focus();
    }

    document.addEventListener("submit", function (event) {
        var f = event.target;
        if (!f.matches || !f.matches("[data-jd-confirm]")) { return; }
        if (f.getAttribute("data-jd-confirm-ok") === "1") { return; } // təsdiqlənib
        event.preventDefault();
        showJdConfirm(f);
    }, true);

    /* ---- ad sahəsi (journal_grid_lesson_modal.js buradan oxuyur) ---------- */
    G.setStep = setStep;
    G.stepOfActiveTab = stepOfActiveTab;
    G.showJdConfirm = showJdConfirm;
    G.setSelectValue = setSelectValue;
    G.lockPageScroll = lockPageScroll;
    G.unlockPageScroll = unlockPageScroll;
})();
