/* Dərs cədvəli grid-i: fənn detal modalı + slot-əlavə modalı.
   Delegated event-lər — profil SPA bölməsi AJAX ilə yenilənəndə də işləyir. */
(function () {
    "use strict";

    function root() {
        return document.querySelector("[data-schedule-root]");
    }

    function openModal(modal) {
        if (modal) {
            modal.hidden = false;
            document.body.style.overflow = "hidden";
        }
    }

    function closeModals() {
        document.querySelectorAll(".sgx-modal").forEach(function (m) {
            m.hidden = true;
        });
        document.body.style.overflow = "";
    }

    function setField(modal, name, value) {
        modal.querySelectorAll('[data-sgx-f="' + name + '"]').forEach(function (el) {
            el.textContent = value || "";
        });
    }

    function toggleRow(modal, name, show) {
        var row = modal.querySelector('[data-sgx-row="' + name + '"]');
        if (row) row.hidden = !show;
    }

    function fillSlotModal(card) {
        var host = root();
        if (!host) return;
        var modal = host.querySelector("[data-sgx-modal]");
        if (!modal) return;
        var d = card.dataset;

        setField(modal, "code", d.code);
        setField(modal, "name", d.name);
        setField(modal, "kind_label", d.kindLabel);
        setField(modal, "when", d.when);
        setField(modal, "parity_label", d.parityLabel);
        setField(modal, "room", d.room);
        setField(modal, "teacher", d.teacher);
        setField(modal, "group", d.group);
        setField(modal, "count", d.count);
        setField(modal, "ects", d.ects);

        toggleRow(modal, "room", Boolean(d.room));
        toggleRow(modal, "teacher", Boolean(d.teacher));
        toggleRow(modal, "group", Boolean(d.group));
        toggleRow(modal, "count", Boolean(d.count));
        toggleRow(modal, "ects", Boolean(d.ects));

        // Başlıq zolağının rəngi dərs növünə uyğun.
        var head = modal.querySelector("[data-sgx-modal-head]");
        if (head) {
            head.className = head.className.replace(/\s*sgx-modal-head--kind-\w+/g, "");
            if (d.kind) head.classList.add("sgx-modal-head--kind-" + d.kind);
        }

        // Tələbə statistikası (varsa).
        var statsWrap = modal.querySelector('[data-sgx-row="stats"]');
        if (statsWrap) {
            var hasStats = d.abs !== undefined;
            statsWrap.hidden = !hasStats;
            if (hasStats) {
                setField(modal, "abs", d.abs + " / " + (d.absLimit || "?") + " saat");
                setField(modal, "entry", d.entry + " / " + (d.entryMax || ""));
                var statusCard = statsWrap.querySelector(".sgx-stat-card--status");
                var barred = d.barred === "1";
                setField(modal, "status", barred ? statsWrap.dataset.barredLabel : statsWrap.dataset.okLabel);
                if (statusCard) {
                    statusCard.classList.toggle("is-barred", barred);
                    statusCard.classList.toggle("is-ok", !barred);
                }
            }
        }

        // Müəllim linkləri: jurnal (yeni tab) + slot silmə.
        var journalLink = modal.querySelector('[data-sgx-f="journal_link"]');
        if (journalLink) {
            if (d.journalUrl) {
                journalLink.href = d.journalUrl;
                journalLink.hidden = false;
            } else {
                journalLink.hidden = true;
            }
        }
        var delForm = modal.querySelector("[data-sgx-delete-form]");
        if (delForm) {
            if (d.deleteUrl) {
                delForm.action = d.deleteUrl;
                delForm.hidden = false;
            } else {
                delForm.hidden = true;
            }
        }

        openModal(modal);
    }

    document.addEventListener("click", function (event) {
        var card = event.target.closest("[data-sgx-slot]");
        if (card) {
            fillSlotModal(card);
            return;
        }
        if (event.target.closest("[data-sgx-open-add]")) {
            var host = root();
            openModal(host && host.querySelector("[data-sgx-add-modal]"));
            return;
        }
        if (event.target.closest("[data-sgx-close]")) {
            closeModals();
        }
    });

    // Slot silmə təsdiqi — inline `onsubmit` CSP-yə görə YAZILMIR (CLAUDE.md).
    document.addEventListener("submit", function (event) {
        var form = event.target.closest("[data-sgx-delete-form]");
        if (!form) return;
        var question = form.getAttribute("data-sgx-confirm");
        if (question && !window.confirm(question)) event.preventDefault();
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") closeModals();
    });
})();
