import { UI } from './dom.js?v=lx20261008';
import { LOBBY_MAX_BUBBLES, PHASES } from './constants.js?v=lx20261008';
import { state } from './state.js?v=lx20261008';
import { playJoin } from './audio.js?v=lx20261008';
import { icon } from './icons.js?v=lx20261008';
import { setPresentationMarkup } from './presentation.js?v=lx20261008';
import { renderTimeSettings } from './time_setting.js?v=lx20261008';
import {
    avatarImageMarkup,
    buildJoinUrl,
    controlsEnabled,
    currentQrUrl,
    esc,
    fmt,
    formatNumber,
    joinUrlLabel,
    notifyHostShell,
    pinMarkup,
    tr,
} from './utils.js?v=lx20261008';

/* Lobbi: «qabıq» (qoşulma kartı, PIN, QR, başlıq) yalnız öz imzası dəyişəndə
 * yenidən çəkilir; oyunçu buludu isə id ilə fərq (diff) edilir — yeni gələn
 * «pop» animasiyası + qoşulma səsi alır, köhnələr yerində qalır (sayrışma yoxdur). */
const cloud = { rendered: new Map(), known: new Set(), initialized: false };

export function resetLobbyStage() {
    cloud.rendered.clear();
    cloud.known.clear();
    cloud.initialized = false;
}

function shellSignature() {
    return [
        "lobby",
        CONFIG.pin,
        state.isLocked ? "locked" : "open",
        state.sessionSettings.two_step_join === false ? "direct" : "pin",
        CONFIG.entryUrl || "",
    ].join(":");
}

/* Sahib 2026-09-30: «Yenilə» — oyunçu siyahısını/sayını serverdən (state JSON) yenidən çəkir,
 * səhifəni yeniləmədən yerində çəkir (WS hadisəsi itibsə və ya qopub-qoşulubsa). Yalnız
 * idarə edən aparıcıda (proyektor görünüşündə yox). Klik: events.js (delegasiya). */
function refreshButtonMarkup() {
    if (!controlsEnabled()) return "";
    const hint = tr("refreshPlayersHint", "Oyunçu siyahısını serverdən yenilə");
    return `<button type="button" class="hx-refresh" data-action="refresh-state" title="${esc(hint)}">${icon("refresh")}<span>${esc(tr("refreshPlayers", "Yenilə"))}</span></button>`;
}

function shellMarkup() {
    const joinUrl = joinUrlLabel(buildJoinUrl()) || CONFIG.entryUrl || "";
    const locked = Boolean(state.isLocked);
    return `
        <section class="hx-scene hx-lobby ${locked ? "is-locked" : ""}" data-lobby>
            <header class="hx-lobby__top">
                <div class="hx-join">
                    <div class="hx-join__step">
                        <span class="hx-join__num" aria-hidden="true">1</span>
                        <div class="hx-join__copy">
                            <span class="hx-join__label">${esc(tr("lobbyJoinAt", "Qoşulmaq üçün keçid"))}</span>
                            <strong class="hx-join__url">${esc(joinUrl)}</strong>
                        </div>
                    </div>
                    <div class="hx-join__step hx-join__step--pin">
                        <span class="hx-join__num" aria-hidden="true">2</span>
                        <div class="hx-join__copy">
                            <span class="hx-join__label">${esc(tr("lobbyPinLabel", "Oyun PIN-i"))}</span>
                            <strong class="hx-pin" aria-label="PIN ${esc(CONFIG.pin)}">${pinMarkup(CONFIG.pin)}</strong>
                        </div>
                    </div>
                    ${
                        locked
                            ? `<div class="hx-join__locked" role="status">${icon("lock")}<span><strong>${esc(tr("lobbyLocked", "Qoşulma bağlanıb"))}</strong>${esc(tr("lobbyLockedHint", "Yeni iştirakçılar qoşula bilməz"))}</span></div>`
                            : ""
                    }
                </div>
                <button type="button" class="hx-qr" data-action="open-qr" aria-label="${esc(tr("lobbyScanQr", "QR kodu böyüt"))}">
                    <img src="${esc(currentQrUrl())}" alt="" width="260" height="260">
                    <span>${esc(tr("lobbyScanQr", "Və ya QR kodu skan edin"))}</span>
                </button>
            </header>
            <div class="hx-lobby__mid">
                <h1 class="hx-lobby__title" data-len="${String(CONFIG.examTitle || "").length > 48 ? "l" : "s"}">${esc(CONFIG.examTitle || tr("introTitle", "Viktorina"))}</h1>
                <div class="hx-lobby__meta">
                    <div class="hx-count" aria-live="polite">
                        ${icon("users")}
                        <strong data-lobby-count>0</strong>
                        <span>${esc(tr("lobbyPlayersWord", "iştirakçı"))}</span>
                    </div>
                    ${refreshButtonMarkup()}
                    <div class="hx-lobby__time" data-time-setting></div>
                    <div class="hx-lobby__status" data-lobby-status></div>
                </div>
            </div>
            <div class="hx-cloud hx-scroll" data-lobby-cloud data-density="l" tabindex="0" aria-label="${esc(tr("lobbyParticipants", "Qoşulan iştirakçılar"))}"></div>
            <p class="hx-cloud-hint" aria-hidden="true">${icon("down")}<span>${esc(tr("lobbyScrollHint", "Hamısını görmək üçün siyahını sürüşdürün"))}</span></p>
            <p class="hx-lobby__empty" data-lobby-empty>
                <span class="hx-dots" aria-hidden="true"><i></i><i></i><i></i></span>
                ${esc(tr("lobbyEmpty", "Hələ heç kim qoşulmayıb — telefonla PIN-i daxil edin"))}
            </p>
        </section>
    `;
}

function bubbleMarkup(player, removable) {
    const id = Number(player?.id || 0);
    const name = esc(player?.nickname || "");
    return `
        <span class="hx-bubble__avatar">${avatarImageMarkup(player, 64, "hx-bubble__img")}</span>
        <span class="hx-bubble__name" title="${name}">${name}</span>
        ${
            removable
                ? `<button type="button" class="hx-bubble__remove" data-remove-player-id="${id}" aria-label="${esc(tr("lobbyRemove", "İştirakçını çıxar"))}: ${name}" title="${esc(tr("lobbyRemove", "İştirakçını çıxar"))}">${icon("close")}</button>`
                : ""
        }
    `;
}

function bubbleKey(player) {
    return [player?.nickname || "", player?.avatar_key || "", player?.accessory_key || ""].join("|");
}

function updateStatus(root, count) {
    const status = root.querySelector("[data-lobby-status]");
    if (!status) return;
    let text = tr("lobbyWaiting", "İştirakçılar gözlənilir…");
    let tone = "waiting";
    if (state.isLocked) {
        text = tr("lobbyLocked", "Qoşulma bağlanıb");
        tone = "locked";
    } else if (count > 0) {
        text = controlsEnabled() ? tr("lobbyReadyHost", "Hazır olduqda «Başla» düyməsini basın") : tr("lobbyReady", "Oyun tezliklə başlayır!");
        tone = "ready";
    }
    if (status.dataset.tone !== tone || status.textContent.trim() !== text) {
        status.dataset.tone = tone;
        status.innerHTML = `<span class="hx-lobby__dot" aria-hidden="true"></span><span>${esc(text)}</span>`;
    }
}

function renderCloud(root, fromData) {
    const list = root.querySelector("[data-lobby-cloud]");
    if (!list) return;
    const players = (Array.isArray(state.players) ? state.players : []).slice().reverse(); // server: ən yeni birinci
    const total = Math.max(Number(state.rosterCount || 0), players.length);
    const visible = players.slice(-LOBBY_MAX_BUBBLES);
    const hidden = Math.max(0, total - visible.length);

    const removable = controlsEnabled();
    const nextIds = new Set(visible.map((player) => String(player.id)));
    cloud.rendered.forEach((entry, id) => {
        if (!nextIds.has(id)) {
            entry.el.remove();
            cloud.rendered.delete(id);
        }
    });

    let more = list.querySelector("[data-lobby-more]");
    if (hidden > 0) {
        if (!more) {
            more = document.createElement("span");
            more.className = "hx-bubble hx-bubble--more";
            more.dataset.lobbyMore = "1";
            list.prepend(more);
        }
        more.textContent = fmt(tr("lobbyMore", "+{count} daha"), { count: formatNumber(hidden) });
    } else if (more) {
        more.remove();
    }

    let anchor = more || null;
    visible.forEach((player) => {
        const id = String(player.id);
        let entry = cloud.rendered.get(id);
        const key = bubbleKey(player);
        if (!entry) {
            const el = document.createElement("article");
            el.className = "hx-bubble";
            el.dataset.playerId = id;
            el.innerHTML = bubbleMarkup(player, removable);
            // «Yeni» yalnız ilk server məlumatından SONRA gələnlərdir (refresh-də 30 pop olmasın).
            if (cloud.initialized && !cloud.known.has(id)) {
                el.classList.add("is-new");
                playJoin(`join:${CONFIG.pin}:${id}`);
            }
            entry = { el, key };
            cloud.rendered.set(id, entry);
        } else if (entry.key !== key) {
            entry.el.innerHTML = bubbleMarkup(player, removable);
            entry.key = key;
        }
        const expected = anchor ? anchor.nextElementSibling : list.firstElementChild;
        if (expected !== entry.el) {
            if (anchor) anchor.after(entry.el);
            else list.prepend(entry.el);
        }
        anchor = entry.el;
    });

    const countEl = root.querySelector("[data-lobby-count]");
    if (countEl) countEl.textContent = formatNumber(total);
    root.classList.toggle("has-players", total > 0);
    fitCloud(root, list, total);
    updateStatus(root, total);
    if (fromData) {
        players.forEach((player) => cloud.known.add(String(player.id)));
        cloud.initialized = true;
    }
}

/* 2026-10-08 (L1): sıxlıq sayla başlayır, sığmırsa pillə-pillə kiçilir; ən kiçikdə də sığmırsa
 * siyahı SÜRÜŞÜR (əvvəl `overflow: hidden` idi — 22 nəfərdə adlar ekranın altında itirdi). */
const DENSITIES = ["l", "m", "s", "xs", "xxs"];
const CROWD_THRESHOLD = 12;

function densityForCount(total) {
    if (total <= 12) return 0;
    if (total <= 30) return 1;
    if (total <= 60) return 2;
    if (total <= 120) return 3;
    return 4;
}

const overflows = (list) => list.scrollHeight > list.clientHeight + 2;

function syncScrollEnd(list) {
    const atEnd = list.scrollTop + list.clientHeight >= list.scrollHeight - 4;
    list.classList.toggle("is-scrolled-end", atEnd);
    list.closest("[data-lobby]")?.classList.toggle("is-scrolled-end", atEnd);
}

function fitCloud(root, list, total) {
    root.dataset.crowd = total > CROWD_THRESHOLD ? "1" : "0";
    let level = densityForCount(total);
    list.dataset.density = DENSITIES[level];
    while (level < DENSITIES.length - 1 && total > 0 && overflows(list)) {
        level += 1;
        list.dataset.density = DENSITIES[level];
    }
    const scrollable = total > 0 && overflows(list);
    list.classList.toggle("is-scrollable", scrollable);
    root.classList.toggle("is-overflowing", scrollable);
    syncScrollEnd(list);
}

/** Pəncərə ölçüsü dəyişəndə (proyektor / tam ekran) sıxlığı yenidən seç. */
export function refitLobbyCloud() {
    if (state.sessionState !== "lobby") return;
    const root = UI.presentationContent?.querySelector("[data-lobby]");
    const list = root?.querySelector("[data-lobby-cloud]");
    if (root && list) fitCloud(root, list, Math.max(Number(state.rosterCount || 0), list.childElementCount));
}

/* Siyahının ölçüsü dəyişəndə (pəncərə, tam ekran, idarə panelinin itələməsi — L5) sıxlıq yenidən seçilir.
 * Yalnız «resize» hadisəsi kifayət etmir: panel keçidi / state sinxronu ilə yarışda köhnə enə görə ölçülürdü. */
let refitFrame = 0;
const cloudResizeObserver =
    typeof ResizeObserver === "function"
        ? new ResizeObserver(() => {
              if (refitFrame) return;
              refitFrame = window.requestAnimationFrame(() => {
                  refitFrame = 0;
                  refitLobbyCloud();
              });
          })
        : null;

document.addEventListener(
    "scroll",
    (event) => {
        if (event.target?.matches?.("[data-lobby-cloud]")) syncScrollEnd(event.target);
    },
    true
);

export function renderIdleStage(fromData = false) {
    if (state.sessionState !== "lobby") return;
    const signature = shellSignature();
    const fresh = setPresentationMarkup(PHASES.IDLE, signature, shellMarkup());
    if (fresh) {
        cloud.rendered.clear();
    }
    const root = UI.presentationContent?.querySelector("[data-lobby]");
    if (fresh && root) {
        renderTimeSettings(root);
        const list = root.querySelector("[data-lobby-cloud]");
        if (list && cloudResizeObserver) {
            cloudResizeObserver.disconnect();
            cloudResizeObserver.observe(list);
        }
    }
    if (root) renderCloud(root, fromData);
}

/** «Yenilə»: bulud DOM-u sıfırdan qurulur (itmiş/artıq baloncuqlar düzəlir; «yeni» pop-u YOX). */
export function rebuildLobbyCloud() {
    if (state.sessionState !== "lobby") return;
    const root = UI.presentationContent?.querySelector("[data-lobby]");
    const list = root?.querySelector("[data-lobby-cloud]");
    if (!root || !list) return;
    list.textContent = "";
    cloud.rendered.clear();
    renderCloud(root, true);
}

export function renderLobbyPlayers(players, totalCount = null) {
    state.players = Array.isArray(players) ? players : [];
    const expectedTotal = Number.isFinite(Number(totalCount)) && totalCount != null ? Number(totalCount) : state.players.length;
    // 2026-10-08 (L3): roster sayı ≠ cari suala cavab verməli olanlar (gec qoşulan növbəti sualdan
    // sayılır) — oyun gedərkən `totalPlayers`-i yalnız server sayğacları (answer_progress / sual) yeniləyir.
    state.rosterCount = expectedTotal;
    if (state.sessionState === "lobby") state.totalPlayers = expectedTotal;
    if (UI.playersCount) UI.playersCount.textContent = String(state.rosterCount);
    if (state.sessionState === "lobby") renderIdleStage(true);
    notifyHostShell();
}
