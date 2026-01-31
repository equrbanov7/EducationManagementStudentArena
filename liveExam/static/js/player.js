/* ═══════════════════════════════════════════════════════════════
   PLAYER SCREEN - Complete Logic
   ═══════════════════════════════════════════════════════════════ */

   const AVATARS = {
    'avatar_1':'🦊','avatar_2':'🐼','avatar_3':'🦁','avatar_4':'🐯',
    'avatar_5':'🐨','avatar_6':'🐷','avatar_7':'🐸','avatar_8':'🐙',
    'avatar_9':'🐵','avatar_10':'🦄','avatar_11':'🐰','avatar_12':'🐹'
};

// DOM Elements
const $ = id => document.getElementById(id);

const UI = {
    connStatus: $('connStatus'),
    timerBox: $('timerBox'),
    timerText: $('timerText'),
    questionMeta: $('questionMeta'),
    questionText: $('questionText'),
    optionsContainer: $('optionsContainer'),
    multiActions: $('multiActions'),
    selectCounter: $('selectCounter'),
    submitBtn: $('submitBtn'),
    statusMessage: $('statusMessage'),
    leaderboardSection: $('leaderboardSection'),
    leaderboardList: $('leaderboardList'),
    resultsSection: $('resultsSection'),
    resultsList: $('resultsList'),
    finalScreen: $('finalScreen'),
    finalLeaderboard: $('finalLeaderboard'),
    confettiLayer: $('confettiLayer')
};

// State
let currentQuestion = null;
let selectedIds = new Set();
let answered = false;
let timerInterval = null;

// Helpers
const wsUrl = path => `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}${path}`;
const esc = t => { const d = document.createElement('div'); d.textContent = t || ''; return d.innerHTML; };
const pad = n => String(n).padStart(2, '0');

/* ═══════════════════════════════════════════════════════════════
   CONNECTION STATUS
   ═══════════════════════════════════════════════════════════════ */

function setConnection(online) {
    UI.connStatus.className = 'connection-status ' + (online ? 'online' : 'offline');
    UI.connStatus.querySelector('.text').textContent = online ? 'Onlayn' : 'Oflayn';
}

/* ═══════════════════════════════════════════════════════════════
   TIMER
   ═══════════════════════════════════════════════════════════════ */

function clearTimer() {
    if (timerInterval) clearInterval(timerInterval);
    timerInterval = null;
    UI.timerText.textContent = '--:--';
    UI.timerBox.className = 'timer-box';
}

function startTimer(endsAt) {
    clearTimer();
    if (!endsAt) return;
    
    const endTime = new Date(endsAt).getTime();
    
    function tick() {
        const now = Date.now();
        const diff = Math.max(0, endTime - now);
        const sec = Math.ceil(diff / 1000);
        const mm = Math.floor(sec / 60);
        const ss = sec % 60;
        
        UI.timerText.textContent = `${pad(mm)}:${pad(ss)}`;
        
        if (sec <= 5) {
            UI.timerBox.className = 'timer-box danger';
        } else if (sec <= 10) {
            UI.timerBox.className = 'timer-box warning';
        } else {
            UI.timerBox.className = 'timer-box';
        }
        
        if (diff <= 0) {
            clearInterval(timerInterval);
            disableOptions();
            if (!answered) {
                showStatus('timeout', '⏰ Vaxt bitdi!');
            }
        }
    }
    
    tick();
    timerInterval = setInterval(tick, 200);
}

/* ═══════════════════════════════════════════════════════════════
   STATUS MESSAGE
   ═══════════════════════════════════════════════════════════════ */

function showStatus(type, text) {
    UI.statusMessage.className = 'status-message ' + type;
    UI.statusMessage.textContent = text;
}

function hideStatus() {
    UI.statusMessage.className = 'status-message';
}

/* ═══════════════════════════════════════════════════════════════
   OPTIONS
   ═══════════════════════════════════════════════════════════════ */

function disableOptions() {
    document.querySelectorAll('.option-btn').forEach(btn => btn.disabled = true);
    UI.submitBtn.disabled = true;
}

function isMulti(q) {
    return !!(q && q.multi);
}

function maxSelect(q) {
    const v = Number(q?.max_select);
    return Number.isFinite(v) && v > 0 ? v : 1;
}

function updateCounter() {
    if (!isMulti(currentQuestion)) return;
    const max = maxSelect(currentQuestion);
    UI.selectCounter.textContent = `Seçilib: ${selectedIds.size} / ${max}`;
    UI.submitBtn.disabled = selectedIds.size === 0;
}

/* ═══════════════════════════════════════════════════════════════
   RENDER QUESTION
   ═══════════════════════════════════════════════════════════════ */

function renderQuestion(q) {
    currentQuestion = q;
    answered = false;
    selectedIds = new Set();
    
    // Hide sections
    UI.leaderboardSection.style.display = 'none';
    UI.finalScreen.style.display = 'none';
    hideStatus();
    
    // Meta
    UI.questionMeta.textContent = q.index && q.total ? `Sual ${q.index} / ${q.total}` : '';
    
    // Question text
    UI.questionText.innerHTML = `<div class="q-text-content">${esc(q.text || 'Sual yüklənir...')}</div>`;
    
    // Options
    UI.optionsContainer.innerHTML = '';
    const letters = ['A', 'B', 'C', 'D', 'E', 'F'];
    
    (q.options || []).forEach((opt, i) => {
        const btn = document.createElement('button');
        btn.className = `option-btn opt-${i % 6}`;
        btn.dataset.id = opt.id;
        
        const label = opt.label || letters[i] || String(i + 1);
        const text = opt.text || opt.title || '';
        
        btn.innerHTML = `
            <span class="option-letter">${label}</span>
            <span class="option-text">${esc(text)}</span>
        `;
        
        btn.onclick = () => handleOptionClick(btn, opt.id);
        UI.optionsContainer.appendChild(btn);
    });
    
    // Multi actions
    if (isMulti(q)) {
        UI.multiActions.style.display = 'flex';
        updateCounter();
    } else {
        UI.multiActions.style.display = 'none';
    }
    
    // Timer
    startTimer(q.ends_at);
}

function handleOptionClick(btn, optId) {
    if (answered) return;
    
    // Single choice
    if (!isMulti(currentQuestion)) {
        selectedIds = new Set([optId]);
        document.querySelectorAll('.option-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        
        // Auto submit after short delay
        setTimeout(() => submitAnswer(), 150);
        return;
    }
    
    // Multi choice
    const max = maxSelect(currentQuestion);
    
    if (selectedIds.has(optId)) {
        selectedIds.delete(optId);
        btn.classList.remove('selected');
    } else {
        if (selectedIds.size >= max) return;
        selectedIds.add(optId);
        btn.classList.add('selected');
    }
    
    updateCounter();
}

/* ═══════════════════════════════════════════════════════════════
   SUBMIT ANSWER
   ═══════════════════════════════════════════════════════════════ */

function submitAnswer() {
    if (!currentQuestion || selectedIds.size === 0 || answered) return;
    
    answered = true;
    disableOptions();
    showStatus('sending', '🚀 Cavab göndərilir...');
    
    const startedAt = currentQuestion.started_at ? new Date(currentQuestion.started_at).getTime() : Date.now();
    const answerMs = Math.max(0, Date.now() - startedAt);
    
    const payload = {
        type: 'answer',
        question_id: currentQuestion.id,
        answer_ms: answerMs
    };
    
    if (isMulti(currentQuestion)) {
        payload.option_ids = Array.from(selectedIds);
    } else {
        payload.option_id = Array.from(selectedIds)[0];
    }
    
    try {
        playWS.send(JSON.stringify(payload));
    } catch (e) {
        console.error('Send error:', e);
    }
}

// Submit button for multi
UI.submitBtn.onclick = () => {
    if (isMulti(currentQuestion) && !answered) {
        submitAnswer();
    }
};

/* ═══════════════════════════════════════════════════════════════
   RENDER REVEAL
   ═══════════════════════════════════════════════════════════════ */

function renderReveal(msg) {
    clearTimer();
    disableOptions();
    
    const correctIds = new Set((msg.correct_option_ids || []).map(Number));
    
    // Mark correct/wrong options
    document.querySelectorAll('.option-btn').forEach(btn => {
        const optId = Number(btn.dataset.id);
        if (correctIds.has(optId)) {
            btn.classList.add('correct');
        } else if (selectedIds.has(optId)) {
            btn.classList.add('wrong');
        }
    });
    
    // Determine if user was correct
    let isCorrect = false;
    if (answered && selectedIds.size > 0) {
        if (isMulti(currentQuestion)) {
            isCorrect = selectedIds.size === correctIds.size && 
                        Array.from(selectedIds).every(id => correctIds.has(Number(id)));
        } else {
            isCorrect = correctIds.has(Number(Array.from(selectedIds)[0]));
        }
        showStatus(isCorrect ? 'correct' : 'wrong', isCorrect ? '🎉 Düzgün!' : '❌ Səhv!');
    } else {
        showStatus('timeout', '⚠️ Cavab verilmədi');
    }
    
    // Show leaderboard
    renderLeaderboard(msg.top || []);
    renderResults(msg.results || []);
    UI.leaderboardSection.style.display = 'block';
}

/* ═══════════════════════════════════════════════════════════════
   RENDER LEADERBOARD
   ═══════════════════════════════════════════════════════════════ */

function renderLeaderboard(top) {
    UI.leaderboardList.innerHTML = '';
    
    top.slice(0, 10).forEach((p, i) => {
        const div = document.createElement('div');
        div.className = 'lb-row';
        div.innerHTML = `
            <div class="lb-info">
                <span class="lb-rank">${i + 1}</span>
                <span class="lb-avatar">${AVATARS[p.avatar_key] || '👤'}</span>
                <span class="lb-name">${esc(p.nickname)}</span>
            </div>
            <span class="lb-score">${p.score || 0}</span>
        `;
        UI.leaderboardList.appendChild(div);
    });
}

function renderResults(results) {
    UI.resultsList.innerHTML = '';
    
    if (!results || results.length === 0) {
        UI.resultsSection.style.display = 'none';
        return;
    }
    
    UI.resultsSection.style.display = 'block';
    
    results.slice(0, 10).forEach(r => {
        const div = document.createElement('div');
        div.className = `result-row ${r.is_correct ? 'correct' : 'wrong'}`;
        div.innerHTML = `
            <div class="result-info">
                <span class="result-avatar">${AVATARS[r.avatar_key] || '👤'}</span>
                <span class="result-name">${esc(r.nickname)}</span>
            </div>
            <span class="result-points">${r.is_correct ? '+' + (r.awarded_points || 0) : '0'}</span>
        `;
        UI.resultsList.appendChild(div);
    });
}

/* ═══════════════════════════════════════════════════════════════
   RENDER FINAL
   ═══════════════════════════════════════════════════════════════ */

function renderFinal(msg) {
    clearTimer();
    
    // Create confetti
    UI.confettiLayer.innerHTML = '';
    const colors = ['#fbbf24', '#ef4444', '#3b82f6', '#10b981', '#a855f7', '#ec4899'];
    for (let i = 0; i < 50; i++) {
        const c = document.createElement('div');
        c.className = 'confetti-piece';
        c.style.cssText = `
            left: ${Math.random() * 100}%;
            animation-delay: ${Math.random() * 3}s;
            animation-duration: ${3 + Math.random() * 2}s;
            background: ${colors[Math.floor(Math.random() * colors.length)]};
            width: ${6 + Math.random() * 8}px;
            height: ${6 + Math.random() * 8}px;
            border-radius: ${Math.random() > 0.5 ? '50%' : '2px'};
        `;
        UI.confettiLayer.appendChild(c);
    }
    
    // Render leaderboard
    UI.finalLeaderboard.innerHTML = '';
    
    (msg.top || []).slice(0, 10).forEach((p, i) => {
        const div = document.createElement('div');
        div.className = 'final-row';
        div.style.animationDelay = `${0.1 + i * 0.1}s`;
        div.innerHTML = `
            <div class="final-info">
                <span class="final-rank">${i + 1}</span>
                <span class="final-avatar">${AVATARS[p.avatar_key] || '👤'}</span>
                <span class="final-name">${esc(p.nickname)}</span>
            </div>
            <span class="final-score">${p.score || 0} xal</span>
        `;
        UI.finalLeaderboard.appendChild(div);
    });
    
    UI.finalScreen.style.display = 'block';
}

/* ═══════════════════════════════════════════════════════════════
   WEBSOCKET
   ═══════════════════════════════════════════════════════════════ */

const playWS = new WebSocket(wsUrl(`/ws/live/${GAME_CONFIG.pin}/play/`));

playWS.onopen = async () => {
    setConnection(true);
    
    // Fetch initial state
    try {
        const res = await fetch(`/live/state/${GAME_CONFIG.pin}/`, {
            headers: { 'Accept': 'application/json' }
        });
        const st = await res.json();
        
        if (st.ok && st.question) {
            renderQuestion(st.question);
            
            if (st.state === 'reveal') {
                renderReveal({
                    correct_option_ids: st.correct_option_ids || [],
                    top: [],
                    results: []
                });
            }
        }
    } catch (e) {
        console.error('State fetch error:', e);
    }
};

playWS.onclose = () => setConnection(false);
playWS.onerror = () => setConnection(false);

playWS.onmessage = (e) => {
    try {
        const msg = JSON.parse(e.data);
        const data = msg.data || msg;
        
        switch (data.type) {
            case 'question_published':
                renderQuestion(data.question);
                break;
                
            case 'answer_saved':
                showStatus('sending', '✅ Cavab qəbul edildi!');
                break;
                
            case 'reveal':
                renderReveal(data);
                break;
                
            case 'finished':
                renderFinal(data);
                break;
        }
    } catch (err) {
        console.error('Message parse error:', err);
    }
};