// exam_paint.js - Stable paint handler with SignaturePad (pen/eraser/clear/undo + resize-safe)

document.addEventListener("DOMContentLoaded", () => {
    const paintCards = document.querySelectorAll(".paint-card");
    paintCards.forEach(initPaintCard);
  
    // Optional: re-resize all on window resize (each card already attaches its own)
  });
  
  function initPaintCard(card) {
    const qid = card.dataset.qid;
  
    const canvas = card.querySelector(".paint-canvas");
    const colorInput = card.querySelector(".paint-color");
    const widthInput = card.querySelector(".paint-width");
    const drawBtn = card.querySelector(".paint-draw");
    const eraseBtn = card.querySelector(".paint-erase");
    const clearBtn = card.querySelector(".paint-clear");
    const hiddenInput = card.querySelector(".paint-data");
  
    if (!canvas) return;
  
    // ---------- State ----------
    let signaturePad = null;
    let mode = "draw"; // "draw" | "erase"
    let undoStack = []; // toData snapshots
  
    // ---------- Helpers ----------
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
  
    function setMode(nextMode) {
      mode = nextMode;
  
      if (mode === "erase") {
        // Real eraser (removes pixels)
        ctx.globalCompositeOperation = "destination-out";
        // penColor doesn't matter much in destination-out, but keep it defined
        signaturePad.penColor = "rgba(0,0,0,1)";
  
        eraseBtn?.classList.add("active");
        drawBtn?.classList.remove("active");
      } else {
        // Normal drawing
        ctx.globalCompositeOperation = "source-over";
        signaturePad.penColor = colorInput?.value || "#000000";
  
        drawBtn?.classList.add("active");
        eraseBtn?.classList.remove("active");
      }
    }
  
    function setWidthFromInput() {
      const w = Math.max(1, parseFloat(widthInput?.value || "3"));
      signaturePad.minWidth = w * 0.5;
      signaturePad.maxWidth = w * 1.5;
    }
  
    function syncHidden() {
      if (!hiddenInput) return;
      hiddenInput.value = signaturePad.isEmpty()
        ? ""
        : signaturePad.toDataURL("image/png");
    }
  
    function pushUndoSnapshot() {
      // save strokes for undo
      try {
        const data = signaturePad.toData();
        undoStack.push(data);
        // limit memory
        if (undoStack.length > 50) undoStack.shift();
      } catch (e) {
        // ignore
      }
    }
  
    function undo() {
      if (!undoStack.length) {
        signaturePad.clear();
        syncHidden();
        return;
      }
      // remove last snapshot (current state)
      undoStack.pop();
      const prev = undoStack.length ? undoStack[undoStack.length - 1] : [];
      signaturePad.clear();
      if (prev && prev.length) signaturePad.fromData(prev);
      syncHidden();
    }
  
    function resizeCanvasKeepData() {
      const ratio = Math.max(window.devicePixelRatio || 1, 1);
      const rect = canvas.parentElement.getBoundingClientRect();
  
      // store strokes before resize
      const data = signaturePad ? signaturePad.toData() : null;
  
      // set size
      canvas.width = Math.max(1, Math.floor(rect.width * ratio));
      canvas.height = Math.max(1, Math.floor(rect.height * ratio));
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
  
      // reset transforms then scale
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.scale(ratio, ratio);
  
      // restore
      if (signaturePad) {
        signaturePad.clear();
        if (data && data.length) signaturePad.fromData(data);
        // keep current mode after resize
        setMode(mode);
        syncHidden();
      }
    }
  
    // ---------- Init SignaturePad ----------
    signaturePad = new SignaturePad(canvas, {
      backgroundColor: "rgb(255,255,255)",
      penColor: colorInput?.value || "#000000",
      minWidth: 1.5,
      maxWidth: 3.5,
    });
  
    // IMPORTANT: set size AFTER signaturePad created (or at least after ctx exists)
    resizeCanvasKeepData();
    window.addEventListener("resize", () => resizeCanvasKeepData());
  
    // Apply width + mode
    setWidthFromInput();
    setMode("draw");
    pushUndoSnapshot();
  
    // SignaturePad callbacks
    signaturePad.onBegin = () => {
      // snapshot before change so undo works nicely
      pushUndoSnapshot();
    };
  
    signaturePad.onEnd = () => {
      // stroke finished
      syncHidden();
    };
  
    // ---------- UI Events ----------
    colorInput?.addEventListener("change", () => {
      if (mode === "draw") {
        signaturePad.penColor = colorInput.value;
      }
    });
  
    widthInput?.addEventListener("input", () => {
      setWidthFromInput();
    });
  
    drawBtn?.addEventListener("click", (e) => {
      e.preventDefault();
      setMode("draw");
    });
  
    eraseBtn?.addEventListener("click", (e) => {
      e.preventDefault();
      setMode("erase");
    });
  
    clearBtn?.addEventListener("click", (e) => {
      e.preventDefault();
      if (confirm("Paint-i təmizləmək istədiyinizdən əminsiniz?")) {
        signaturePad.clear();
        // clear undo too (optional)
        undoStack = [];
        pushUndoSnapshot();
        setMode(mode);
        syncHidden();
      }
    });
  
    // Ctrl+Z undo (card focused or document)
    document.addEventListener("keydown", (e) => {
      const isMac = navigator.platform.toUpperCase().includes("MAC");
      const zKey = e.key.toLowerCase() === "z";
      const cmdOrCtrl = isMac ? e.metaKey : e.ctrlKey;
      if (cmdOrCtrl && zKey) {
        // only if this canvas is in viewport / user interacted (simple heuristic)
        // you can tighten this if needed
        e.preventDefault();
        undo();
      }
    });
  
    // If you want to load existing base64 from hidden input on page load:
    if (hiddenInput?.value && hiddenInput.value.startsWith("data:image")) {
      try {
        signaturePad.fromDataURL(hiddenInput.value);
        syncHidden();
        pushUndoSnapshot();
      } catch (e) {
        // ignore
      }
    }
  }
  
  /**
   * ✅ Form submit-dən əvvəl paint-ləri fayl kimi FormData-ya əlavə et.
   * IMPORTANT: Bu async-dir → submit handler-də `await appendPaintFilesToFormData(formData);`
   */
  window.appendPaintFilesToFormData = async function appendPaintFilesToFormData(formData) {
    const paintCards = document.querySelectorAll(".paint-card");
    const tasks = [];
  
    paintCards.forEach((card) => {
      const qid = card.dataset.qid;
      const canvas = card.querySelector(".paint-canvas");
      const hiddenInput = card.querySelector(".paint-data");
  
      if (!canvas) return;
  
      // boşdursa skip (hiddenInput sync olmasa belə, canvas-a baxacağıq)
      tasks.push(
        new Promise((resolve) => {
          canvas.toBlob(
            (blob) => {
              if (blob) {
                // Əgər boş şəkildirsə (tələbə heç nə çəkməyibsə) bunu aşkar etmək çətindir.
                // Amma hiddenInput boşdursa, böyük ehtimalla boşdur:
                if (hiddenInput && !hiddenInput.value) {
                  resolve();
                  return;
                }
  
                const fileName = `paint_q${qid}_${Date.now()}.png`;
                // BACKEND ilə uyğunlaşdır: məsələn paint_image_<qid> və ya paint_<qid>
                formData.append(`paint_${qid}`, blob, fileName);
              }
              resolve();
            },
            "image/png",
            1.0
          );
        })
      );
    });
  
    await Promise.all(tasks);
  };
  