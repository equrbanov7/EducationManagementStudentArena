/* testQuestionBank_upload.js — toplu sual iş sahəsi — 2/2:
 * faylın client-side validasiyası, submit-dən əvvəl asinxron mətn çıxarma
 * (P3-b), uzun submit qoruyucusu, scroll-to-top FAB, preview-dan sonra avto-scroll.
 * testQuestionBank.js-dən SONRA yüklənir (DOMContentLoaded sırası): `clearFileState`
 * `window.EMSTestQuestionBank`-dan, `showWorkbenchError` `window`-dan oxunur.
 * 2026-09-21 bölgüsü (modul ölçü büdcəsi).
 */
document.addEventListener("DOMContentLoaded", function () {
    const TQB = window.EMSTestQuestionBank || {};
    function clearFileState() {
      if (typeof TQB.clearFileState === "function") TQB.clearFileState();
    }
    function showWorkbenchError(message) {
      (window.showWorkbenchError || window.alert)(message);
    }

    // ====== Faylın client-side validation (UX cəhəti — server-side əsasdır) ======
    // Köhnə Word (.doc) və macro/executable uzantılar bloklanır; .docx 2026-09-14-dən idxal edilir.
    const FORBIDDEN_EXT = ["doc", "docm", "dotm", "dotx", "rtf", "xlsm", "pptm", "bin", "exe", "scr", "js", "html", "htm", "zip"];
    const MAX_FILE_BYTES = 45 * 1024 * 1024; // 45MB — server limiti ilə uyğun
    function validateFileClientSide(input) {
      if (!input || !input.files || !input.files[0]) return true;
      const f = input.files[0];
      const ext = (f.name.split(".").pop() || "").toLowerCase();
      if (FORBIDDEN_EXT.includes(ext)) {
        showWorkbenchError(gettext("Bu fayl növü təhlükəsizlik səbəbi ilə qəbul edilmir. Yalnız .pdf / .docx / .txt / .png / .jpg yükləyin."));
        input.value = "";
        clearFileState();
        return false;
      }
      if (f.size > MAX_FILE_BYTES) {
        showWorkbenchError(gettext("Fayl ölçüsü 45MB-dan böyükdür."));
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


    // P3-b (2026-07-02): fayl seçilibsə submit-dən əvvəl mətn worker-də çıxarılır
    // (start + status poll, düstur-şəkil stash daxil). Endpoint yoxdursa köhnə
    // sinxron POST davranışı qalır.
    function getCsrfTokenTQ() {
      const el = document.querySelector("[name=csrfmiddlewaretoken]");
      if (el && el.value) return el.value;
      const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
      return m ? decodeURIComponent(m[1]) : "";
    }

    function pollExtractJob(statusUrl, attempt) {
      return fetch(statusUrl, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin"
      })
        .then(function (r) { return r.json(); })
        .then(function (json) {
          if (json.status === "success") return json;
          if (json.status === "failed") throw new Error(json.error || gettext("Fayldan mətn çıxarıla bilmədi."));
          if (attempt >= 240) throw new Error(gettext("Mətn çıxarma çox uzun çəkdi. Yenidən cəhd edin."));
          return new Promise(function (res) { setTimeout(res, 2500); }).then(function () {
            return pollExtractJob(statusUrl, attempt + 1);
          });
        });
    }

    function extractBeforeSubmit(form, fileInput, submitter) {
      const extractUrl = form.getAttribute("data-extract-url");
      const fd = new FormData();
      fd.append("source_file", fileInput.files[0]);
      fd.append("stash_math", "1");

      if (submitter) {
        if (!submitter.dataset.defaultLabel) submitter.dataset.defaultLabel = submitter.innerHTML;
        submitter.disabled = true;
        submitter.innerHTML = gettext('<i class="fas fa-circle-notch fa-spin"></i> Mətn çıxarılır...');
      }

      return fetch(extractUrl, {
        method: "POST",
        body: fd,
        headers: { "X-CSRFToken": getCsrfTokenTQ(), "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin"
      })
        .then(function (r) {
          if (r.status === 404) return null; // endpoint yoxdur → köhnə yol
          return r.text().then(function (body) {
            let json = {};
            try { json = body ? JSON.parse(body) : {}; } catch (e) { json = {}; }
            if (!r.ok || !json.ok) throw new Error(json.error || gettext("Fayldan mətn çıxarıla bilmədi."));
            return json;
          });
        })
        .then(function (json) {
          if (json === null) return null;
          if (json.status === "success") return json;
          return pollExtractJob(extractUrl + json.job_id + "/", 0);
        })
        .then(function (done) {
          if (done === null) return false; // fallback: faylla köhnə submit
          const textarea = form.querySelector('textarea[name="raw_text"]');
          if (textarea) {
            textarea.value = done.text || "";
            textarea.dispatchEvent(new Event("input", { bubbles: true }));
          }
          const meta = done.meta || {};
          if (meta.math_token) {
            let tokenInput = form.querySelector('input[name="math_token"]');
            if (!tokenInput) {
              tokenInput = document.createElement("input");
              tokenInput.type = "hidden";
              tokenInput.name = "math_token";
              form.appendChild(tokenInput);
            }
            tokenInput.value = meta.math_token;
          }
          fileInput.value = "";
          return true;
        });
    }

    function guardLongSubmit(form) {
      if (!form) return;
      form.addEventListener("submit", function (event) {
        if (form.dataset.isSubmitting === "true") {
          event.preventDefault();
          return;
        }

        const fileInput = form.querySelector('input[type="file"]');
        if (fileInput && !validateFileClientSide(fileInput)) {
          event.preventDefault();
          return;
        }

        // P3-b: fayl varsa əvvəl asinxron çıxarma, sonra normal POST (faylsız).
        if (
          form.getAttribute("data-extract-url") &&
          fileInput &&
          fileInput.files.length &&
          form.dataset.extractDone !== "true"
        ) {
          event.preventDefault();
          const submitter = event.submitter || form.querySelector('button[type="submit"]');
          extractBeforeSubmit(form, fileInput, submitter)
            .then(function (extracted) {
              form.dataset.extractDone = "true";
              if (submitter && submitter.dataset.defaultLabel) {
                submitter.innerHTML = submitter.dataset.defaultLabel;
                submitter.disabled = false;
              }
              if (extracted === false && submitter) {
                // endpoint yoxdur → köhnə davranış: faylla birbaşa göndər
              }
              form.requestSubmit(submitter || undefined);
            })
            .catch(function (error) {
              form.dataset.extractDone = "";
              form.dataset.isSubmitting = "";
              if (submitter && submitter.dataset.defaultLabel) {
                submitter.innerHTML = submitter.dataset.defaultLabel;
                submitter.disabled = false;
              }
              (window.showWorkbenchError || window.alert)(
                error.message || gettext("Fayldan mətn çıxarıla bilmədi.")
              );
            });
          return;
        }

        form.dataset.isSubmitting = "true";
        const submitter = event.submitter || form.querySelector('button[type="submit"]');
        if (submitter) {
          if (!submitter.dataset.defaultLabel) {
            submitter.dataset.defaultLabel = submitter.innerHTML;
          }
          submitter.disabled = true;
          submitter.innerHTML = gettext('<i class="fas fa-circle-notch fa-spin"></i> Yüklənir...');
        }
        form.querySelectorAll('button[type="submit"]').forEach(function (button) {
          if (button !== submitter) button.disabled = true;
        });
      });
    }

    guardLongSubmit(document.querySelector(".split-layout"));
    guardLongSubmit(document.getElementById("saveForm"));

    // ====== Scroll-to-top FAB ======
    (function setupScrollTopFab() {
      const fab = document.createElement("button");
      fab.type = "button";
      fab.className = "scroll-top-fab";
      fab.setAttribute("aria-label", gettext("Yuxarı qayıt"));
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
