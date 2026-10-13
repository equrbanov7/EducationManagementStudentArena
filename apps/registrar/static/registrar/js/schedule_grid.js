/* Dərs cədvəli grid-i: fənn detal modalı + slot-əlavə modalı.
   Delegated event-lər — profil SPA bölməsi AJAX ilə yenilənəndə də işləyir. */
(function () {
    "use strict";

    /* 2026-10-14: modal kartın ƏN YAXIN kökündə axtarılır. Əvvəl həmişə səhifənin
       BİRİNCİ `[data-schedule-root]`-u götürülürdü — «Cədvəl idarəetməsi»ndə (yalnız-oxu
       kartlar, müəllim görünüşü) belə kök yox idi və klik heç nə açmırdı; profil
       qabığında gizli bölmə DOM-da qalanda isə modal görünməyən paneldə açılırdı. */
    function root(from) {
        var near = from && from.closest ? from.closest("[data-schedule-root], [data-sedit-root]") : null;
        return near || document.querySelector(".profile-section-panel.is-active [data-schedule-root]")
            || document.querySelector("[data-schedule-root]");
    }

    var returnFocus = null;

    function openModal(modal, opener) {
        if (modal) {
            returnFocus = opener || document.activeElement;
            modal.hidden = false;
            document.body.style.overflow = "hidden";
            var close = modal.querySelector(".sgx-modal-close");
            if (close && close.focus) close.focus();
        }
    }

    function closeModals() {
        var wasOpen = false;
        document.querySelectorAll(".sgx-modal").forEach(function (m) {
            if (!m.hidden) wasOpen = true;
            m.hidden = true;
        });
        document.body.style.overflow = "";
        if (wasOpen && returnFocus && document.contains(returnFocus) && returnFocus.focus) {
            returnFocus.focus();
        }
        returnFocus = null;
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
        var host = root(card);
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

        // Müəllim linki: jurnal (yeni tab). Slot silmə forması URL auditi A11 (2026-10-10) ilə silindi.
        var journalLink = modal.querySelector('[data-sgx-f="journal_link"]');
        if (journalLink) {
            if (d.journalUrl) {
                journalLink.href = d.journalUrl;
                journalLink.hidden = false;
            } else {
                journalLink.hidden = true;
            }
        }
        openModal(modal, card);
    }

    document.addEventListener("click", function (event) {
        var card = event.target.closest("[data-sgx-slot]");
        if (card) {
            fillSlotModal(card);
            return;
        }
        if (event.target.closest("[data-sgx-open-add]")) {
            var host = root(event.target);
            openModal(host && host.querySelector("[data-sgx-add-modal]"));
            return;
        }
        if (event.target.closest("[data-sgx-close]")) {
            closeModals();
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && document.querySelector(".sgx-modal:not([hidden])")) closeModals();
    });

    // ── Tədris ili + yarım il seçicisi (R-4) ───────────────────────────────
    // Bölmə `?period=<id>` ilə yenidən yüklənir; profil SPA-sında shell içində
    // qalmaq üçün gizli `js-profile-section-link` klikləyirik (my-journal ilə
    // eyni müqavilə), standalone səhifədə isə adi naviqasiya.
    function gotoPeriod(periodId) {
        var term = document.querySelector("[data-sgx-term]");
        var base = (term && term.getAttribute("data-base-url")) || "";
        if (!periodId) return;
        if (!base) {
            window.location.search = "?period=" + encodeURIComponent(periodId);
            return;
        }
        var url = base + "?section=my-schedule&period=" + encodeURIComponent(periodId);
        var link = document.createElement("a");
        link.href = url;
        link.className = "js-profile-section-link";
        link.setAttribute("data-section", "my-schedule");
        link.style.display = "none";
        document.body.appendChild(link);
        link.click();
        setTimeout(function () { link.remove(); }, 0);
        if (!document.querySelector("[data-profile-sections-host]")) window.location.href = url;
    }

    document.addEventListener("change", function (event) {
        var yearSelect = event.target.closest("[data-sgx-year]");
        if (yearSelect) {
            var year = yearSelect.value;
            var periodSelect = document.querySelector("[data-sgx-period]");
            if (!periodSelect) return;
            var first = null;
            Array.prototype.forEach.call(periodSelect.options, function (option) {
                var match = option.getAttribute("data-year") === year;
                option.hidden = !match;
                if (match && first === null) first = option.value;
            });
            if (typeof periodSelect._refreshBootstrapSelect === "function") periodSelect._refreshBootstrapSelect();
            if (first) gotoPeriod(first);
            return;
        }
        var periodSelect2 = event.target.closest("[data-sgx-period]");
        if (periodSelect2) gotoPeriod(periodSelect2.value);
    });
})();
