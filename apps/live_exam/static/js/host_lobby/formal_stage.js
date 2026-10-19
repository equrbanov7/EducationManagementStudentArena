/* formal_stage.js — «Rəsmi» üslubun YEKUN NƏTİCƏLƏR ekranı (2026-10-19).
 *
 * Oyunbaz final şousunun (pərdə, projektor, rəqs edən avatarlar, konfetti topları, fanfar — stage.js)
 * əvəzinə sakit sıralama cədvəli: yer · baş hərflər · ad · düzgün cavab · xal. Animasiya, səs və fx
 * kanvası YOXDUR. Sıra — serverin `top` sırası (stage_logic.buildStageModel), müştəridə sıralanmır.
 * Proyektorda oxunaqlı: 10 sətir, iri rəqəmlər; telefonda (idarə paneli) cədvəl üfüqi sürüşmür.
 */
import { icon } from './icons.js?v=lx20261019s';
import { avatarImageMarkup, esc, fmt, formatNumber, formatSeconds, tr } from './utils.js?v=lx20261019s';

function correctCell(player) {
    if (player?.answered_count == null || player?.correct_count == null) return "—";
    return esc(fmt(tr("stageCorrect", "{correct}/{answered} düzgün"), { correct: player.correct_count, answered: player.answered_count }));
}

function rowMarkup(entry) {
    const player = entry.player || {};
    const name = esc(player.nickname || "");
    return `
        <tr class="hx-ftable__row${entry.place <= 3 ? " is-top" : ""}" data-place="${entry.place}">
            <td class="hx-ftable__rank"><span class="hx-ftable__place">${entry.place}</span></td>
            <td class="hx-ftable__who">
                <span class="hx-ftable__who-inner">
                    <span class="hx-ftable__initials">${avatarImageMarkup(player, 40, "hx-ftable__img")}</span>
                    <span class="hx-ftable__name" title="${name}">${name}</span>
                    ${entry.tie ? `<span class="hx-ftable__tie">${esc(tr("stageTie", "Bərabər xal"))}</span>` : ""}
                </span>
            </td>
            <td class="hx-ftable__correct">${correctCell(player)}</td>
            <td class="hx-ftable__score"><strong>${formatNumber(entry.score)}</strong></td>
        </tr>
    `;
}

function statsMarkup(stats) {
    if (!stats || typeof stats !== "object") return "";
    const items = [];
    if (stats.total_players != null) items.push([icon("users"), formatNumber(stats.total_players), tr("stageStatsPlayers", "iştirakçı")]);
    if (stats.total_questions != null) items.push([icon("chartBar"), formatNumber(stats.total_questions), tr("stageStatsQuestions", "sual")]);
    if (stats.correct_rate != null) items.push([icon("checkCircle"), `${Math.round(Number(stats.correct_rate) * 100)}%`, tr("stageStatsAccuracy", "düzgünlük")]);
    if (stats.avg_answer_ms != null) items.push([icon("clock"), `${formatSeconds(stats.avg_answer_ms)} ${tr("secondsShort", "san")}`, tr("stageStatsSpeed", "orta cavab")]);
    if (!items.length) return "";
    return `<dl class="hx-fstats">${items.map(([ic, value, label]) => `<div class="hx-fstats__item">${ic}<dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join("")}</dl>`;
}

/** Bütün final ekranı (`[data-stage]` kökü — stage.js-in bağla/nəticələr düymələri eyni işləyir). */
export function formalStageMarkup(model, payload, { closable = false, resultsUrl = "" } = {}) {
    const rows = [...model.podium, ...model.audience].map(rowMarkup).join("");
    const more = model.more > 0 ? `<p class="hx-ftable__more">${esc(fmt(tr("stageMore", "+{count} iştirakçı"), { count: formatNumber(model.more) }))}</p>` : "";
    const body = model.empty
        ? `<p class="hx-formal-final__empty">${esc(tr("stageNoPlayers", "Bu oyunda iştirakçı olmadı"))}</p>`
        : `
            <div class="hx-ftable-wrap">
                <table class="hx-ftable">
                    <thead>
                        <tr>
                            <th scope="col" class="hx-ftable__rank">${esc(tr("formalRank", "Yer"))}</th>
                            <th scope="col">${esc(tr("formalParticipant", "İştirakçı"))}</th>
                            <th scope="col" class="hx-ftable__correct">${esc(tr("formalCorrect", "Düzgün cavablar"))}</th>
                            <th scope="col" class="hx-ftable__score">${esc(tr("formalScore", "Xal"))}</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
            ${more}`;
    return `
        <div class="hx-stagebox hx-formal-final" data-stage data-phase="static" data-style="formal">
            <header class="hx-formal-final__head">
                <h1 class="hx-formal-final__title">${icon("chartBar")}<span>${esc(tr("formalResultsTitle", "Yekun nəticələr"))}</span></h1>
                <p class="hx-formal-final__sub">${esc(CONFIG.examTitle || "")}</p>
                ${statsMarkup(payload?.stats)}
            </header>
            ${body}
            <div class="hx-stage-controls">
                ${resultsUrl ? `<a class="hx-btn hx-btn--ghost" href="${esc(resultsUrl)}" target="_blank" rel="noopener">${icon("chartBar")}<span>${esc(tr("stageResults", "Ətraflı nəticələr"))}</span></a>` : ""}
                ${closable ? `<button type="button" class="hx-btn hx-btn--ghost hx-btn--icon" data-stage-close aria-label="${esc(tr("close", "Bağla"))}">${icon("close")}</button>` : ""}
            </div>
        </div>
    `;
}
