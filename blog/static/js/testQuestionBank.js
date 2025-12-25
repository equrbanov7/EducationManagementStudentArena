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
  });
  