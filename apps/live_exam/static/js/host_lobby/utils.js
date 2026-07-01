import { UI } from './dom.js';
import { state } from './state.js';

export const I18N = window.LIVE_EXAM_HOST_I18N || {};
export const hostShellSubscribers = new Set();
export const tr = (key, fallback) => I18N[key] || fallback;
export const controlsEnabled = () => CONFIG.controlsEnabled !== false;
export const fmt = (template, values) =>
    String(template || "").replace(/\{(\w+)\}/g, (_, key) => (values && key in values ? values[key] : `{${key}}`));
export const esc = text => {
    const div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
};
export const wsUrl = path => `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${path}`;
export const safeDisplay = (node, value) => {
    if (node) node.style.display = value;
};
export const toMs = value => {
    const parsed = value ? new Date(value).getTime() : 0;
    return Number.isFinite(parsed) ? parsed : 0;
};
export const nowMs = () => Date.now() + Number(state.serverTimeOffsetMs || 0);
export const questionKey = question => `${question?.id || "0"}:${question?.started_at || ""}`;
export const revealKey = payload => `${payload?.question_id || "0"}:${payload?.revealed_at || ""}`;
export const answerWord = count => tr(count === 1 ? "answersSingular" : "answersPlural", count === 1 ? "Answer" : "Answers");
export const progressLabel = question => `${Number(question?.index || 0)} of ${Number(question?.total || 0)}`;
export const usesPresentationStageLayout = () => document.body.classList.contains("host-presentation-page");
export const progressBadgeMarkup = question => `
    <div class="quiz-progress-badge" aria-label="${esc(progressLabel(question))}">
        <strong>${Number(question?.index || 0)}</strong>
        <span>of ${Number(question?.total || 0)}</span>
    </div>
`;
export const avatarMarkup = (player, size, className = "") =>
    (window.LiveAvatarRenderer || { renderAvatarMarkup: () => "" }).renderAvatarMarkup(player || {}, {
        size,
        className,
        interactive: false,
    });
export const avatarImageMarkup = (player, size, className = "") => {
    const renderer = window.LiveAvatarRenderer || {};
    if (typeof renderer.renderAvatarDataUrl !== "function") {
        return avatarMarkup(player, size, className);
    }

    const resolvedSize = Number(size) > 0 ? Number(size) : 72;
    const label = esc(player?.nickname || "Player");
    const classes = ["host-avatar-image", className].filter(Boolean).join(" ");
    return `<img class="${esc(classes)}" src="${renderer.renderAvatarDataUrl(player || {})}" alt="${label}" width="${resolvedSize}" height="${resolvedSize}" decoding="async">`;
};
export const topSignature = rows =>
    (Array.isArray(rows) ? rows : [])
        .map((player) =>
            [
                Number(player?.player_id || player?.id || 0),
                String(player?.nickname || ""),
                Number(player?.score || 0),
            ].join(":")
        )
        .join("|");

function timelinePhaseRank(kind) {
    switch (kind) {
        case "question":
            return 1;
        case "reveal":
            return 2;
        case "finished":
            return 3;
        default:
            return 0;
    }
}

export function updateServerTimeOffset(payload, receivedAtMs = Date.now()) {
    const serverMs = toMs(payload?.server_time);
    if (!serverMs) return;
    const sample = serverMs - receivedAtMs;
    if (!Number.isFinite(sample)) return;
    if (!Number.isFinite(state.serverTimeOffsetMs) || state.serverTimeOffsetMs === 0) {
        state.serverTimeOffsetMs = sample;
        return;
    }
    state.serverTimeOffsetMs = Math.round((state.serverTimeOffsetMs * 3 + sample) / 4);
}

function extractTimelineMeta(payload) {
    if (!payload) return null;

    const kind = payload.type === "finished" || payload.state === "finished"
        ? "finished"
        : payload.type === "reveal" || payload.state === "reveal"
            ? "reveal"
            : payload.type === "question_published" || payload.state === "question"
                ? "question"
                : "lobby";
    const question = payload.question || null;
    const questionId = Number(payload.question_id || question?.id || 0);
    let phaseAtMs = 0;

    if (kind === "finished") {
        phaseAtMs = toMs(payload.finished_at) || toMs(payload.next_question_at) || toMs(payload.revealed_at) || toMs(question?.ends_at);
    } else if (kind === "reveal") {
        phaseAtMs = toMs(payload.revealed_at) || toMs(question?.ends_at) || toMs(payload.question_ends_at);
    } else if (kind === "question") {
        phaseAtMs = toMs(question?.started_at) || toMs(payload.question_started_at);
    }

    return {
        phaseRank: timelinePhaseRank(kind),
        phaseAtMs,
        questionId,
    };
}

function compareTimelineMeta(nextMeta, currentMeta) {
    if (!nextMeta) return 0;
    if (!currentMeta) return 1;
    if (nextMeta.phaseAtMs !== currentMeta.phaseAtMs) {
        return nextMeta.phaseAtMs > currentMeta.phaseAtMs ? 1 : -1;
    }
    if (nextMeta.phaseRank !== currentMeta.phaseRank) {
        return nextMeta.phaseRank > currentMeta.phaseRank ? 1 : -1;
    }
    if (nextMeta.questionId && currentMeta.questionId && nextMeta.questionId !== currentMeta.questionId) {
        return nextMeta.questionId > currentMeta.questionId ? 1 : -1;
    }
    return 0;
}

export function shouldApplyTimelinePayload(payload) {
    const nextMeta = extractTimelineMeta(payload);
    return compareTimelineMeta(nextMeta, state.timelineMeta) >= 0;
}

export function rememberTimelinePayload(payload) {
    const nextMeta = extractTimelineMeta(payload);
    if (!nextMeta) return;
    if (compareTimelineMeta(nextMeta, state.timelineMeta) >= 0) {
        state.timelineMeta = nextMeta;
    }
}


export function buildJoinUrl() {
    const twoStepJoin = state.sessionSettings.two_step_join !== false;
    let origin = location.origin;
    try {
        origin = new URL(CONFIG.entryUrl || location.origin).origin;
    } catch (error) {
        origin = location.origin;
    }
    if (twoStepJoin) {
        const url = new URL("/live/", `${origin}/`);
        url.searchParams.set("pin", CONFIG.pin);
        return url.toString();
    }
    return `${origin}/live/join/${encodeURIComponent(CONFIG.pin)}/`;
}

export function currentQrUrl() {
    const base = CONFIG.qrUrl || "";
    if (!base) return "";
    const cacheKey = state.sessionSettings.two_step_join === false ? "direct" : "pin";
    return `${base}${base.includes("?") ? "&" : "?"}mode=${cacheKey}`;
}

export function publicHostState() {
    return {
        sessionState: state.sessionState,
        phase: state.phase,
        totalPlayers: Number(state.totalPlayers || 0),
        answeredCount: Number(state.answeredCount || 0),
        players: Array.isArray(state.players) ? [...state.players] : [],
        settings: Object.assign({}, state.sessionSettings),
        isLocked: Boolean(state.isLocked),
    };
}

export function notifyHostShell() {
    const snapshot = publicHostState();
    hostShellSubscribers.forEach(listener => {
        try {
            listener(snapshot);
        } catch (error) {
            console.error("live host shell subscriber error", error);
        }
    });
    window.dispatchEvent(new CustomEvent("live-host-state", { detail: snapshot }));
}

export function markStateMutation() {
    state.lastStateMutationAt = nowMs();
}

export function lobbyCopy() {
    const lang = String(CONFIG.languageCode || "az").slice(0, 2).toLowerCase();
    const copy = {
        az: {
            brand: "EMSArena Live",
            joinLabel: "Qoşulmaq üçün",
            joinHint: "Tələbələr link, PIN və ya QR kod ilə qoşula bilər.",
            pinLabel: "Canlı PIN",
            waitingLabel: "İştirakçılar gözlənilir",
            waitingHint: "Müəllim Başla düyməsini sıxan kimi ilk sual yayımlanacaq.",
            audienceLabel: "{count} iştirakçı qoşulub",
            audienceEmpty: "Hələ heç kim qoşulmayıb",
            participantsTitle: "Qoşulan iştirakçılar",
            playersEmpty: "İştirakçılar burada görünəcək.",
            lockedLabel: "Qoşulma bağlanıb",
            lockedHint: "Yeni iştirakçılar artıq bu lobby-yə daxil ola bilməz.",
            removePlayerLabel: "İştirakçını çıxar",
        },
        en: {
            brand: "EMSArena Live",
            joinLabel: "Join the live exam",
            joinHint: "Students can join with the link, PIN, or QR code.",
            pinLabel: "Live PIN",
            waitingLabel: "Waiting for participants",
            waitingHint: "The first question will appear as soon as the teacher presses Start.",
            audienceLabel: "{count} participants joined",
            audienceEmpty: "No participants have joined yet",
            participantsTitle: "Joined participants",
            playersEmpty: "Participants will appear here.",
            lockedLabel: "Lobby locked",
            lockedHint: "New participants cannot join until the teacher unlocks the session.",
            removePlayerLabel: "Remove participant",
        },
        ru: {
            brand: "EMSArena Live",
            joinLabel: "Подключение к игре",
            joinHint: "Участники могут войти по ссылке, PIN-коду или QR-коду.",
            pinLabel: "PIN игры",
            waitingLabel: "Ожидаем участников",
            waitingHint: "Как только преподаватель нажмет Старт, появится первый вопрос.",
            audienceLabel: "Подключились: {count}",
            audienceEmpty: "Пока никто не подключился",
            participantsTitle: "Подключившиеся участники",
            playersEmpty: "Здесь появятся участники.",
            lockedLabel: "Лобби закрыто",
            lockedHint: "Новые участники больше не могут присоединиться к этой сессии.",
            removePlayerLabel: "Удалить участника",
        },
        tr: {
            brand: "EMSArena Live",
            joinLabel: "Canli sinava katıl",
            joinHint: "Öğrenciler bağlantı, PIN veya QR kod ile katılabilir.",
            pinLabel: "Canlı PIN",
            waitingLabel: "Katılımcılar bekleniyor",
            waitingHint: "Öğretmen Başlat'a basar basmaz ilk soru gösterilecek.",
            audienceLabel: "{count} katılımcı bağlandı",
            audienceEmpty: "Henüz kimse bağlanmadı",
            participantsTitle: "Katılan katılımcılar",
            playersEmpty: "Katılımcılar burada görünecek.",
            lockedLabel: "Lobi kilitli",
            lockedHint: "Öğretmen yeniden açana kadar yeni katılımcı giremez.",
            removePlayerLabel: "Katılımcıyı çıkar",
        },
    };
    return copy[lang] || copy.az;
}

export function joinUrlLabel(rawUrl) {
    if (!rawUrl) return "";
    try {
        const parsed = new URL(rawUrl);
        const path = parsed.pathname === "/" ? "" : parsed.pathname.replace(/\/$/, "");
        return `${parsed.host}${path}`;
    } catch (error) {
        return String(rawUrl).replace(/^https?:\/\//, "").replace(/\/$/, "");
    }
}

const logs = [];

export function log(message) {
    console.log("[HOST]", message);
    if (!UI.debugLog) return;
    logs.unshift(`> ${new Date().toLocaleTimeString()} ${message}`);
    if (logs.length > 100) logs.length = 100;
    UI.debugLog.textContent = logs.join("\n");
}


let debugOn = false;

export function bindDebugToggle() {
    UI.debugBtn?.addEventListener("click", () => {
        debugOn = !debugOn;
        UI.debugBtn.innerHTML = `<i class="fas fa-terminal"></i> ${tr("debugLabel", "Debug")} ${debugOn ? "▾" : "▸"}`;
        UI.debugLog.style.display = debugOn ? "block" : "none";
    });
}
