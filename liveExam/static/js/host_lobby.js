/* host_lobby.js  (UPDATED) */

/** Emojilər */
const AVATARS = {
    'avatar_1': '🦊',   // Fox
    'avatar_2': '🐼',   // Panda
    'avatar_3': '🦁',   // Lion
    'avatar_4': '🐯',   // Tiger
    'avatar_5': '🐨',   // Koala
    'avatar_6': '🐷',   // Pig
    'avatar_7': '🐸',   // Frog
    'avatar_8': '🐙',   // Octopus
    'avatar_9': '🐵',   // Monkey
    'avatar_10': '🦄',  // Unicorn
    'avatar_11': '🐰',  // Rabbit
    'avatar_12': '🐹'   // Hamster
};
  
  /** DOM */
  const els = {
    startBtn: document.getElementById("startBtn"),
    revealBtn: document.getElementById("revealBtn"),
    nextBtn: document.getElementById("nextBtn"),
    finishBtn: document.getElementById("finishBtn"),
    qCountInput: document.getElementById("questionCount"),
    autoMode: document.getElementById("autoMode"),
    gameState: document.getElementById("gameState"),
  
    lobbyHeader: document.getElementById("lobbyHeader"),
  
    questionWrap: document.getElementById("questionWrap"),
    leaderWrap: document.getElementById("leaderWrap"),
    playersCount: document.getElementById("playersCount"),
    playersList: document.getElementById("playersList"),
    hostLog: document.getElementById("hostLog"),
  
    qMeta: document.getElementById("qMeta"),
    qText: document.getElementById("qText"),
    qTimer: document.getElementById("qTimer"),
    qOptions: document.getElementById("qOptions"),
  
    leaderList: document.getElementById("leaderList"),
  
    // ✅ yeni: debug toggle düyməsi (HTML-də əlavə et)
    debugBtn: document.getElementById("debugBtn"),
  };
  
  let state = "lobby";
  let qTimerInterval = null;
  let autoRevealTimer = null;
  let autoNextTimer = null;
  

/* =========================
   DEBUG LOG SYSTEM 
   - yeni log yuxarıda
   - 1-ci klik aç, 2-ci klik bağla
   - alt-alta səliqəli
   ========================= */

   let debugEnabled = false;
   const LOG_MAX_LINES = 250;
   const logBuffer = []; // ✅ yeni yuxarıda saxlanacaq
   
   function setDebugUI(open) {
     debugEnabled = !!open;
   
     if (els.debugBtn) {
       els.debugBtn.textContent = debugEnabled ? "Debug Logs ▾" : "Debug Logs ▸";
       els.debugBtn.style.opacity = debugEnabled ? "1" : "0.75";
     }
     if (els.hostLog) {
       els.hostLog.style.display = debugEnabled ? "block" : "none";
     }
   }
   
   function toggleDebug() {
     setDebugUI(!debugEnabled);
     log(`Debug ${debugEnabled ? "açıldı" : "bağlandı"}`, "info", { force: true });
   }
   
   // level="debug" yalnız debugEnabled=true olanda UI-a yaz
   function log(msg, level = "debug", opts = {}) {
     const force = !!opts.force;
   
     // Console-a həmişə
     if (level === "error") console.error("[HOST]", msg);
     else console.log("[HOST]", msg);
   
     // UI log-a yalnız debug açıq olanda (və ya force)
     if (!els.hostLog) return;
     if (!debugEnabled && !force) return;
   
     const line = `> ${new Date().toLocaleTimeString()} [${level.toUpperCase()}] ${msg}`;
   
     // ✅ yeni log yuxarıda görünsün
     logBuffer.unshift(line);
   
     // limit
     if (logBuffer.length > LOG_MAX_LINES) logBuffer.length = LOG_MAX_LINES;
   
     // yazdır
     els.hostLog.textContent = logBuffer.join("\n");
   
     // ✅ yeni yuxarıda olduğu üçün scroll-u yuxarı saxla
     els.hostLog.scrollTop = 0;
   }
   
   // default bağlı
   setDebugUI(false);
   
   // 1-ci klik aç, 2-ci klik bağla
   if (els.debugBtn) {
     els.debugBtn.addEventListener("click", toggleDebug);
   } else if (els.hostLog) {
     // düymə yoxdursa, log panelinə kliklə toggle
     els.hostLog.addEventListener("click", toggleDebug);
   }
   
  
  /* =========================
     HELPERS
     ========================= */
  function getWsUrl(path) {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${location.host}${path}`;
  }
  
  async function sendAction(url, bodyData = null) {
    try {
      const headers = {
        "X-CSRFToken": GAME_CONFIG.csrf,
        "X-Requested-With": "XMLHttpRequest"
      };
  
      const options = { method: "POST", headers };
      if (bodyData) options.body = bodyData;
  
      log(`POST -> ${url}`, "debug");
      const res = await fetch(url, options);
  
      const json = await res.json().catch(() => ({}));
      if (!res.ok || json.ok === false) {
        const msg = json.message || "Server Request Failed";
        log(`Action error: ${msg}`, "error", { force: true });
        return json;
      }
  
      log(`Action OK: ${url}`, "debug");
      return json;
    } catch (e) {
      log("Fetch error: " + e.message, "error", { force: true });
      return { ok: false, message: e.message };
    }
  }
  
  /* =========================
     UI STATE
     ========================= */
  function updateUIState(newState) {
    state = newState;
    if (els.gameState) els.gameState.textContent = state.toUpperCase();
  
    // Buttons
    if (els.startBtn) els.startBtn.disabled = (state !== "lobby");
    if (els.revealBtn) els.revealBtn.disabled = (state !== "question");
    if (els.nextBtn) els.nextBtn.disabled = (state !== "reveal");
    if (els.finishBtn) els.finishBtn.disabled = false;
  
    // Panels
    if (els.questionWrap) els.questionWrap.style.display = (state === "question") ? "block" : "none";
    if (els.leaderWrap) els.leaderWrap.style.display = (state === "reveal" || state === "finished") ? "block" : "none";
  
    // Header hide (oyun başlayanda gizlət)
    if (els.lobbyHeader) {
      els.lobbyHeader.style.display = (state !== "lobby") ? "none" : "block";
    }
  
    if (state !== "question") {
      clearInterval(qTimerInterval);
      qTimerInterval = null;
      if (els.qTimer) els.qTimer.textContent = "--";
    }
  
    log(`STATE -> ${state}`, "debug");
  }
  
  /* =========================
     WEBSOCKETS
     ========================= */
  
  // Lobby WS
  const lobbyWs = new WebSocket(getWsUrl(`/ws/live/${GAME_CONFIG.pin}/lobby/`));
  
  lobbyWs.onopen = () => log("Lobby WS connected", "debug");
  lobbyWs.onclose = () => log("Lobby WS closed", "debug");
  lobbyWs.onerror = () => log("Lobby WS error", "error", { force: true });
  
  lobbyWs.onmessage = (e) => {
    const data = JSON.parse(e.data);
    log(`Lobby msg: ${data.type}`, "debug");
  
    if (data.type === "lobby_state") {
        if (els.playersCount) els.playersCount.textContent = data.count || 0;
      
        if (els.playersList) {
          els.playersList.innerHTML = "";
          (data.players || []).forEach(p => {
            const div = document.createElement("div");
            div.className = "player-chip";
      
            const emoji = AVATARS[p.avatar_key] || "👤";
      
            div.innerHTML = `
              <span class="player-avatar">${emoji}</span>
              <div class="player-name">${p.nickname}</div>
            `;
            els.playersList.appendChild(div);
          });
        }
      }
      
  
    // istəsən: game_started redirect kimi mesajları da burada log edə bilərsən
  };
  
  
  // Play WS
  const playWs = new WebSocket(getWsUrl(`/ws/live/${GAME_CONFIG.pin}/play/`));
  
  playWs.onopen = () => log("Play WS connected", "debug");
  playWs.onclose = () => log("Play WS closed", "debug");
  playWs.onerror = () => log("Play WS error", "error", { force: true });
  
  playWs.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    log(`Play msg: ${msg.type}`, "debug");
  
    if (msg.type === "question_published") {
      updateUIState("question");
      renderQuestion(msg.question);
      log(`Sual yayımlandı: ${msg.question.index}/${msg.question.total}`, "info", { force: true });
  
      // Auto Reveal (vaxt bitəndə)
      if (els.autoMode?.checked && msg.question.ends_at) {
        const ends = new Date(msg.question.ends_at).getTime();
        const ms = Math.max(0, ends - Date.now());
  
        if (autoRevealTimer) clearTimeout(autoRevealTimer);
        autoRevealTimer = setTimeout(() => {
          if (state === "question") els.revealBtn?.click();
        }, ms + 500);
      }
    }
  
    else if (msg.type === "reveal") {
      updateUIState("reveal");
      renderLeaderboard(msg.top || []);
      log("Nəticələr göstərildi", "info", { force: true });
  
      // Auto Next (5 saniyə sonra)
      if (els.autoMode?.checked) {
        if (autoNextTimer) clearTimeout(autoNextTimer);
        autoNextTimer = setTimeout(() => {
          if (state === "reveal") els.nextBtn?.click();
        }, 5000);
      }
    }
  
    else if (msg.type === "finished") {
      updateUIState("finished");
      renderLeaderboard(msg.top || []);
      log("Oyun bitdi", "info", { force: true });
    }
  
    // əlavə debug event: answer_progress (istəsən burada izləyərsən)
    else if (msg.type === "answer_progress") {
      log(`Progress: ${msg.answered_count}/${msg.total_players}`, "debug");
    }
  };
  
  /* =========================
     RENDER
     ========================= */
  function renderQuestion(q) {
    if (!els.qMeta || !els.qText || !els.qOptions) return;
  
    els.qMeta.textContent = `Sual ${q.index} / ${q.total}`;
    els.qText.textContent = q.text;
    els.qOptions.innerHTML = "";
  
    (q.options || []).forEach((opt, idx) => {
      const div = document.createElement("div");
      div.className = `opt-card opt-bg-${idx % 4}`;
  
      // UI üçün A,B,C,D sadəcə labeldır (backend artıq qarışdırır)
      const letter = String.fromCharCode(65 + idx);
      div.innerHTML = `
        <span style="background:rgba(0,0,0,0.2); width:30px; height:30px; display:flex; align-items:center; justify-content:center; border-radius:50%; margin-right:10px;">
          ${letter}
        </span>
        ${opt.text}
      `;
      els.qOptions.appendChild(div);
    });
  
    // Timer
    if (els.qTimer) {
      if (q.ends_at) {
        const ends = new Date(q.ends_at).getTime();
  
        clearInterval(qTimerInterval);
        qTimerInterval = setInterval(() => {
          const diff = Math.max(0, Math.ceil((ends - Date.now()) / 1000));
          els.qTimer.textContent = diff;
          if (diff <= 0) {
            clearInterval(qTimerInterval);
            qTimerInterval = null;
          }
        }, 250);
      } else {
        els.qTimer.textContent = "∞";
      }
    }
  }
  
  function renderLeaderboard(topPlayers) {
    if (!els.leaderList) return;
  
    els.leaderList.innerHTML = "";
    topPlayers.forEach((p, i) => {
      const div = document.createElement("div");
      div.className = "leader-row";
      div.innerHTML = `
        <div style="display:flex; align-items:center;">
          <span class="badge-rank">${i + 1}</span>
          <span>${p.nickname}</span>
        </div>
        <span style="color:var(--primary); font-weight:900;">${p.score} xal</span>
      `;
      els.leaderList.appendChild(div);
    });
  }
  
  /* =========================
     BUTTON ACTIONS
     ========================= */
  els.startBtn && (els.startBtn.onclick = () => {
    const fd = new FormData();
    if (els.qCountInput?.value) fd.append("question_count", els.qCountInput.value);
    sendAction(GAME_CONFIG.urls.start, fd);
  });
  
  els.revealBtn && (els.revealBtn.onclick = () => sendAction(GAME_CONFIG.urls.endQuestion));
  els.nextBtn && (els.nextBtn.onclick = () => sendAction(GAME_CONFIG.urls.nextQuestion));
  els.finishBtn && (els.finishBtn.onclick = () => sendAction(GAME_CONFIG.urls.finish));
  
  /* Init */
  updateUIState("lobby");
  log("Host lobby script loaded", "debug");
  