/* Jurnal iş sahəsi — 2/2: yeni dərs / dərs-redaktə modalı (cədvəl slotundan
   saat seçimi + həftə pariteti, silmə təsdiqi, sənədli düzəliş sahələri,
   bağlanış təsdiqi). journal_grid.js-dən SONRA yüklənir: stepper, təsdiq modalı
   və select/scroll köməkçiləri `window.EMSJournalGrid`-dən alınır, `openModal`
   isə oraya qeyd olunur. Bölgü: 2026-09-21 (modul ölçü büdcəsi). */
(function () {
    "use strict";

    var G = (window.EMSJournalGrid = window.EMSJournalGrid || {});
    var setStep = G.setStep;
    var stepOfActiveTab = G.stepOfActiveTab;
    var showJdConfirm = G.showJdConfirm;
    var setSelectValue = G.setSelectValue;
    var lockPageScroll = G.lockPageScroll;
    var unlockPageScroll = G.unlockPageScroll;

    // ── Yeni dərs / redaktə modalı ────────────────────────────────────────
    var modal = document.querySelector("[data-jd-lesson-modal]");
    if (!modal) return;

    var form = modal.querySelector("[data-jd-lesson-form]");
    var actionInput = modal.querySelector("[data-jd-lesson-action]");
    var deleteBtn = modal.querySelector("[data-jd-lesson-delete]");
    var titleAdd = modal.querySelector("[data-jd-modal-title-add]");
    var titleEdit = modal.querySelector("[data-jd-modal-title-edit]");
    var dateInput = modal.querySelector("[data-jd-lesson-date]");
    var timeSelect = modal.querySelector("[data-jd-lesson-time]");
    var parityBadge = modal.querySelector("[data-jd-parity-badge]");

    function mondayOf(dateStr) {
        var d = new Date(dateStr + "T12:00:00");
        d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
        return d;
    }

    function refreshParityBadge() {
        if (!parityBadge || !dateInput || !dateInput.value) return;
        var periodStart = modal.getAttribute("data-period-start");
        if (!periodStart) {
            parityBadge.hidden = true;
            return;
        }
        // Backend qaydası ilə eyni: semestr başlanğıc həftəsi = 1 (ÜST/odd).
        var weeks = Math.floor((mondayOf(dateInput.value) - mondayOf(periodStart)) / 604800000) + 1;
        var isUst = weeks % 2 === 1;
        parityBadge.textContent = isUst ? gettext("ÜST HƏFTƏ") : gettext("ALT HƏFTƏ");
        parityBadge.classList.toggle("is-ust", isUst);
        parityBadge.classList.toggle("is-alt", !isUst);
        parityBadge.hidden = false;
    }

    if (dateInput) {
        dateInput.addEventListener("change", refreshParityBadge);
    }

    // ── Dərs saatı MƏCBURİDİR: seçilmədən dərs əlavə/redaktə tətbiq olunmasın ──
    var timeError = modal.querySelector("[data-jd-time-error]");
    function timeToggle() {
        var wrap = timeSelect ? timeSelect.closest(".bootstrap-single-select") : null;
        return wrap ? wrap.querySelector(".bootstrap-single-select__toggle") : null;
    }
    if (form && timeSelect) {
        form.addEventListener("submit", function (ev) {
            // Silmə (do_delete) dərs saatı tələb etmir — yalnız redaktə/əlavə üçün.
            if (ev.submitter && ev.submitter.name === "do_delete") {
                return;
            }
            if (!timeSelect.value) {
                ev.preventDefault();
                if (timeError) timeError.hidden = false;
                var tg = timeToggle();
                if (tg) { tg.classList.add("is-invalid"); tg.focus(); }
            }
        });
        timeSelect.addEventListener("change", function () {
            if (timeSelect.value) {
                if (timeError) timeError.hidden = true;
                var tg = timeToggle();
                if (tg) tg.classList.remove("is-invalid");
            }
        });
    }

    // Silmə düyməsi redaktə formasının içindədir → təsdiq → formu do_delete ilə göndər.
    // Kilidli dərsdə PDF `required` olduğundan requestSubmit brauzer validasiyasını
    // işlədir (sənədsiz silmək OLMAZ); server də apply_lesson_deletion-da yoxlayır.
    if (deleteBtn && form) {
        deleteBtn.addEventListener("click", function (ev) {
            ev.preventDefault();
            showJdConfirm(deleteBtn, function () {
                if (form.requestSubmit) {
                    form.requestSubmit(deleteBtn);
                } else {
                    var h = document.createElement("input");
                    h.type = "hidden";
                    h.name = "do_delete";
                    h.value = "1";
                    form.appendChild(h);
                    form.submit();
                }
            });
        });
    }

    function openModal(editData) {
        var editing = Boolean(editData);
        titleAdd.hidden = editing;
        titleEdit.hidden = !editing;
        deleteBtn.hidden = !editing;
        // Dərs saatı xəta vəziyyətini sıfırla (əvvəlki cəhddən qalmasın).
        if (timeError) timeError.hidden = true;
        var _tg = timeToggle();
        if (_tg) _tg.classList.remove("is-invalid");
        var kindField = modal.querySelector("select[data-jd-lesson-kind]");
        var topicField = modal.querySelector("[data-jd-lesson-topic]");
        if (editing) {
            form.action = editData.actionUrl;
            actionInput.value = "update_lesson";
            // Təsdiq modalında hansı dərs silinir — tarix + mövzu göstər.
            deleteBtn.setAttribute("data-confirm-detail", (editData.date || "") + (editData.topic ? " · " + editData.topic : ""));
            dateInput.value = editData.date;
            if (kindField) setSelectValue(kindField, editData.kind);
            if (topicField) {
                if (topicField.tagName === "SELECT") setSelectValue(topicField, editData.topic || "");
                else topicField.value = editData.topic || "";
            }
            setSelectValue(modal.querySelector("[data-jd-lesson-hours]"), String(editData.hours || 2));
            // Standart dərs saatı: mövcud start-end cütünü seçimdə tap.
            setSelectValue(timeSelect, editData.start && editData.end ? editData.start + "|" + editData.end : "");
            // Dərsin müəllimi (fənn 2 müəllim arasında bölünübsə).
            var instrField = modal.querySelector("[data-jd-lesson-instructor]");
            if (instrField && editData.instructor) setSelectValue(instrField, editData.instructor);
        } else {
            form.action = form.getAttribute("data-add-url");
            actionInput.value = "add_lesson";
        }
        // Korpus → otaq kaskadı ayrı modula (journal_lesson_room.js) buradan xəbər verilir.
        modal.dispatchEvent(new CustomEvent("jd:lesson-modal-open", { detail: editData || null, bubbles: true }));
        // Sənədli düzəliş sahələri (İKT): yalnız KİLİDLİ dərs redaktəsində — PDF
        // + qeyd məcburi olur; əlavə/kilidsiz redaktədə gizli və məcburiyyətsiz.
        var corrFields = modal.querySelector("[data-jd-corr-fields]");
        if (corrFields) {
            // Blok yalnız korrektor-only (İKT) üçün render olunur → redaktədə HƏR
            // halda (kilidli/kilidsiz) sənəd tələb olunur.
            var needCorr = editing;
            corrFields.hidden = !needCorr;
            var doc = corrFields.querySelector("[data-jd-corr-doc]");
            var note = corrFields.querySelector("[data-jd-corr-note]");
            if (doc) doc.required = needCorr;
            if (note) note.required = needCorr;
        }
        refreshParityBadge();
        setStep(3); // stepper: Yeni dərs addımı
        modal.hidden = false;
        lockPageScroll();
    }

    G.openModal = openModal;

    function closeModal() {
        modal.hidden = true;
        delete modal.dataset.dirty;
        unlockPageScroll();
        var mapped = stepOfActiveTab();
        if (mapped) setStep(mapped); // modal bağlandı → aktiv tabın addımına qayıt
    }

    // Yadda saxlanılmamış dəyişiklik varsa (bayraq: journal_lesson_modal_guard.js) əvvəl soruş.
    function requestClose() {
        var hint = modal.querySelector("[data-jd-modal-unsaved]");
        if (modal.dataset.dirty === "1" && hint) { showJdConfirm(hint, closeModal); return; }
        closeModal();
    }

    document.addEventListener("click", function (event) {
        if (event.target.closest("[data-jd-open-lesson-modal]")) {
            openModal(null);
            return;
        }
        var editBtn = event.target.closest("[data-jd-edit-lesson]");
        if (editBtn) {
            openModal({
                actionUrl: editBtn.getAttribute("data-action-url"),
                date: editBtn.getAttribute("data-lesson-date"),
                kind: editBtn.getAttribute("data-lesson-kind"),
                topic: editBtn.getAttribute("data-lesson-topic"),
                hours: editBtn.getAttribute("data-lesson-hours"),
                start: editBtn.getAttribute("data-lesson-start"),
                end: editBtn.getAttribute("data-lesson-end"),
                instructor: editBtn.getAttribute("data-lesson-instructor"),
                room: editBtn.getAttribute("data-lesson-room"),
                locked: editBtn.getAttribute("data-lesson-locked") === "1",
            });
            return;
        }
        if (event.target.closest("[data-jd-modal-close]")) requestClose();
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && !modal.hidden && !document.querySelector(".jd-sw-del-overlay")) requestClose();
    });
})();
