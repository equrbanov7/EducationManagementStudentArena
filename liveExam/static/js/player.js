/* player.js - Logic preserved, UI enhanced */

const connPill = document.getElementById("connPill");
const timerBox = document.getElementById("timerBox");
const qText = document.getElementById("qText");
const optionsGrid = document.getElementById("optionsGrid");
const statusLine = document.getElementById("statusLine");
const metaLine = document.getElementById("metaLine");

const actionBar = document.getElementById("actionBar");
const submitBtn = document.getElementById("submitBtn");
const multiHint = document.getElementById("multiHint");

const lbWrap = document.getElementById("lbWrap");
const lbList = document.getElementById("lbList");
const resultList = document.getElementById("resultList");

let currentQuestion = null;   
let selectedOptionId = null;  
let selectedOptionIds = new Set(); 
let answered = false;
let timerInterval = null;

// WS URL Helper
function wsUrl(path){
    const proto = location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${location.host}${path}`;
}

function fmt2(n){ return String(n).padStart(2, "0"); }

function setConn(ok){
    connPill.textContent = ok ? "● Onlayn" : "○ Oflayn";
    connPill.style.color = ok ? "#00e676" : "#ff1744";
}

function clearTimer(){
    if (timerInterval) clearInterval(timerInterval);
    timerInterval = null;
    timerBox.textContent = "--:--";
}

function stopAnswerUI(){
    document.querySelectorAll(".opt").forEach(b => b.disabled = true);
    submitBtn.disabled = true;
}

function startTimer(endsAtISO){
    clearTimer();
    if (!endsAtISO) return;

    const ends = new Date(endsAtISO).getTime();

    function tick(){
        const now = Date.now();
        const diff = Math.max(0, ends - now);
        const sec = Math.ceil(diff / 1000);
        const mm = Math.floor(sec / 60);
        const ss = sec % 60;
        timerBox.textContent = `${fmt2(mm)}:${fmt2(ss)}`;

        // Son 10 saniyədə qırmızı olsun
        if (sec < 10) timerBox.style.color = "#d32f2f";
        else timerBox.style.color = "#006064";

        if (diff <= 0){
            stopAnswerUI();
            if (!answered) {
                statusLine.textContent = "⏰ Vaxt bitdi!";
                statusLine.className = "status bad";
            }
        }
    }

    tick();
    timerInterval = setInterval(tick, 250);
}

function isMulti(q){ return !!(q && q.multi); }

function maxSelect(q){
    const v = Number(q && q.max_select);
    return Number.isFinite(v) && v > 0 ? v : 1;
}

function updateMultiHint(){
    if (!isMulti(currentQuestion)) {
        multiHint.style.display = "none";
        return;
    }
    multiHint.style.display = "block";
    const maxS = maxSelect(currentQuestion);
    multiHint.textContent = `Seçilib: ${selectedOptionIds.size} / ${maxS}`;
}

function resetUIForQuestion(q){
    currentQuestion = q;
    answered = false;

    selectedOptionId = null;
    selectedOptionIds = new Set();

    lbWrap.style.display = "none";
    lbList.innerHTML = "";
    resultList.innerHTML = "";

    statusLine.textContent = "";
    statusLine.className = "status";

    metaLine.textContent = (q?.index && q?.total) ? `Sual ${q.index} / ${q.total}` : "";

    qText.textContent = q?.text || "Sual yüklənir...";
    optionsGrid.innerHTML = "";
    optionsGrid.style.display = "grid";

    // Action bar logic
    if (isMulti(q)) {
        actionBar.style.display = "flex";
        submitBtn.disabled = true;
        updateMultiHint();
    } else {
        actionBar.style.display = "none";
    }

    // Düymələrin yaradılması
    (q.options || []).forEach((opt, idx) => {
        const btn = document.createElement("button");
        btn.className = "opt"; // CSS-dəki rənglər avtomatik tətbiq olunacaq
        btn.type = "button";
        btn.dataset.id = opt.id;

        const letters = ["A","B","C","D","E","F"];
        const label = (opt.label ?? opt.key ?? opt.code ?? letters[idx] ?? String(idx+1));
        const text  = (opt.text ?? opt.title ?? opt.content ?? opt.answer ?? "").toString();

        btn.innerHTML = `<span style="margin-right:8px; opacity:0.7;">${label})</span> ${text}`;

        btn.onclick = () => {
            if (answered) return;

            // Single Choice
            if (!isMulti(q)) {
                selectedOptionId = opt.id;
                document.querySelectorAll(".opt").forEach(b => b.classList.remove("selected"));
                btn.classList.add("selected");
                
                // Animasiya və submit
                setTimeout(() => submitAnswerSingle(), 150); 
                return;
            }

            // Multi Choice
            const maxS = maxSelect(q);

            if (selectedOptionIds.has(opt.id)) {
                selectedOptionIds.delete(opt.id);
                btn.classList.remove("selected");
            } else {
                if (selectedOptionIds.size >= maxS) return;
                selectedOptionIds.add(opt.id);
                btn.classList.add("selected");
            }

            submitBtn.disabled = (selectedOptionIds.size === 0);
            updateMultiHint();
        };

        optionsGrid.appendChild(btn);
    });

    submitBtn.onclick = () => {
        if (!isMulti(currentQuestion) || answered) return;
        if (selectedOptionIds.size === 0) return;
        submitAnswerMulti();
    };

    startTimer(q.ends_at);
}

function calcAnswerMs(){
    const startedAt = currentQuestion?.started_at ? new Date(currentQuestion.started_at).getTime() : null;
    return startedAt ? Math.max(0, Date.now() - startedAt) : 0;
}

function submitAnswerSingle(){
    if (!currentQuestion || !selectedOptionId) return;
    answered = true;
    stopAnswerUI();
    statusLine.textContent = "🚀 Cavab göndərildi! Gözləyin...";
    statusLine.className = "status";
    statusLine.style.background = "#e3f2fd";
    statusLine.style.color = "#0d47a1";

    try {
        playWs.send(JSON.stringify({
            type: "answer",
            question_id: currentQuestion.id,
            option_id: selectedOptionId,
            answer_ms: calcAnswerMs()
        }));
    } catch(e) {}
}

function submitAnswerMulti(){
    if (!currentQuestion) return;
    answered = true;
    stopAnswerUI();
    statusLine.textContent = "🚀 Cavab göndərildi! Gözləyin...";
    statusLine.className = "status";
    statusLine.style.background = "#e3f2fd";
    statusLine.style.color = "#0d47a1";

    try {
        playWs.send(JSON.stringify({
            type: "answer",
            question_id: currentQuestion.id,
            option_ids: Array.from(selectedOptionIds),
            answer_ms: calcAnswerMs()
        }));
    } catch(e) {}
}

function renderReveal(msg){
    clearTimer();
    stopAnswerUI();

    const correctIds = (msg.correct_option_ids || []).map(Number);
    const correctSet = new Set(correctIds);

    let isCorrect = false;

    if (answered) {
        if (isMulti(currentQuestion)) {
            const sel = new Set(Array.from(selectedOptionIds).map(Number));
            isCorrect = (sel.size === correctSet.size) && Array.from(sel).every(x => correctSet.has(x));
        } else {
            isCorrect = correctSet.has(Number(selectedOptionId));
        }

        statusLine.textContent = isCorrect ? "🎉 Düzgün Cavab!" : "❌ Səhv Cavab";
        statusLine.className = "status " + (isCorrect ? "good" : "bad");
    } else {
        statusLine.textContent = "⚠️ Vaxt bitdi / cavab yoxdur";
        statusLine.className = "status bad";
    }

    lbWrap.style.display = "block";
    lbList.innerHTML = "";
    (msg.top || []).forEach((p, i) => {
        const li = document.createElement("li");
        li.innerHTML = `<b>#${i+1}</b> ${p.nickname} <span style='float:right'>${p.score}</span>`;
        lbList.appendChild(li);
    });

    resultList.innerHTML = "";
    (msg.results || []).slice(0, 20).forEach(r => {
        const li = document.createElement("li");
        li.textContent = `${r.nickname}: ${r.is_correct ? "✅" : "❌"} (+${r.awarded_points})`;
        resultList.appendChild(li);
    });

    metaLine.textContent = "Növbəti sual hazırlanır...";
}

function renderFinished(msg){
    clearTimer();
    stopAnswerUI();
    qText.textContent = "🏁 Oyun Bitdi!";
    optionsGrid.style.display = "none";
    actionBar.style.display = "none";
    statusLine.style.display = "none";

    lbWrap.style.display = "block";
    lbList.innerHTML = "";
    (msg.top || []).forEach((p, i) => {
        const li = document.createElement("li");
        li.style.fontSize = "1.2rem";
        li.innerHTML = `🏆 <b>${p.nickname}</b> <span style='float:right'>${p.score} xal</span>`;
        lbList.appendChild(li);
    });
    resultList.innerHTML = "";
}

// WebSocket Initialization
// DİQQƏT: pin dəyişəni HTML-dən CONFIG obyekti ilə gələcək
const playWs = new WebSocket(wsUrl(`/ws/live/${GAME_CONFIG.pin}/play/`));

playWs.onopen = async () => {
    setConn(true);
    // Fallback state fetch
    try {
        const res = await fetch(`/live/state/${GAME_CONFIG.pin}/`, { headers: { "Accept": "application/json" }});
        const st = await res.json();
        if (st.ok && st.question) {
            resetUIForQuestion(st.question);
            if (st.state === "reveal") {
                renderReveal({ correct_option_ids: st.correct_option_ids || [], top: [], results: [] });
            }
        }
    } catch(e){}
};

playWs.onclose = () => setConn(false);
playWs.onerror = () => setConn(false);

playWs.onmessage = (e) => {
    const msg = JSON.parse(e.data);

    if (msg.type === "question_published") {
        resetUIForQuestion(msg.question);
        return;
    }

    if (msg.type === "answer_saved") {
        statusLine.textContent = "✅ Cavab saxlanıldı. Gözləyin...";
        return;
    }

    if (msg.type === "reveal") {
        renderReveal(msg);
        return;
    }

    if (msg.type === "finished") {
        renderFinished(msg);
        return;
    }
};