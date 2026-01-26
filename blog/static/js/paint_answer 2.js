// static/js/paint_answer.js
(function () {
    function clamp(n, min, max) { return Math.max(min, Math.min(max, n)); }
  
    function initPaintCard(card) {
      const qid = card.dataset.qid;
  
      const body = card.querySelector(".paint-body");
      const enabledHidden = card.querySelector(".paint-enabled-hidden");
      const enabledCheckbox = card.querySelector(".paint-enabled-checkbox");
  
      const canvas = card.querySelector(".paint-canvas");
      const ctx = canvas.getContext("2d");
  
      const btnPen = card.querySelector(".paint-pen");
      const btnEraser = card.querySelector(".paint-eraser");
      const btnClear = card.querySelector(".paint-clear");
      const btnSave = card.querySelector(".paint-save");
  
      const colorInput = card.querySelector(".paint-color");
      const widthInput = card.querySelector(".paint-width");
      const widthVal = card.querySelector(".paint-width-val");
  
      const clearHidden = card.querySelector(".paint-clear-hidden");
      const dataHidden = card.querySelector(".paint-data-hidden");
  
      const existingUrl = card.dataset.existingUrl || "";
  
      let isEraser = false;
      let drawing = false;
      let lastX = 0, lastY = 0;
  
      // autosave debounce
      let saveTimer = null;
      function scheduleSave(ms = 500) {
        if (saveTimer) clearTimeout(saveTimer);
        saveTimer = setTimeout(() => {
          exportToHidden();
        }, ms);
      }
  
      function setTool(mode) {
        isEraser = (mode === "eraser");
        btnPen.classList.toggle("active", !isEraser);
        btnEraser.classList.toggle("active", isEraser);
      }
  
      function resizeCanvasKeepDrawing() {
        // mövcud şəkli saxla
        const prev = canvas.width && canvas.height ? canvas.toDataURL("image/png") : null;
  
        const rect = canvas.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
  
        canvas.width = Math.floor(rect.width * dpr);
        canvas.height = Math.floor(rect.height * dpr);
  
        // koordinatları CSS px ilə idarə etmək üçün transform:
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
  
        // əvvəlki şəkli geri draw et
        if (prev) {
          const img = new Image();
          img.onload = () => {
            ctx.globalCompositeOperation = "source-over";
            ctx.drawImage(img, 0, 0, rect.width, rect.height);
          };
          img.src = prev;
        }
      }
  
      function getPointFromEvent(e) {
        const rect = canvas.getBoundingClientRect();
        const clientX = e.clientX;
        const clientY = e.clientY;
        return {
          x: clientX - rect.left,
          y: clientY - rect.top
        };
      }
  
      function startDraw(e) {
        drawing = true;
        const p = getPointFromEvent(e);
        lastX = p.x;
        lastY = p.y;
        canvas.setPointerCapture(e.pointerId);
      }
  
      function endDraw() {
        if (!drawing) return;
        drawing = false;
        ctx.beginPath();
        scheduleSave(350); // user əlini qaldıranda auto-save
      }
  
      function draw(e) {
        if (!drawing) return;
  
        e.preventDefault();
  
        const p = getPointFromEvent(e);
  
        const width = clamp(Number(widthInput.value || 4), 1, 30);
        ctx.lineWidth = width;
  
        if (isEraser) {
          ctx.globalCompositeOperation = "destination-out";
          ctx.strokeStyle = "rgba(0,0,0,1)";
        } else {
          ctx.globalCompositeOperation = "source-over";
          ctx.strokeStyle = colorInput.value || "#111111";
        }
  
        ctx.beginPath();
        ctx.moveTo(lastX, lastY);
        ctx.lineTo(p.x, p.y);
        ctx.stroke();
  
        lastX = p.x;
        lastY = p.y;
      }
  
      function clearAll() {
        const rect = canvas.getBoundingClientRect();
        ctx.globalCompositeOperation = "source-over";
        ctx.clearRect(0, 0, rect.width, rect.height);
  
        clearHidden.value = "1";
        dataHidden.value = "";
  
        // progress update (əgər var)
        if (typeof window.updateProgress === "function") window.updateProgress();
      }
  
      function exportToHidden() {
        const dataUrl = canvas.toDataURL("image/png");
        dataHidden.value = dataUrl;
        clearHidden.value = "0";
  
        if (typeof window.updateProgress === "function") window.updateProgress();
      }
  
      function loadExistingToCanvas(url) {
        if (!url) return;
        const rect = canvas.getBoundingClientRect();
        const img = new Image();
        img.crossOrigin = "anonymous";
        img.onload = () => {
          ctx.globalCompositeOperation = "source-over";
          ctx.drawImage(img, 0, 0, rect.width, rect.height);
          // hidden-ə də yaz (autosave üçün)
          exportToHidden();
        };
        img.src = url;
      }
  
      // Toggle open/close
      enabledCheckbox.addEventListener("change", () => {
        const isOn = enabledCheckbox.checked;
        enabledHidden.value = isOn ? "1" : "0";
        body.style.display = isOn ? "block" : "none";
  
        if (isOn) {
          resizeCanvasKeepDrawing();
          // əvvəlki image varsa yüklə (canvas boşdursa)
          if (existingUrl && (!dataHidden.value || dataHidden.value.length < 50)) {
            loadExistingToCanvas(existingUrl);
          } else {
            scheduleSave(200);
          }
        }
        if (typeof window.updateProgress === "function") window.updateProgress();
      });
  
      // toolbar
      btnPen.addEventListener("click", () => setTool("pen"));
      btnEraser.addEventListener("click", () => setTool("eraser"));
  
      widthInput.addEventListener("input", () => {
        widthVal.textContent = String(widthInput.value || "4");
      });
  
      btnClear.addEventListener("click", clearAll);
      btnSave.addEventListener("click", exportToHidden);
  
      // pointer events (touch + mouse + stylus)
      canvas.addEventListener("pointerdown", startDraw);
      canvas.addEventListener("pointermove", draw);
      canvas.addEventListener("pointerup", endDraw);
      canvas.addEventListener("pointercancel", endDraw);
      canvas.addEventListener("pointerleave", endDraw);
  
      // init default tool + canvas size
      setTool("pen");
      widthVal.textContent = String(widthInput.value || "4");
  
      // Əgər ilkin olaraq açıqdırsa (ans.has_paint), canvas ölçüsünü qur
      if (enabledCheckbox.checked) {
        // slight delay: DOM ölçüləri tam otursun
        setTimeout(() => {
          resizeCanvasKeepDrawing();
          if (existingUrl) loadExistingToCanvas(existingUrl);
        }, 0);
      }
  
      // window resize – çəkilən şəkli qoruyaraq resize
      window.addEventListener("resize", () => {
        if (body.style.display !== "none") {
          resizeCanvasKeepDrawing();
        }
      });
    }


//     const paintEnabled = slide.querySelector('.paint-enabled-hidden');
// const paintData = slide.querySelector('.paint-data-hidden');
// let hasPaint = false;
// if (paintEnabled && paintEnabled.value === "1" && paintData && paintData.value && paintData.value.length > 50) {
//   hasPaint = true;
// }
// if (inputs.length > 0 || hasText || hasPaint) {
//   answeredCount++;
// }

  
    document.addEventListener("DOMContentLoaded", () => {
      document.querySelectorAll(".paint-card").forEach(initPaintCard);
    });
  })();
  