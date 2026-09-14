/**
 * Toplu sual iş masası — pano (Ctrl+V) və sürükləmə ilə şəkil yapışdırma.
 * W8 2026-09-14 (w3import yarımçıq 7, NIGHT_WAVES §5 maddə 11).
 *
 * Yalnız `.bulk-page-wrapper[data-paste-url]` olanda aktivdir (bank toplu əlavə).
 * Şəkil eyni səhifənin `action=paste_image` JSON qoluna gedir (server DOCX-formatlı
 * stash-a yazır, `[[img:N]]` marker nömrəsini qaytarır); marker redaktorda caret-in
 * yerinə yazılır, gizli `math_token` sahəsi yenilənir, çip (thumbnail + sil) göstərilir.
 *
 * Qaydalar:
 *  - Panoda MƏTN varsa (Word-dən mətn + şəkil kopyalanıb) brauzerin adi yapışdırması
 *    işləyir — şəkil götürülmür (müəllim mətni istəyir).
 *  - Yükləmələr növbəyə salınır: server manifesti oxu-dəyiş-yaz edir, paralel
 *    sorğu eyni indeksi verə bilər.
 *  - `#dropZone`-a sürüşdürülən fayl (PDF/DOCX/TXT/PNG) adi fayl yükləməsidir
 *    (`fileInput.files` + mövcud `fileSelected`); redaktora sürüşdürülən ŞƏKİL isə
 *    yapışdırma kimi stash-a düşür.
 *  - CSP: inline yoxdur; AJAX-safe: `EMSReady`, idempotent.
 */
window.EMSReady(function () {
  "use strict";

  var wrapper = document.querySelector(".bulk-page-wrapper[data-paste-url]");
  if (!wrapper || wrapper.dataset.pasteReady === "1") return;
  var editor = wrapper.querySelector("#testRawEditor");
  var strip = wrapper.querySelector("#wbPasteStrip");
  var chips = wrapper.querySelector("#wbPasteChips");
  var status = wrapper.querySelector("#wbPasteStatus");
  if (!editor || !strip || !chips) return;
  wrapper.dataset.pasteReady = "1";

  var pasteUrl = wrapper.dataset.pasteUrl;
  var form = editor.closest("form");
  var msg = strip.dataset;
  var queue = Promise.resolve();

  function toast(text, level) {
    if (window.EMSToast && typeof window.EMSToast.show === "function") {
      window.EMSToast.show(text, level || "error");
    } else if (typeof window.showWorkbenchError === "function") {
      window.showWorkbenchError(text);
    }
  }

  function setStatus(text) {
    if (!status) return;
    status.textContent = text || "";
    status.hidden = !text;
  }

  function tokenInput() {
    var input = form ? form.querySelector('input[name="math_token"]') : null;
    if (!input && form) {
      input = document.createElement("input");
      input.type = "hidden";
      input.name = "math_token";
      form.appendChild(input);
    }
    return input;
  }

  function currentToken() {
    var input = tokenInput();
    return input ? input.value || "" : "";
  }

  function setToken(value) {
    var input = tokenInput();
    if (input) input.value = value || "";
    // Save formundakı gizli token da (preview render olunubsa) sinxron qalsın.
    document.querySelectorAll('#saveForm input[name="math_token"]').forEach(function (el) {
      el.value = value || "";
    });
  }

  function markerRegex(marker) {
    return new RegExp("[ \\t]*" + marker.replace(/[[\]]/g, "\\$&") + "[ \\t]*", "g");
  }

  function insertAtCaret(marker, position) {
    var start = position ? position.start : editor.selectionStart;
    var end = position ? position.end : editor.selectionEnd;
    if (typeof start !== "number") { start = end = editor.value.length; }
    var before = editor.value.slice(0, start);
    var needsSpace = before.length && !/\s$/.test(before);
    var text = (needsSpace ? " " : "") + marker + " ";
    editor.focus();
    editor.setRangeText(text, start, end, "end");
    editor.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function removeMarker(marker) {
    var next = editor.value.replace(markerRegex(marker), " ");
    if (next !== editor.value) {
      editor.value = next;
      editor.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  function renderChip(item) {
    var chip = document.createElement("span");
    chip.className = "wb-paste-chip";
    chip.setAttribute("role", "listitem");
    chip.dataset.pasteIndex = String(item.index);
    chip.dataset.pasteMarker = item.marker;

    if (item.thumb) {
      var img = document.createElement("img");
      img.className = "wb-paste-chip__thumb";
      img.src = item.thumb;
      img.alt = "";
      chip.appendChild(img);
    } else {
      var icon = document.createElement("i");
      icon.className = "fas fa-image wb-paste-chip__icon";
      chip.appendChild(icon);
    }

    var label = document.createElement("code");
    label.className = "wb-paste-chip__marker";
    label.textContent = item.marker;
    label.title = item.marker;
    chip.appendChild(label);

    var remove = document.createElement("button");
    remove.type = "button";
    remove.className = "wb-paste-chip__remove";
    remove.setAttribute("aria-label", (msg.labelRemove || "") + " " + item.marker);
    remove.innerHTML = '<i class="fas fa-xmark"></i>';
    remove.addEventListener("click", function () { removeImage(chip); });
    chip.appendChild(remove);

    chips.appendChild(chip);
    strip.classList.add("has-chips");
    return chip;
  }

  function postForm(formData) {
    return window.EMSCore.fetchJSON(pasteUrl, { method: "POST", body: formData })
      .then(function (payload) {
        if (!payload || payload.ok !== true) {
          throw new Error((payload && payload.error) || msg.msgFailed || "");
        }
        return payload;
      })
      .catch(function (error) {
        var detail = error && error.payload && error.payload.error;
        throw new Error(detail || (error && error.message) || msg.msgFailed || "");
      });
  }

  function uploadImage(file, position) {
    var task = queue.then(function () {
      setStatus(msg.msgUploading || "");
      var fd = new FormData();
      fd.append("action", "paste_image");
      fd.append("math_token", currentToken());
      var ext = (file.type.split("/")[1] || "png").replace("jpeg", "jpg");
      fd.append("image", file, file.name && file.name.indexOf(".") > 0 ? file.name : "paste_" + Date.now() + "." + ext);
      return postForm(fd).then(function (payload) {
        setToken(payload.token);
        insertAtCaret(payload.marker, position);
        renderChip(payload);
      });
    });
    queue = task.catch(function () {});
    return task
      .then(function () { setStatus(""); })
      .catch(function (error) {
        setStatus("");
        toast(error.message || msg.msgFailed || "", "error");
      });
  }

  function removeImage(chip) {
    var marker = chip.dataset.pasteMarker;
    var index = chip.dataset.pasteIndex;
    var task = queue.then(function () {
      var fd = new FormData();
      fd.append("action", "paste_image_remove");
      fd.append("math_token", currentToken());
      fd.append("index", index);
      return postForm(fd).then(function (payload) {
        setToken(payload.token);
        removeMarker(marker);
        chip.remove();
        if (!chips.children.length) strip.classList.remove("has-chips");
        toast((msg.msgRemoved || "").replace("[[img:N]]", marker), "info");
      });
    });
    queue = task.catch(function () {});
    return task.catch(function (error) { toast(error.message || msg.msgFailed || "", "error"); });
  }

  function imageFiles(list) {
    var files = [];
    for (var i = 0; list && i < list.length; i++) {
      var f = list[i];
      if (f && /^image\//.test(f.type || "")) files.push(f);
    }
    return files;
  }

  function clipboardImages(data) {
    var files = [];
    if (!data || !data.items) return files;
    for (var i = 0; i < data.items.length; i++) {
      var item = data.items[i];
      if (item.kind === "file" && /^image\//.test(item.type || "")) {
        var f = item.getAsFile();
        if (f) files.push(f);
      }
    }
    return files;
  }

  function uploadAll(files, position) {
    files.forEach(function (file) { uploadImage(file, position); });
  }

  // ── Pano (Ctrl+V) ────────────────────────────────────────────────────────
  editor.addEventListener("paste", function (event) {
    var data = event.clipboardData;
    if (!data) return;
    var text = data.getData("text/plain");
    if (text && text.trim()) return; // mətn var → adi yapışdırma
    var files = clipboardImages(data);
    if (!files.length) return;
    event.preventDefault();
    uploadAll(files, { start: editor.selectionStart, end: editor.selectionEnd });
  });

  // ── Redaktora sürükləmə (yalnız şəkil) ───────────────────────────────────
  editor.addEventListener("dragover", function (event) {
    if (!event.dataTransfer) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    editor.classList.add("is-dragover");
  });
  editor.addEventListener("dragleave", function () { editor.classList.remove("is-dragover"); });
  editor.addEventListener("drop", function (event) {
    editor.classList.remove("is-dragover");
    if (!event.dataTransfer || !event.dataTransfer.files || !event.dataTransfer.files.length) return;
    event.preventDefault();
    var files = imageFiles(event.dataTransfer.files);
    if (!files.length) {
      toast(msg.msgNotImage || "", "warning");
      return;
    }
    // Caret-i buraxılan nöqtəyə yaxınlaşdırmaq brauzerdən asılıdır — cari caret işlədilir.
    uploadAll(files, { start: editor.selectionStart, end: editor.selectionEnd });
  });

  // ── Yükləmə zonasına sürükləmə → adi fayl yükləməsi ───────────────────────
  var dropZone = wrapper.querySelector("#dropZone");
  var fileInput = wrapper.querySelector("#fileInput");
  if (dropZone && fileInput) {
    dropZone.addEventListener("dragover", function (event) {
      event.preventDefault();
      dropZone.classList.add("is-dragover");
    });
    dropZone.addEventListener("dragleave", function () { dropZone.classList.remove("is-dragover"); });
    dropZone.addEventListener("drop", function (event) {
      dropZone.classList.remove("is-dragover");
      if (!event.dataTransfer || !event.dataTransfer.files || !event.dataTransfer.files.length) return;
      event.preventDefault();
      try {
        var dt = new DataTransfer();
        dt.items.add(event.dataTransfer.files[0]); // tək fayl (input `multiple` deyil)
        fileInput.files = dt.files;
      } catch (e) {
        return;
      }
      // `change` → csp_event_handlers.js `data-file-selected-callback` (fileSelected) +
      // testQuestionBank.js client-side validasiya — ayrıca çağırış lazım deyil.
      fileInput.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }

  // ── Preview POST-dan sonra çipləri bərpa et (manifest thumbnail-ləri) ─────
  var seed = document.getElementById("wb-paste-images");
  if (seed) {
    try {
      var items = JSON.parse(seed.textContent || "[]");
      if (Array.isArray(items)) items.forEach(renderChip);
    } catch (e) { /* boş */ }
  }
});
