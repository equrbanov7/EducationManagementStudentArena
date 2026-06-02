document.addEventListener("DOMContentLoaded", function () {

  
      

    // ====== Keys (per exam) ======
    const examSlug = document.body.dataset.examSlug || "default_exam";
    const fileKey = `tqb_last_file_${examSlug}`;
  
    // ====== Helpers ======
    function setUploadUI(fileName = "", extension = "") {
      const display = document.getElementById("fileNameDisplay");
      const uploadZone = document.getElementById("dropZone");
      if (!display || !uploadZone) return;
  
      if (!fileName) {
        display.classList.remove("show");
        display.innerHTML = "";
        uploadZone.style.borderColor = "";
        uploadZone.style.background = "";
        return;
      }
  
      const ext = (extension || fileName.split(".").pop() || "").toLowerCase();
      const isPdf = ext === "pdf";
      const icon = isPdf ? "bi-file-earmark-pdf-fill" : "bi-file-earmark-check-fill";
      const color = isPdf ? "#e74c3c" : "#4361ee";
  
      display.classList.add("show");
      display.innerHTML = `
      <i class="bi ${icon}" style="color:${color}"></i>
      <span title="${String(fileName).replace(/"/g, "&quot;")}">${fileName}</span>
    `;
      uploadZone.style.borderColor = color;
      uploadZone.style.background = "#f8faff";
    }

    function highlightFormatTag(extension) {
        const tags = document.querySelectorAll(".format-tag");
        tags.forEach(t => {
          t.classList.remove("is-active", "is-pdf", "is-docx", "is-txt");
        });
      
        const ext = (extension || "").toLowerCase();
        const active = document.querySelector(`.format-tag[data-ext="${ext}"]`);
        if (!active) return;
      
        active.classList.add("is-active");
        if (ext === "pdf") active.classList.add("is-pdf");
        if (ext === "docx") active.classList.add("is-docx");
        if (ext === "txt") active.classList.add("is-txt");
      }
  
    function clearFileState() {
      try { localStorage.removeItem(fileKey); } catch (e) {}
      setUploadUI("", "");
  
      const fileInput = document.getElementById("fileInput");
      if (fileInput) fileInput.value = "";
    }
  
    function clearTextareaState() {
      // həm preview form-da, həm save form-da ola bilər
      document.querySelectorAll('textarea[name="raw_text"]').forEach(t => t.value = "");
    }
  
    function resetWarningUI() {
      const totalWarnDisplay = document.getElementById("totalWarnings");
      if (totalWarnDisplay) totalWarnDisplay.innerText = "0";
  
      const totalDup = document.getElementById("totalDuplicates");
      if (totalDup) totalDup.innerText = "0";
    }
  
    function removePreviewSectionFromDOM() {
      // parsed nəticələrin blokunu DOM-dan sil (refresh etməsən belə təmiz görünsün)
      const results = document.querySelector(".results-container");
      if (results) results.remove();
    }
  
    // ====== ✅ CLEAR button ======
    const clearBtn = document.getElementById("clearBtn");
    if (clearBtn) {
      clearBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
  
        // 1) localStorage + file UI sıfırla
        clearFileState();
  
        // 2) textarea sıfırla
        clearTextareaState();
  
        // 3) warning/duplicate UI sıfırla
        resetWarningUI();
  
        // 4) nəticə bölməsini DOM-dan sil (gözlə görünən təmizlik)
        removePreviewSectionFromDOM();
  
        // 5) ən vacibi: “ilk giriş” kimi olsun deyə GET-ə qayıt
        // (server-side parsed da yox olacaq)
        const cleanUrl = window.location.origin + window.location.pathname;
        window.location.href = cleanUrl;
      });
    } else {
      // Debug üçün (istəsən sil)
      // console.warn("clearBtn tapılmadı. HTML-də id='clearBtn' var?");
    }
  
    // ====== Save basanda file adı storage sıfırlansın ======
    const saveForm = document.getElementById("saveForm");
    if (saveForm) {
      saveForm.addEventListener("submit", function () {
        const selectedInput = document.getElementById("selectedIndicesInput");
        if (selectedInput) {
          selectedInput.value = Array.from(document.querySelectorAll(".qcheck:checked"))
            .map(cb => cb.value)
            .join(",");
        }

        const pointsInput = document.getElementById("pointsPayloadInput");
        if (pointsInput) {
          const pointsPayload = {};
          document.querySelectorAll('input[name^="points_"]').forEach(input => {
            const match = input.name.match(/^points_(\d+)$/);
            if (match) pointsPayload[match[1]] = input.value || "";
          });
          pointsInput.value = JSON.stringify(pointsPayload);
        }

        document.querySelectorAll(".qcheck").forEach(cb => {
          cb.disabled = true;
        });
        document.querySelectorAll('input[name^="points_"]').forEach(input => {
          input.disabled = true;
        });
        clearFileState();
      });
    }
  
    // ====== File seçiləndə show + localStorage ======
    window.fileSelected = function (input) {
      if (input && input.files && input.files[0]) {
        const f = input.files[0];
        const fileName = f.name || "";
        const extension = (fileName.split(".").pop() || "").toLowerCase();
        highlightFormatTag(extension)
  
        setUploadUI(fileName, extension);

  
        try {
          localStorage.setItem(fileKey, JSON.stringify({ fileName, extension }));
        } catch (e) {}
      } else {
        clearFileState();
      }
    };
  
    // ====== Refresh sonrası file adını bərpa et ======
    (function restoreLastFileName() {
      let saved = null;
      try { saved = JSON.parse(localStorage.getItem(fileKey) || "null"); } catch (e) {}
  
      if (saved && saved.fileName) {
        setUploadUI(saved.fileName, saved.extension || "");
      }
    })();
  
    // ====== Warning sayını göstər (preview render olunanda) ======
    const warningCount = document.querySelectorAll(".warning-msg").length;
    const totalWarnDisplay = document.getElementById("totalWarnings");
    if (totalWarnDisplay) totalWarnDisplay.innerText = String(warningCount);
  
    // ====== Row selection ======
    function updateCardStyle(card, isChecked) {
      if (!card) return;
      card.classList.toggle("is-selected", !!isChecked);
    }
  
    window.toggleRow = function (card, evt) {
      const e = evt || window.event;

      if (e && e.target && e.target.type === "checkbox") {
        updateCardStyle(card, e.target.checked);
        return;
      }

      if (e && e.target && e.target.closest) {
        const interactiveSelector = [
          ".warning-box",
          ".warning-box__summary",
          ".warning-msg__jump",
          "button",
          "a",
          "input",
          "textarea",
          "select",
          "details",
          "summary"
        ].join(",");
        if (e.target.closest(interactiveSelector)) return;
      }
  
      const cb = card ? card.querySelector(".qcheck") : null;
      if (!cb) return;
  
      cb.checked = !cb.checked;
      updateCardStyle(card, cb.checked);
    };
  
    window.toggleAll = function (val) {
      document.querySelectorAll(".qcheck").forEach(cb => {
        cb.checked = val;
        updateCardStyle(cb.closest(".q-card"), val);
      });
    };

    // ====== Filter Toolbar (chip + stat-card + search) ======
    const filterToolbar = document.getElementById("qFilterToolbar");
    const questionList = document.getElementById("questionList");
    const emptyState = document.getElementById("filterEmptyState");
    const visibleCounter = document.getElementById("filterVisibleCount");
    const searchInput = document.getElementById("qSearch");

    function applyFilter(filterKey, searchTerm) {
      if (!questionList) return;
      const key = filterKey || "all";
      const term = (searchTerm || "").trim().toLowerCase();
      const cards = questionList.querySelectorAll(".q-card");

      let visible = 0;
      cards.forEach(card => {
        const flags = card.getAttribute("data-q-flags") || "";
        let matchesFilter = true;
        if (key !== "all") {
          matchesFilter = flags.split(/\s+/).includes(key);
        }

        let matchesSearch = true;
        if (term) {
          const text = (card.querySelector(".q-text")?.textContent || "").toLowerCase();
          const optsText = Array.from(card.querySelectorAll(".opt-text"))
            .map(n => n.textContent.toLowerCase())
            .join(" ");
          matchesSearch = text.includes(term) || optsText.includes(term);
        }

        if (matchesFilter && matchesSearch) {
          card.removeAttribute("hidden");
          visible++;
        } else {
          card.setAttribute("hidden", "");
        }
      });

      if (emptyState) {
        if (visible === 0) emptyState.removeAttribute("hidden");
        else emptyState.setAttribute("hidden", "");
      }

      if (visibleCounter) {
        if (key === "all" && !term) {
          visibleCounter.textContent = "";
        } else {
          visibleCounter.textContent = visible + " / " + cards.length;
        }
      }
    }

    function setActiveChip(filterKey) {
      if (!filterToolbar) return;
      filterToolbar.setAttribute("data-active-filter", filterKey || "all");
      filterToolbar.querySelectorAll(".filter-chip").forEach(chip => {
        const isActive = chip.getAttribute("data-filter") === filterKey;
        chip.classList.toggle("is-active", isActive);
      });
    }

    function activateFilter(filterKey) {
      // disabled chip-ə klik effekti olmasın
      if (!filterToolbar) return;
      const chip = filterToolbar.querySelector('.filter-chip[data-filter="' + filterKey + '"]');
      if (chip && chip.hasAttribute("disabled")) return;

      setActiveChip(filterKey);
      applyFilter(filterKey, searchInput ? searchInput.value : "");

      // İlk görünən karta scroll et
      if (filterKey !== "all" && questionList) {
        const firstVisible = questionList.querySelector(".q-card:not([hidden])");
        if (firstVisible && typeof firstVisible.scrollIntoView === "function") {
          firstVisible.scrollIntoView({ behavior: "smooth", block: "center" });
          firstVisible.classList.add("is-flash");
          setTimeout(() => firstVisible.classList.remove("is-flash"), 1200);
        }
      }
    }

    // chip klikləri
    if (filterToolbar) {
      filterToolbar.querySelectorAll(".filter-chip").forEach(chip => {
        chip.addEventListener("click", function (e) {
          e.preventDefault();
          if (chip.hasAttribute("disabled")) return;
          activateFilter(chip.getAttribute("data-filter") || "all");
        });
      });
    }

    // stat-card klik → uyğun filtri aktiv et və scroll
    document.querySelectorAll("[data-filter-trigger]").forEach(card => {
      card.addEventListener("click", function () {
        const key = card.getAttribute("data-filter-trigger");
        if (!key) return;
        activateFilter(key);
        if (filterToolbar) {
          filterToolbar.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    });

    // search input
    if (searchInput) {
      let debounceTimer = null;
      searchInput.addEventListener("input", function () {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          const activeFilter = filterToolbar
            ? (filterToolbar.getAttribute("data-active-filter") || "all")
            : "all";
          applyFilter(activeFilter, searchInput.value);
        }, 180);
      });
    }

    // Dublikat referans jump-link
    document.querySelectorAll("[data-jump-to]").forEach(link => {
      link.addEventListener("click", function (e) {
        e.preventDefault();
        const targetId = link.getAttribute("data-jump-to");
        const target = document.getElementById(targetId);
        if (!target) return;

        // Hədəf gizli olsa filtri "all"-a qaytar
        if (target.hasAttribute("hidden")) {
          activateFilter("all");
        }
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        target.classList.add("is-flash");
        setTimeout(() => target.classList.remove("is-flash"), 1500);
      });
    });

    // ====== Faylın client-side validation (UX cəhəti — server-side əsasdır) ======
    // .docm/.exe və s. uzantıları client-side bloklayırıq və istifadəçiyə yumşaq mesaj.
    const FORBIDDEN_EXT = ["docm", "dotm", "xlsm", "pptm", "bin", "exe", "scr", "js", "html", "htm"];
    const MAX_FILE_BYTES = 5 * 1024 * 1024; // 5MB — server limiti ilə uyğun
    function validateFileClientSide(input) {
      if (!input || !input.files || !input.files[0]) return true;
      const f = input.files[0];
      const ext = (f.name.split(".").pop() || "").toLowerCase();
      if (FORBIDDEN_EXT.includes(ext)) {
        alert("Bu fayl növü təhlükəsizlik səbəbi ilə qəbul edilmir. Yalnız .docx / .pdf / .txt yükləyin.");
        input.value = "";
        clearFileState();
        return false;
      }
      if (f.size > MAX_FILE_BYTES) {
        alert("Fayl ölçüsü 5MB-dan böyükdür.");
        input.value = "";
        clearFileState();
        return false;
      }
      return true;
    }

    const mainFileInput = document.getElementById("fileInput");
    if (mainFileInput) {
      mainFileInput.addEventListener("change", function () {
        validateFileClientSide(mainFileInput);
      });
    }
    const aiFileInput = document.getElementById("testAiSourceFile");
    if (aiFileInput) {
      aiFileInput.addEventListener("change", function () {
        validateFileClientSide(aiFileInput);
      });
    }

    // ====== Scroll-to-top FAB ======
    (function setupScrollTopFab() {
      const fab = document.createElement("button");
      fab.type = "button";
      fab.className = "scroll-top-fab";
      fab.setAttribute("aria-label", "Yuxarı qayıt");
      fab.innerHTML = '<i class="fas fa-arrow-up"></i>';
      document.body.appendChild(fab);

      function update() {
        if (window.scrollY > 480) fab.classList.add("is-visible");
        else fab.classList.remove("is-visible");
      }
      window.addEventListener("scroll", update, { passive: true });
      fab.addEventListener("click", function () {
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
      update();
    })();

    // ====== Preview submit-dən sonra avtomatik scroll ======
    (function autoScrollAfterPreview() {
      const wrapper = document.querySelector(".bulk-page-wrapper");
      if (!wrapper || wrapper.getAttribute("data-auto-scroll-preview") !== "true") return;
      const target = document.querySelector(".results-container");
      if (!target) return;
      // Kiçik gecikmə ilə smooth scroll — render bitsin
      setTimeout(() => {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 250);
    })();
  });
