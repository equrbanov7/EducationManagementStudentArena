/* ═══════════════════════════════════════════════════════════════
   HOST LOBBY - Full Rewrite
   ═══════════════════════════════════════════════════════════════ */

// DOM Elements
const $ = id => document.getElementById(id);

const UI = {
    startBtn: $('startBtn'),
    revealBtn: $('revealBtn'),
    nextBtn: $('nextBtn'),
    finishBtn: $('finishBtn'),
    questionCount: $('questionCount'),
    autoMode: $('autoMode'),
    gameState: $('gameState'),
    lobbyHeader: $('lobbyHeader'),
    gameArea: $('gameArea'),
    questionPanel: $('questionPanel'),
    resultsPanel: $('resultsPanel'),
    resultsList: $('resultsList'),
    playersSection: $('playersSection'),
    playersCount: $('playersCount'),
    playersList: $('playersList'),
    leaderList: $('leaderList'),
    finalPodium: $('finalPodium'),
    podiumStage: $('podiumStage'),
    othersList: $('othersList'),
    confetti: $('confetti'),
    progressBox: $('progressBox'),
    answeredText: $('answeredText'),
    debugBtn: $('debugBtn'),
    debugLog: $('debugLog'),
    qMeta: $('qMeta'),
    qText: $('qText'),
    qTimer: $('qTimer'),
    qOptions: $('qOptions'),
    reactionOverlay: $('hostReactionOverlay')
};

let state = 'lobby';
let timerInterval = null;
let autoRevealTimeout = null;
let autoNextTimeout = null;
let totalPlayers = 0;
const I18N = window.LIVE_EXAM_HOST_I18N || {};
const tr = (key, fallback) => I18N[key] || fallback;
const fmt = (template, values) =>
    String(template || '').replace(/\{(\w+)\}/g, (_, key) => (values && key in values ? values[key] : `{${key}}`));
const stateLabel = (value) => {
    if (value === 'question') return tr('stateQuestion', 'Question');
    if (value === 'reveal') return tr('stateReveal', 'Reveal');
    if (value === 'finished') return tr('stateFinished', 'Finished');
    return tr('stateLobby', 'Lobby');
};

/* ═══════════════════════════════════════════════════════════════
   DEBUG
   ═══════════════════════════════════════════════════════════════ */

let debugOn = false;
const logs = [];

UI.debugBtn?.addEventListener('click', () => {
    debugOn = !debugOn;
    UI.debugBtn.innerHTML = `<i class="fas fa-terminal"></i> ${tr('debugLabel', 'Debug')} ${debugOn ? '▾' : '▸'}`;
    UI.debugLog.style.display = debugOn ? 'block' : 'none';
});

function log(msg) {
    console.log('[HOST]', msg);
    if (!UI.debugLog) return;
    logs.unshift(`> ${new Date().toLocaleTimeString()} ${msg}`);
    if (logs.length > 100) logs.length = 100;
    UI.debugLog.textContent = logs.join('\n');
}

/* ═══════════════════════════════════════════════════════════════
   HELPERS
   ═══════════════════════════════════════════════════════════════ */

const wsUrl = path => `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}${path}`;
const esc = t => { const d = document.createElement('div'); d.textContent = t || ''; return d.innerHTML; };
const avatarMarkup = (player, size, className = '') =>
    window.LiveAvatarRenderer.renderAvatarMarkup(player || {}, { size, className, interactive: false });

function spawnReaction(eventData) {
    if (!UI.reactionOverlay) return;
    const meta = (window.LiveAvatarCatalog || {}).reactions?.[eventData?.reaction_key] || {};
    const burst = document.createElement('div');
    burst.className = 'host-reaction-burst';
    burst.innerHTML = `
        <span class="host-reaction-burst__emoji">${meta.emoji || eventData?.emoji || '✨'}</span>
        <span class="host-reaction-burst__name">${esc(eventData?.player?.nickname || '')}</span>
    `;
    const left = 16 + Math.random() * 68;
    const drift = -26 + Math.random() * 52;
    burst.style.left = `${left}%`;
    burst.style.setProperty('--reaction-drift', `${drift}px`);
    UI.reactionOverlay.appendChild(burst);
    setTimeout(() => burst.remove(), 2300);
}

async function post(url, data = null) {
    try {
        const opts = { method: 'POST', headers: { 'X-CSRFToken': CONFIG.csrf } };
        if (data) opts.body = data;
        const res = await fetch(url, opts);
        const payload = await res.json();
        if (payload && payload.ok) {
            await syncState();
        }
        return payload;
    } catch (e) {
        log(fmt(tr('postError', 'POST error: {message}'), { message: e.message }));
        return { ok: false };
    }
}

async function syncState() {
    try {
        const res = await fetch(CONFIG.urls.state, {
            headers: { Accept: 'application/json' }
        });
        if (!res.ok) {
            log(`State sync failed: ${res.status}`);
            return null;
        }
        const snapshot = await res.json();
        applyStateSnapshot(snapshot);
        return snapshot;
    } catch (e) {
        log(fmt(tr('playMessageError', 'Play message error: {message}'), { message: e.message || '' }));
        return null;
    }
}

function applyStateSnapshot(snapshot) {
    if (!snapshot || !snapshot.ok) return;

    if (snapshot.state === 'question' && snapshot.question) {
        setState('question');
        renderQuestion(snapshot.question);
        UI.answeredText.textContent = `0 / ${totalPlayers}`;
        return;
    }

    if (snapshot.state === 'reveal') {
        setState('reveal');
        renderResults(snapshot.results || []);
        renderLeaderboard(snapshot.top || []);
        return;
    }

    if (snapshot.state === 'finished') {
        setState('finished');
        renderPodium(snapshot.top || []);
        return;
    }

    setState('lobby');
}

/* ═══════════════════════════════════════════════════════════════
   UI STATE
   ═══════════════════════════════════════════════════════════════ */

function setState(newState) {
    state = newState;
    const label = stateLabel(state);
    UI.gameState.textContent = label;
    
    UI.startBtn.disabled = state !== 'lobby';
    UI.revealBtn.disabled = state !== 'question';
    UI.nextBtn.disabled = state !== 'reveal';
    
    const isLobby = state === 'lobby';
    const isQuestion = state === 'question';
    const isReveal = state === 'reveal';
    const isFinished = state === 'finished';
    
    UI.lobbyHeader.style.display = isLobby ? 'block' : 'none';
    UI.playersSection.style.display = isLobby ? 'block' : 'none';
    UI.gameArea.style.display = (isQuestion || isReveal) ? 'grid' : 'none';
    UI.questionPanel.style.display = isQuestion ? 'block' : 'none';
    UI.resultsPanel.style.display = isReveal ? 'block' : 'none';
    UI.finalPodium.style.display = isFinished ? 'block' : 'none';
    UI.progressBox.style.display = isQuestion ? 'flex' : 'none';
    
    if (!isQuestion) {
        clearInterval(timerInterval);
        UI.qTimer.textContent = '--';
        UI.qTimer.className = 'timer';
    }
    
    log(fmt(tr('stateLog', 'State: {state}'), { state: label }));
}

/* ═══════════════════════════════════════════════════════════════
   WEBSOCKETS
   ═══════════════════════════════════════════════════════════════ */

// Lobby WS
const lobbyWS = new WebSocket(wsUrl(`/ws/live/${CONFIG.pin}/lobby/`));
lobbyWS.onopen = () => log(tr('wsLobbyOpen', 'Lobby WS open'));
lobbyWS.onclose = () => log(tr('wsLobbyClosed', 'Lobby WS closed'));

lobbyWS.onmessage = e => {
    try {
        const msg = JSON.parse(e.data);
        const d = msg.data || msg;
        
        if (d.type === 'lobby_state') {
            totalPlayers = d.count || 0;
            UI.playersCount.textContent = totalPlayers;
            
            UI.playersList.innerHTML = '';
            (d.players || []).forEach(p => {
                const div = document.createElement('div');
                div.className = 'player-chip';
                div.innerHTML = `<div class="avatar">${avatarMarkup(p, 54, 'host-avatar host-avatar--chip')}</div><div class="name">${esc(p.nickname)}</div>`;
                UI.playersList.appendChild(div);
            });
        }
        else if (d.type === 'reaction_event') {
            spawnReaction(d);
        }
    } catch (err) {
        log(fmt(tr('lobbyMessageError', 'Lobby message error: {message}'), { message: err.message || '' }));
    }
};

// Play WS
const playWS = new WebSocket(wsUrl(`/ws/live/${CONFIG.pin}/play/`));
playWS.onopen = async () => {
    log(tr('wsPlayOpen', 'Play WS open'));
    await syncState();
};
playWS.onclose = () => log(tr('wsPlayClosed', 'Play WS closed'));

playWS.onmessage = e => {
    try {
        const msg = JSON.parse(e.data);
        const d = msg.data || msg;
        
        if (d.type === 'question_published') {
            setState('question');
            renderQuestion(d.question);
            UI.answeredText.textContent = `0 / ${totalPlayers}`;
            
            // Auto reveal at end
            if (UI.autoMode.checked && d.question.ends_at) {
                const ms = Math.max(0, new Date(d.question.ends_at) - Date.now());
                clearTimeout(autoRevealTimeout);
                autoRevealTimeout = setTimeout(() => {
                    if (state === 'question') UI.revealBtn.click();
                }, ms + 200);
            }
        }
        
        else if (d.type === 'answer_progress') {
            const answered = d.answered_count || 0;
            const total = d.total_players || totalPlayers;
            UI.answeredText.textContent = `${answered} / ${total}`;
            
            // All answered -> auto reveal
            if (answered >= total && total > 0 && state === 'question') {
                log(tr('allAnsweredAutoReveal', 'All answered, auto reveal!'));
                clearTimeout(autoRevealTimeout);
                setTimeout(() => {
                    if (state === 'question') UI.revealBtn.click();
                }, 400);
            }
        }
        
        else if (d.type === 'reveal') {
            setState('reveal');
            renderResults(d.results || []);
            renderLeaderboard(d.top || []);
            
            // Auto next
            if (UI.autoMode.checked) {
                clearTimeout(autoNextTimeout);
                autoNextTimeout = setTimeout(() => {
                    if (state === 'reveal') UI.nextBtn.click();
                }, 4000);
            }
        }
        
        else if (d.type === 'finished') {
            setState('finished');
            renderPodium(d.top || []);
        }
        
    } catch (err) {
        log(fmt(tr('playMessageError', 'Play message error: {message}'), { message: err.message || '' }));
    }
};

/* ═══════════════════════════════════════════════════════════════
   RENDER
   ═══════════════════════════════════════════════════════════════ */

function renderQuestion(q) {
    UI.qMeta.textContent = fmt(tr('questionMeta', 'Question {index} / {total}'), {
        index: q.index,
        total: q.total,
    });
    UI.qText.textContent = q.text;
    
    UI.qOptions.innerHTML = '';
    (q.options || []).forEach((opt, i) => {
        const div = document.createElement('div');
        div.className = `opt-card opt-${i % 4}`;
        div.innerHTML = `<span class="letter">${String.fromCharCode(65 + i)}</span><span>${esc(opt.text)}</span>`;
        UI.qOptions.appendChild(div);
    });
    
    // Timer
    if (q.ends_at) {
        const end = new Date(q.ends_at).getTime();
        clearInterval(timerInterval);
        
        timerInterval = setInterval(() => {
            const left = Math.max(0, Math.ceil((end - Date.now()) / 1000));
            UI.qTimer.textContent = left;
            
            UI.qTimer.className = 'timer' + (left <= 5 ? ' danger' : left <= 10 ? ' warning' : '');
            
            if (left <= 0) clearInterval(timerInterval);
        }, 200);
    }
}

function renderResults(results) {
    UI.resultsList.innerHTML = '';
    
    if (!results || results.length === 0) {
        UI.resultsList.innerHTML = `<div style="text-align:center;opacity:0.6;padding:20px;">${tr('noAnswersYet', 'No one answered yet')}</div>`;
        return;
    }
    
    results.slice(0, 10).forEach(r => {
        const div = document.createElement('div');
        div.className = `result-row ${r.is_correct ? 'correct' : 'wrong'}`;
        div.innerHTML = `
            <div class="result-info">
                ${avatarMarkup(r, 38, 'result-avatar host-avatar')}
                <span class="result-name">${esc(r.nickname)}</span>
            </div>
            <span class="result-points">${r.is_correct ? '+' + (r.awarded_points || 0) : '0'}</span>
        `;
        UI.resultsList.appendChild(div);
    });
}

function renderLeaderboard(top) {
    UI.leaderList.innerHTML = '';
    
    top.slice(0, 10).forEach((p, i) => {
        const div = document.createElement('div');
        div.className = 'leader-row';
        div.innerHTML = `
            <div class="leader-info">
                <span class="leader-rank">${i + 1}</span>
                ${avatarMarkup(p, 40, 'leader-avatar host-avatar')}
                <span class="leader-name">${esc(p.nickname)}</span>
            </div>
            <span class="leader-score">${p.score || 0}</span>
        `;
        UI.leaderList.appendChild(div);
    });
}

function renderPodium(top) {
    // Confetti
    UI.confetti.innerHTML = '';
    const colors = ['#fbbf24','#ef4444','#3b82f6','#10b981','#a855f7','#ec4899'];
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
        UI.confetti.appendChild(c);
    }
    
    // Podium
    UI.podiumStage.innerHTML = '';
    const t3 = top.slice(0, 3);
    const order = [];
    if (t3[1]) order.push({ ...t3[1], place: 2, cls: 'p2' });
    if (t3[0]) order.push({ ...t3[0], place: 1, cls: 'p1' });
    if (t3[2]) order.push({ ...t3[2], place: 3, cls: 'p3' });
    
    order.forEach((p, i) => {
        const div = document.createElement('div');
        div.className = `podium-block ${p.cls}`;
        div.style.animationDelay = `${0.2 + i * 0.25}s`;
        div.innerHTML = `
            <div class="podium-card">
                ${p.place === 1 ? '<div class="crown">👑</div>' : ''}
                <div class="podium-avatar">${avatarMarkup(p, 78, 'podium-avatar host-avatar')}</div>
                <div class="podium-name">${esc(p.nickname)}</div>
                <div class="podium-score">${p.score || 0} ${tr('pointsSuffix', 'pts')}</div>
            </div>
            <div class="podium-stand">${p.place}</div>
        `;
        UI.podiumStage.appendChild(div);
    });
    
    // Others
    UI.othersList.innerHTML = '';
    top.slice(3, 10).forEach((p, i) => {
        const div = document.createElement('div');
        div.className = 'other-row';
        div.style.animationDelay = `${0.8 + i * 0.1}s`;
        div.innerHTML = `
            <div class="other-info">
                <span class="other-rank">${i + 4}</span>
                ${avatarMarkup(p, 38, 'other-avatar host-avatar')}
                <span class="other-name">${esc(p.nickname)}</span>
            </div>
            <span class="other-score">${p.score || 0}</span>
        `;
        UI.othersList.appendChild(div);
    });
}

/* ═══════════════════════════════════════════════════════════════
   BUTTON HANDLERS
   ═══════════════════════════════════════════════════════════════ */

UI.startBtn.onclick = () => {
    const fd = new FormData();
    const count = parseInt(UI.questionCount.value) || 1;
    fd.append('question_count', count);
    post(CONFIG.urls.start, fd);
};

UI.revealBtn.onclick = () => post(CONFIG.urls.reveal);
UI.nextBtn.onclick = () => post(CONFIG.urls.next);
UI.finishBtn.onclick = () => post(CONFIG.urls.finish);

// Question count input - proper handling
UI.questionCount.addEventListener('focus', function() {
    this.select();
});

UI.questionCount.addEventListener('blur', function() {
    let v = parseInt(this.value) || 1;
    if (v < 1) v = 1;
    if (v > CONFIG.maxQuestions) v = CONFIG.maxQuestions;
    this.value = v;
});

UI.questionCount.addEventListener('keydown', function(e) {
    // Allow: backspace, delete, tab, escape, enter, arrows
    if ([8, 46, 9, 27, 13, 37, 38, 39, 40].includes(e.keyCode)) return;
    // Allow: Ctrl+A, Ctrl+C, Ctrl+V, Ctrl+X
    if ((e.ctrlKey || e.metaKey) && [65, 67, 86, 88].includes(e.keyCode)) return;
    // Allow: numbers
    if ((e.keyCode >= 48 && e.keyCode <= 57) || (e.keyCode >= 96 && e.keyCode <= 105)) return;
    e.preventDefault();
});

/* ═══════════════════════════════════════════════════════════════
   INIT
   ═══════════════════════════════════════════════════════════════ */

setState('lobby');
log(tr('hostReady', 'Host ready'));
syncState();
