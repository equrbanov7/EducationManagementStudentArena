/* players_drawer.js — aparıcının «İştirakçılar» çekməcəsi + çıxarma təsdiqi (2026-10-08, L6).
 *
 * «Kahoot gedə gedə istifadəçi çıxara bilirik?» — bəli: siyahıdan (lobbidə və oyun gedərkən)
 * iştirakçı seçilir, təsdiq dialoqu açılır, server oyunçunu çıxarır (socket bağlanır, eyni cihazla
 * qayıtmır, balı liderlər lövhəsində görünmür). Lobbi baloncuqlarındakı «×» də eyni dialoqdan keçir.
 * Siyahı: lobbi roster-i (WS `lobby_state`) + açılışda HTTP snapshot. Hadisələr document-də delegasiya.
 */
import { state } from './state.js?v=lx20261008';
import { post, syncState } from './api.js?v=lx20261008';
import { showToast } from './toast.js?v=lx20261008';
import { avatarImageMarkup, controlsEnabled, esc, fmt, formatNumber, tr } from './utils.js?v=lx20261008';
import { icon } from './icons.js?v=lx20261008';

const $ = (id) => document.getElementById(id);
let bound = false;
let listSignature = "";
let confirmState = null;
const removing = new Set();

const dom = () => ({
    drawer: $("hostPlayersDrawer"),
    backdrop: $("hostPlayersBackdrop"),
    list: document.querySelector("[data-players-list]"),
    search: document.querySelector("[data-players-search]"),
    confirm: $("hostConfirm"),
});

const isOpen = () => document.body.classList.contains("host-players-open");

function playerRows() {
    const players = Array.isArray(state.players) ? state.players.slice() : [];
    // Server: ən yeni birinci → siyahıda qoşulma sırası ilə.
    return players.reverse();
}

function rowMarkup(player) {
    const id = Number(player?.id || 0);
    const name = esc(player?.nickname || "");
    const late = Number(player?.active_from_index || 0) > Number(state.currentQuestion?.index || 0) - 1 && state.sessionState !== "lobby";
    const busy = removing.has(id);
    return `
        <div class="host-player-row" role="listitem" data-player-row="${id}">
            <span class="host-player-row__avatar">${avatarImageMarkup(player, 40, "host-player-row__img")}</span>
            <span class="host-player-row__name" title="${name}">${name}</span>
            ${late ? `<span class="host-player-row__tag">${esc(tr("playersLateTag", "Növbəti sualdan"))}</span>` : ""}
            <button type="button" class="host-player-row__remove" data-remove-player-id="${id}" ${busy ? "disabled" : ""}
                    aria-label="${esc(tr("lobbyRemove", "İştirakçını çıxar"))}: ${name}">
                ${icon("userMinus")}<span>${esc(tr("playersRemove", "Çıxar"))}</span>
            </button>
        </div>
    `;
}

/** Çekməcə siyahısı və idarə panelindəki say nişanı. */
export function renderPlayersDrawer() {
    const count = Math.max(Number(state.rosterCount || 0), Array.isArray(state.players) ? state.players.length : 0);
    document.querySelectorAll("[data-players-count], [data-players-total]").forEach((el) => {
        el.textContent = formatNumber(count);
    });
    const { list, search } = dom();
    if (!list || !isOpen()) return;
    const needle = String(search?.value || "").trim().toLocaleLowerCase();
    const rows = playerRows().filter((player) => !needle || String(player.nickname || "").toLocaleLowerCase().includes(needle));
    const signature = `${needle}|${state.sessionState}|${state.currentQuestion?.index || 0}|${[...removing].join(",")}|${rows
        .map((player) => `${player.id}:${player.nickname}:${player.avatar_key}:${player.active_from_index || 0}`)
        .join(",")}`;
    if (signature === listSignature) return;
    listSignature = signature;
    list.innerHTML = rows.length
        ? rows.map(rowMarkup).join("")
        : `<p class="host-players-empty">${esc(needle ? tr("playersNoMatch", "Uyğun iştirakçı yoxdur") : tr("playersEmpty", "Hələ heç kim qoşulmayıb"))}</p>`;
}

function setDrawerOpen(open) {
    const { drawer, backdrop, search } = dom();
    if (!drawer) return;
    document.body.classList.toggle("host-players-open", open);
    drawer.setAttribute("aria-hidden", open ? "false" : "true");
    if (backdrop) backdrop.hidden = !open;
    document.querySelectorAll("[data-action='open-players']").forEach((button) => button.setAttribute("aria-expanded", open ? "true" : "false"));
    if (open) {
        listSignature = "";
        renderPlayersDrawer();
        syncState(); // siyahı serverdən təzələnsin (oyun gedərkən WS qopubsa da)
        window.requestAnimationFrame(() => search?.focus());
    }
}

function findPlayer(id) {
    return (Array.isArray(state.players) ? state.players : []).find((player) => Number(player.id) === Number(id)) || { id, nickname: "" };
}

function openConfirm(player, trigger) {
    const { confirm } = dom();
    if (!confirm) return;
    const inGame = state.sessionState === "question" || state.sessionState === "reveal";
    confirmState = { player, trigger };
    $("hostConfirmTitle").textContent = fmt(tr("removeConfirmTitle", "«{name}» oyundan çıxarılsın?"), { name: player.nickname || "?" });
    $("hostConfirmBody").textContent = inGame
        ? tr("removeConfirmBodyGame", "Telefonu oyundan çıxacaq, bu cihazla geri qayıda bilməyəcək. Balı liderlər lövhəsində göstərilməyəcək.")
        : tr("removeConfirmBodyLobby", "Telefonu lobbidən çıxacaq və bu cihazla geri qayıda bilməyəcək.");
    confirm.hidden = false;
    document.body.classList.add("host-confirm-open");
    window.requestAnimationFrame(() => confirm.querySelector("[data-confirm-cancel]")?.focus());
}

function closeConfirm() {
    const { confirm } = dom();
    if (!confirm || confirm.hidden) return;
    confirm.hidden = true;
    document.body.classList.remove("host-confirm-open");
    const trigger = confirmState?.trigger;
    confirmState = null;
    if (trigger?.isConnected) trigger.focus();
}

async function removeConfirmed() {
    const player = confirmState?.player;
    closeConfirm();
    if (!player?.id || removing.has(Number(player.id))) return;
    removing.add(Number(player.id));
    renderPlayersDrawer();
    const formData = new FormData();
    formData.append("player_id", player.id);
    try {
        const result = await post(CONFIG.urls.removePlayer, formData);
        if (result?.ok) {
            showToast(fmt(tr("removeDone", "«{name}» oyundan çıxarıldı"), { name: player.nickname || "" }), "ok");
        } else {
            showToast(result?.message || tr("removeFailed", "Çıxarmaq alınmadı. Yenidən cəhd edin."), "error");
        }
    } finally {
        removing.delete(Number(player.id));
        listSignature = "";
        renderPlayersDrawer();
    }
}

/** Lobbi baloncuğu və çekməcə sətri — ikisi də bu təsdiqdən keçir. */
export function requestPlayerRemoval(playerId, trigger) {
    if (!controlsEnabled() || !CONFIG?.urls?.removePlayer || state.sessionState === "finished") return;
    openConfirm(findPlayer(playerId), trigger);
}

export function bindPlayersDrawer() {
    if (bound || !controlsEnabled()) return;
    bound = true;
    document.addEventListener("click", (event) => {
        const target = event.target;
        if (target.closest?.("[data-action='open-players']")) {
            setDrawerOpen(!isOpen());
            return;
        }
        if (target.closest?.("[data-players-close]")) {
            setDrawerOpen(false);
            return;
        }
        if (target.closest?.("[data-confirm-cancel]") || target === dom().confirm) {
            closeConfirm();
            return;
        }
        if (target.closest?.("[data-confirm-ok]")) {
            removeConfirmed();
            return;
        }
        const remove = target.closest?.("[data-remove-player-id]");
        if (remove && !remove.disabled) {
            event.preventDefault();
            requestPlayerRemoval(Number(remove.dataset.removePlayerId), remove);
        }
    });
    document.addEventListener("input", (event) => {
        if (event.target.matches?.("[data-players-search]")) renderPlayersDrawer();
    });
    document.addEventListener(
        "keydown",
        (event) => {
            if (event.key !== "Escape") return;
            if (!dom().confirm?.hidden) {
                event.stopImmediatePropagation();
                closeConfirm();
            } else if (isOpen()) {
                event.stopImmediatePropagation();
                setDrawerOpen(false);
                document.querySelector("[data-action='open-players']")?.focus();
            }
        },
        true
    );
    window.addEventListener("live-host-state", renderPlayersDrawer);
    renderPlayersDrawer();
}
