document.addEventListener("DOMContentLoaded", function() {

    // ---- Fayl adı üçün localStorage key (hər imtahan üçün ayrı) ----
    const examSlug = document.body.dataset.examSlug || "default_exam";
    const fileKey = `tqb_last_file_${examSlug}`;

      // ✅ Save (Seçilənləri Yadda Saxla) basanda file-name storage sıfırlansın
        const saveForm = document.getElementById("saveForm");
        if (saveForm) {
            saveForm.addEventListener("submit", function () {
            // localStorage-dan sil
            try { localStorage.removeItem(fileKey); } catch (e) {}

            // UI-da da gizlət (redirect olsa da problem deyil, amma dərhal silinsin)
            const display = document.getElementById("fileNameDisplay");
            const uploadZone = document.getElementById("dropZone");
            if (display) {
                display.classList.remove("show");
                display.innerHTML = "";
            }
            if (uploadZone) {
                uploadZone.style.borderColor = "";
                uploadZone.style.background = "";
            }
            });
        }

    // 1) Fayl seçildikdə vizual effekt + fayl adını göstər + localStorage-da saxla
    window.fileSelected = function(input) {
        const display = document.getElementById("fileNameDisplay");
        const uploadZone = document.getElementById("dropZone");

        if (!display || !uploadZone) return;

        if (input.files && input.files[0]) {
            const f = input.files[0];
            const fileName = f.name || "";
            const extension = fileName.split(".").pop().toLowerCase();

            const isPdf = extension === "pdf";
            const icon = isPdf ? "bi-file-earmark-pdf-fill" : "bi-file-earmark-check-fill";
            const color = isPdf ? "#e74c3c" : "#4361ee";

            display.classList.add("show");
            display.innerHTML = `<i class="bi ${icon}" style="color:${color}"></i><span>${fileName}</span>`;

            uploadZone.style.borderColor = color;
            uploadZone.style.background = "#f8faff";

            // >>> ƏLAVƏ: refresh-dən sonra ad görünsün deyə saxlayırıq
            try {
                localStorage.setItem(fileKey, JSON.stringify({ fileName, extension }));
            } catch (e) {}
        } else {
            // fayl seçimi ləğv olunubsa
            display.classList.remove("show");
            display.innerHTML = "";
            try { localStorage.removeItem(fileKey); } catch (e) {}
        }
    };

    // >>> ƏLAVƏ: Səhifə refresh olandan sonra son seçilən fayl adını ekrana qaytar
    (function restoreLastFileName() {
        const display = document.getElementById("fileNameDisplay");
        const uploadZone = document.getElementById("dropZone");
        if (!display || !uploadZone) return;

        let saved = null;
        try {
            saved = JSON.parse(localStorage.getItem(fileKey) || "null");
        } catch (e) {}

        if (saved && saved.fileName) {
            const extension = (saved.extension || "").toLowerCase();
            const isPdf = extension === "pdf";
            const icon = isPdf ? "bi-file-earmark-pdf-fill" : "bi-file-earmark-check-fill";
            const color = isPdf ? "#e74c3c" : "#4361ee";

            display.classList.add("show");
            display.innerHTML = `<i class="bi ${icon}" style="color:${color}"></i><span>${saved.fileName}</span>`;

            uploadZone.style.borderColor = color;
            uploadZone.style.background = "#f8faff";
        }
    })();

    // 2. Warninglərin cəmi
    const warningCount = document.querySelectorAll(".warning-msg").length;
    const totalWarnDisplay = document.getElementById("totalWarnings");
    if (totalWarnDisplay) totalWarnDisplay.innerText = warningCount;

    // 3. Tək-tək sətir seçimi
    window.toggleRow = function(card) {
        if (event.target.type === "checkbox") {
            updateCardStyle(card, event.target.checked);
            return;
        }

        const cb = card.querySelector(".qcheck");
        cb.checked = !cb.checked;
        updateCardStyle(card, cb.checked);
    };

    function updateCardStyle(card, isChecked) {
        if (isChecked) card.classList.add("is-selected");
        else card.classList.remove("is-selected");
    }

    // 4. Hamısını Seç / Ləğv Et
    window.toggleAll = function(val) {
        const checkboxes = document.querySelectorAll(".qcheck");
        checkboxes.forEach(cb => {
            cb.checked = val;
            const card = cb.closest(".q-card");
            updateCardStyle(card, val);
        });
    };
});
