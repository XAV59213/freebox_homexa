/* Carte Lovelace « Homexa TNT » pour Freebox Homexa.
 *
 * Adapted from cyclope205/programme-tnt-fr v3.0.8 (MIT), www/programme-tnt-fr-card.js.
 * Modifications : nom d'élément homexa-tnt-card (pas de collision avec la carte
 * d'origine), websocket freebox_homexa/tnt_*, services freebox_homexa.*,
 * uniquement les capteurs TNT de Freebox Homexa (attribut homexa_tnt).
 * Servie par l'intégration elle-même, sans CDN ni ressource externe.
 *
 * Utilisation : type: custom:homexa-tnt-card
 *
 * MIT License
 *
 * Copyright (c) 2026 cyclope205
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */

// Ligne « libellé + interrupteur ». Home Assistant 2026 n'affiche plus l'attribut
// `label` de <ha-formfield> : le texte est donc écrit nous-mêmes, à gauche du switch.
function _tntSwitchRow(label, sw, padding) {
  var row = document.createElement("div");
  row.style.display = "flex";
  row.style.alignItems = "center";
  row.style.justifyContent = "space-between";
  row.style.gap = "12px";
  row.style.padding = padding;
  var text = document.createElement("span");
  text.textContent = label;
  text.style.flex = "1";
  text.style.cursor = "pointer";
  text.addEventListener("click", function () {
    sw.checked = !sw.checked;
    sw.dispatchEvent(new Event("change", { bubbles: true }));
  });
  row.appendChild(text);
  return row;
}



const CARD_VERSION = "3.0.8-homexa.1";
(function () {
  "use strict";

  var STYLE = [
    "ha-card { padding: 16px; overflow: hidden; }",
    ".header { font-size: 1.2em; font-weight: 500; margin-bottom: 14px; display: flex; align-items: center; justify-content: space-between; gap: 10px; }",
    ".header-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }",
    ".header-actions { display: flex; gap: 6px; flex-shrink: 0; }",
    ".header-guide-link { flex-shrink: 0; border: none; background: var(--secondary-background-color, #2a2a2a); color: var(--primary-text-color); font-size: 0.62em; font-weight: 700; text-transform: uppercase; letter-spacing: 0.02em; padding: 7px 12px; border-radius: 999px; cursor: pointer; font-family: inherit; display: flex; align-items: center; gap: 5px; }",
    ".header-guide-link:active { transform: scale(0.96); }",
    ".header-guide-link.active { background: var(--primary-color, #3f6fe0); color: #fff; }",
    ".header-guide-link[hidden] { display: none; }",
    ".slot-section { margin-bottom: 10px; }",
    ".slot-section:last-child { margin-bottom: 0; }",
    ".slot-title-header { font-size: 1.12em; font-weight: 700; margin-bottom: 12px; color: var(--primary-text-color); display: flex; align-items: center; gap: 9px; }",
    ".slot-title-icon { width: 8px; height: 22px; border-radius: 4px; flex-shrink: 0; }",
    ".slot-title-icon.live { background: #e0263f; }",
    ".slot-title-icon.prime { background: #3f6fe0; }",
    ".slot-title-icon.second { background: #1c9c8a; }",
    ".slot-title-icon.next { background: #f2a900; }",
    ".carousel-wrap { position: relative; }",
    ".carousel { display: flex; gap: 12px; overflow-x: auto; overflow-y: hidden; padding: 2px 2px 2px; scroll-snap-type: x mandatory; -webkit-overflow-scrolling: touch; scroll-behavior: smooth; }",
    ".carousel::-webkit-scrollbar { display: none; }",
    ".carousel { scrollbar-width: none; }",
    ".poster-card { position: relative; flex: 0 0 calc((100% - (var(--tntfr-columns, 2) - 1) * 12px) / var(--tntfr-columns, 2)); width: calc((100% - (var(--tntfr-columns, 2) - 1) * 12px) / var(--tntfr-columns, 2)); border-radius: 18px; overflow: hidden; display: flex; flex-direction: column; border: none; padding: 0; margin: 0; cursor: pointer; scroll-snap-align: start; background: none; transition: transform 0.15s ease; font-family: inherit; -webkit-tap-highlight-color: transparent; }",
    ".poster-card:active { transform: scale(0.97); }",
    ".poster-card:disabled { cursor: default; opacity: 0.55; }",
    ".poster-image-wrap { position: relative; width: 100%; aspect-ratio: 2 / 3; overflow: hidden; flex-shrink: 0; border-radius: 18px; box-shadow: 0 8px 20px rgba(0,0,0,0.35); }",
    ".poster-bg { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }",
    ".poster-bg--contain { object-fit: contain; position: relative; z-index: 1; background: transparent; }",
    ".poster-bg-fill { position: absolute; inset: 0; background-size: cover; background-position: center; filter: blur(20px) brightness(0.55); transform: scale(1.15); z-index: 0; }",
    ".poster-watermark { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; opacity: 0.16; }",
    ".poster-watermark img { width: 52%; height: 52%; object-fit: contain; filter: brightness(0) invert(1); }",
    ".poster-channel-badge { position: absolute; bottom: 10px; left: 10px; width: 34px; height: 34px; border-radius: 50%; background: #fff; padding: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.45); object-fit: contain; z-index: 1; }",
    ".poster-channel-badge-zap { cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,0.45), 0 0 0 2px rgba(255,255,255,0.9); }",
    ".poster-channel-badge-zap:hover { transform: scale(1.08); }",
    ".poster-channel-badge-zap:active { transform: scale(0.95); }",
    ".guide-col-logo-zap { cursor: pointer; box-shadow: 0 0 0 2px rgba(255,255,255,0.9); }",
    ".guide-col-logo-zap:hover { transform: scale(1.08); }",
    ".guide-col-logo-zap:active { transform: scale(0.95); }",
    ".poster-favorite-badge { position: absolute; top: 10px; left: 10px; width: 26px; height: 26px; border-radius: 50%; background: rgba(255,179,0,0.95); display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 8px rgba(0,0,0,0.4); z-index: 2; color: #fff; }",
    ".poster-favorite-badge svg { width: 14px; height: 14px; }",
    ".guide-item-favorite-badge { position: absolute; top: 4px; left: 4px; width: 18px; height: 18px; border-radius: 50%; background: rgba(255,179,0,0.95); display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 4px rgba(0,0,0,0.4); z-index: 2; color: #fff; }",
    ".guide-item-favorite-badge svg { width: 10px; height: 10px; }",
    ".guide-col-logo-wrap { position: relative; display: inline-flex; }",
    ".guide-col-favorite-badge { position: absolute; top: -4px; left: -4px; width: 18px; height: 18px; border-radius: 50%; background: rgba(255,179,0,0.95); display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 4px rgba(0,0,0,0.4); z-index: 2; color: #fff; }",
    ".guide-col-favorite-badge svg { width: 10px; height: 10px; }",
    ".modal-notify-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 4px; }",
    ".modal-notify-row[hidden] { display: none; }",
    ".modal-notify-label { font-size: 0.85em; opacity: 0.8; }",
      ".modal-notify-profile { font-size: 0.8em; padding: 4px 8px; border-radius: 8px; border: 1px solid var(--divider-color, #555); background: var(--card-background-color, #1c1c1c); color: var(--primary-text-color); }",
      ".modal-notify-profile[hidden] { display: none; }",
    ".modal-notify-btn { border: none; background: var(--primary-color, #3f6fe0); color: #fff; font-size: 0.8em; font-weight: 600; padding: 6px 12px; border-radius: 999px; cursor: pointer; font-family: inherit; }",
    ".modal-notify-btn:active { transform: scale(0.95); }",
    ".modal-notify-cancel-btn { border: 1px solid var(--divider-color, #555); background: transparent; color: var(--primary-text-color); font-size: 0.8em; font-weight: 600; padding: 6px 12px; border-radius: 999px; cursor: pointer; font-family: inherit; }",
    ".modal-notify-cancel-btn:active { transform: scale(0.95); }",
    ".modal-notify-status { font-size: 0.8em; opacity: 0.85; margin-left: 2px; }",
    ".poster-live-badge { position: absolute; top: 10px; right: 10px; display: flex; align-items: center; gap: 5px; background: rgba(224,38,63,0.94); color: #fff; font-size: 0.66em; font-weight: 800; letter-spacing: 0.04em; text-transform: uppercase; padding: 5px 10px 5px 8px; border-radius: 20px; box-shadow: 0 2px 10px rgba(224,38,63,0.5); z-index: 1; }",
    ".poster-live-dot { width: 6px; height: 6px; border-radius: 50%; background: #fff; animation: tntfr-pulse 1.6s infinite; }",
    "@keyframes tntfr-pulse { 0% { box-shadow: 0 0 0 0 rgba(255,255,255,0.7); } 70% { box-shadow: 0 0 0 6px rgba(255,255,255,0); } 100% { box-shadow: 0 0 0 0 rgba(255,255,255,0); } }",
    ".poster-content { padding: 10px 12px 2px; color: var(--primary-text-color); background: transparent; flex: 1 1 auto; }",
    ".poster-channel-name { font-size: 0.72em; font-weight: 700; opacity: 0.85; text-transform: uppercase; letter-spacing: 0.03em; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }",
    ".poster-title { font-size: 1.02em; font-weight: 700; line-height: 1.28; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }",
    ".poster-time { font-size: 0.76em; font-weight: 600; opacity: 0.9; margin-top: 6px; }",
    ".poster-progress-track { position: absolute; left: 0; right: 0; bottom: 0; height: 4px; background: rgba(255,255,255,0.25); }",
    ".poster-progress-fill { position: absolute; left: 0; bottom: 0; height: 4px; background: #e0263f; }",
    ".poster-empty-msg { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; padding: 10px; text-align: center; font-size: 0.85em; opacity: 0.7; font-style: italic; color: var(--primary-text-color); }",
    ".carousel-nav { position: absolute; top: 50%; transform: translateY(-50%); width: 40px; height: 40px; border-radius: 50%; border: none; background: rgba(15,15,25,0.68); backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px); color: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center; z-index: 3; opacity: 0; transition: opacity 0.18s ease, transform 0.18s ease; padding: 0; box-shadow: 0 2px 12px rgba(0,0,0,0.45); }",
    ".carousel-nav.visible { opacity: 0.92; }",
    ".carousel-nav.visible:hover { opacity: 1; transform: translateY(-50%) scale(1.08); }",
    ".carousel-nav svg { width: 20px; height: 20px; }",
    ".carousel-nav.prev { left: 6px; }",
    ".carousel-nav.next { right: 6px; }",
    ".overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.55); display: flex; align-items: center; justify-content: center; z-index: 1000; }",
    ".overlay[hidden] { display: none; }",
    ".modal { background: var(--card-background-color, #fff); color: var(--primary-text-color); border-radius: 12px; padding: 20px; max-width: 480px; width: 90%; max-height: 80vh; overflow-y: auto; position: relative; }",
    ".modal .close { position: absolute; top: 8px; right: 12px; background: none; border: none; font-size: 1.5em; cursor: pointer; color: var(--primary-text-color); line-height: 1; }",
    ".modal-icon { width: 100%; max-height: 220px; object-fit: cover; border-radius: 8px; margin-bottom: 12px; }",
    ".modal-icon[hidden] { display: none; }",
    ".modal-title { margin: 0 0 4px 0; font-size: 1.2em; }",
    ".modal-subtitle { font-style: italic; opacity: 0.85; margin-bottom: 8px; }",
    ".modal-subtitle[hidden] { display: none; }",
    ".modal-meta { font-size: 0.85em; opacity: 0.7; margin-bottom: 12px; }",
    ".modal-rating { font-size: 0.9em; font-weight: 700; margin-bottom: 12px; }",
    ".modal-rating[hidden] { display: none; }",
    ".modal-desc { line-height: 1.45; white-space: pre-line; }",
    ".modal-tmdb-link { display: block; margin-top: 16px; font-size: 0.85em; font-weight: 700; color: var(--primary-color, #3f6fe0); text-decoration: none; }",
    ".modal-tmdb-link[hidden] { display: none; }",
    ".guide-header { margin-bottom: 10px; }",
    ".guide-search { width: 100%; box-sizing: border-box; padding: 10px 14px; border-radius: 999px; border: none; background: var(--secondary-background-color, #2a2a2a); color: var(--primary-text-color); font-size: 0.95em; margin-bottom: 10px; font-family: inherit; }",
    ".guide-daybar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }",
    ".guide-day-btn { width: 36px; height: 36px; flex-shrink: 0; border-radius: 50%; border: none; background: var(--secondary-background-color, #2a2a2a); color: var(--primary-text-color); cursor: pointer; display: flex; align-items: center; justify-content: center; padding: 0; }",
    ".guide-day-btn svg { width: 18px; height: 18px; }",
    ".guide-day-label { flex: 1; text-align: center; padding: 8px 12px; border-radius: 999px; border: none; background: var(--secondary-background-color, #2a2a2a); color: var(--primary-text-color); font-weight: 600; cursor: pointer; font-family: inherit; font-size: 0.92em; text-transform: capitalize; }",
    ".guide-day-input { position: absolute; width: 0; height: 0; opacity: 0; pointer-events: none; }",
    ".guide-hour-filter { flex-shrink: 0; border: none; background: var(--secondary-background-color, #2a2a2a); color: var(--primary-text-color); font-weight: 600; font-size: 0.78em; padding: 0 10px; border-radius: 999px; font-family: inherit; cursor: pointer; height: 36px; max-width: 92px; }",
    ".guide-genre-bar { margin-bottom: 12px; }",
    ".guide-genre-filter { width: 100%; box-sizing: border-box; border: none; background: var(--secondary-background-color, #2a2a2a); color: var(--primary-text-color); font-weight: 600; font-size: 0.85em; padding: 9px 14px; border-radius: 999px; font-family: inherit; cursor: pointer; }",
    ".tntfr-hidden { display: none !important; }",
    ".guide-columns { display: flex; gap: 12px; overflow-x: auto; overflow-y: hidden; scroll-snap-type: x mandatory; -webkit-overflow-scrolling: touch; scroll-behavior: smooth; }",
    ".guide-columns::-webkit-scrollbar { display: none; }",
    ".guide-columns { scrollbar-width: none; }",
    ".guide-column { flex: 0 0 calc(50% - 6px); min-width: 0; scroll-snap-align: start; display: flex; flex-direction: column; }",
    ".guide-column.tntfr-hidden { display: none; }",
    ".guide-col-header { display: flex; align-items: center; gap: 8px; padding: 6px 4px 10px; }",
    ".guide-col-logo { width: 32px; height: 32px; border-radius: 50%; background: #fff; padding: 3px; object-fit: contain; flex-shrink: 0; box-shadow: 0 1px 4px rgba(0,0,0,0.3); }",
    ".guide-col-meta { min-width: 0; }",
    ".guide-col-lcn { font-size: 0.65em; opacity: 0.6; font-weight: 600; }",
    ".guide-col-name { font-size: 0.9em; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }",
    ".guide-col-list { display: flex; flex-direction: column; gap: 10px; overflow-y: auto; max-height: 60vh; padding: 2px 2px 8px; }",
    ".guide-item { display: flex; flex-direction: column; flex-shrink: 0; text-align: left; border: none; padding: 0; margin: 0; cursor: pointer; font-family: inherit; color: inherit; -webkit-tap-highlight-color: transparent; border-radius: 12px; overflow: hidden; background: none; }",
    ".guide-item.is-live { outline: 2px solid #e0263f; outline-offset: -2px; }",
    ".guide-item-image-wrap { position: relative; width: 100%; aspect-ratio: 2 / 3; overflow: hidden; flex-shrink: 0; }",
    ".guide-item-img { width: 100%; height: 100%; object-fit: cover; display: block; }",
    ".guide-item-img--contain { object-fit: contain; position: relative; z-index: 1; background: transparent; }",
    ".guide-item-bg-fill { position: absolute; inset: 0; background-size: cover; background-position: center; filter: blur(16px) brightness(0.55); transform: scale(1.15); z-index: 0; }",
    ".guide-item-img[hidden] { display: none; }",
    ".guide-item-live-badge { position: absolute; top: 8px; right: 8px; display: flex; align-items: center; gap: 5px; background: rgba(224,38,63,0.94); color: #fff; font-size: 0.62em; font-weight: 800; letter-spacing: 0.04em; text-transform: uppercase; padding: 4px 9px 4px 7px; border-radius: 20px; box-shadow: 0 2px 10px rgba(224,38,63,0.5); z-index: 1; }",
    ".guide-item-live-dot { width: 6px; height: 6px; border-radius: 50%; background: #fff; animation: tntfr-pulse 1.6s infinite; }",
    ".guide-item-progress-track { position: absolute; left: 0; right: 0; bottom: 0; height: 3px; background: rgba(255,255,255,0.25); }",
    ".guide-item-progress-fill { position: absolute; left: 0; bottom: 0; height: 3px; background: #e0263f; }",
    ".guide-item-body { padding: 8px 10px 10px; }",
    ".guide-item-title { font-size: 0.92em; font-weight: 700; line-height: 1.28; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }",
    ".guide-item-meta { font-size: 0.72em; font-weight: 600; opacity: 0.78; margin-top: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }",
    ".guide-empty, .guide-loading { padding: 20px 8px; text-align: center; opacity: 0.6; font-size: 0.85em; font-style: italic; }",
    ".films-root { touch-action: pan-y; }",
    ".films-list { display: flex; flex-wrap: wrap; gap: 12px; touch-action: pan-y; }",
    ".film-row { flex: 0 0 calc(50% - 6px); width: calc(50% - 6px); display: flex; flex-direction: column; background: none; border: none; padding: 0; margin: 0; cursor: pointer; font-family: inherit; -webkit-tap-highlight-color: transparent; text-align: left; color: inherit; }",
    ".film-row:active { transform: scale(0.97); }",
    ".film-poster-wrap { position: relative; width: 100%; aspect-ratio: 2 / 3; overflow: hidden; border-radius: 18px; box-shadow: 0 8px 20px rgba(0,0,0,0.35); background: rgba(127,127,127,0.2); }",
    ".film-poster { width: 100%; height: 100%; object-fit: cover; display: block; }",
    ".film-medal-badge { position: absolute; top: 6px; left: 6px; font-size: 1.4em; filter: drop-shadow(0 1px 2px rgba(0,0,0,0.6)); }",
    ".film-info { min-width: 0; margin-top: 6px; }",
    ".film-title { font-weight: 700; font-size: 0.92em; line-height: 1.25; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }",
    ".film-meta { font-size: 0.75em; opacity: 0.75; margin-top: 3px; }"
  ].join("\n");

    // Voir option de carte "zap_channel_scripts" (documentee dans le README) :
  // dictionnaire channel_id -> entity_id de script HA fourni par l'utilisateur.



var SLOT_DEFS = [
    ["current", "En ce moment à la télé", "live"],
    ["next", "À suivre", "next"],
    ["prime_time", "Programmes télé en 1ère partie de soirée", "prime"],
    ["second_part", "Programmes télé en 2ème partie de soirée", "second"]
  ];

  // Vue : cle interne, libelle du bouton, cle de config pour l'afficher/masquer.
  // Utilise a la fois pour construire les 3 boutons d'en-tete et pour piloter
  // quelle vue est affichee (voir _isViewEnabled/_enabledViews/_firstEnabledView).
  var VIEW_DEFS = [
    ["carousel", "Carrousel", "show_carousel"],
    ["favorites", "Favoris", "show_favorites"],
    ["guide", "Guide TV", "show_guide_tv"],
    ["topfilms", "Top films", "show_top_films"]
  ];

  var CHEVRON_LEFT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>';
  var CHEVRON_RIGHT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>';
  var STAR_ICON = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 .587l3.668 7.568 8.332 1.151-6.064 5.828 1.48 8.279L12 19.771l-7.416 3.642 1.48-8.279L0 9.306l8.332-1.151z"/></svg>';

  // Curated display order for TNT channels, matching the physical remote
  // numbering with related channels grouped nearby (e.g. Canal+ variants,
  // Planete+ next to France 5). This is only the INITIAL/fallback copy so
  // the very first render (before the backend round-trip in _checkVersion
  // below resolves) is already correctly ordered - the authoritative copy
  // now lives in const.py's CHANNEL_ORDER and overrides this one via the
  // freebox_homexa/tnt_version websocket response, so a channel added only
  // on the backend gets ordered correctly here too instead of silently
  // falling back to rank 999 forever.
  var CHANNEL_ORDER = {
    "TF1.fr": 1, "France2.fr": 2, "France3.fr": 3,
    "CanalPlus.fr": 3.1, "CanalPlusCinema.fr": 3.2, "CanalPlusSport.fr": 3.3,
    "France4.fr": 4, "France5.fr": 5, "PlanetePlus.fr": 5.1,
    "M6.fr": 6, "Arte.fr": 7, "LaChaineParlementaire.fr": 8,
    "W9.fr": 9, "TMC.fr": 10, "NT1.fr": 11, "Gulli.fr": 12,
    "BFMTV.fr": 13, "CNews.fr": 14, "LCI.fr": 15, "FranceInfo.fr": 16,
    "CStar.fr": 17, "T18.fr": 18, "NOVO19.fr": 19, "TF1SeriesFilms.fr": 20,
    "LEquipe21.fr": 21, "6ter.fr": 22, "Numero23.fr": 23,
    "RMCDecouverte.fr": 24, "Cherie25.fr": 25, "ParisPremiere.fr": 26
  };

  function channelName(hass, entityId) {
    var attrs = hass.states[entityId].attributes || {};
    return attrs.channel_name || entityId;
  }

  function channelRank(hass, entityId) {
    var attrs = hass.states[entityId].attributes || {};
    var cid = attrs.channel_id;
    if (cid && Object.prototype.hasOwnProperty.call(CHANNEL_ORDER, cid)) {
      return CHANNEL_ORDER[cid];
    }
    return 999;
  }

  function formatTime(iso) {
    if (!iso) return null;
    var d = new Date(iso);
    if (isNaN(d.getTime())) return null;
    var h = String(d.getHours()).padStart(2, "0");
    var m = String(d.getMinutes()).padStart(2, "0");
    return h + "h" + m;
  }

  function formatProgDate(dateStr) {
    if (!dateStr) return null;
    var digits = String(dateStr).replace(/[^0-9]/g, "");
    if (digits.length < 4) return null;
    var year = digits.slice(0, 4);
    var months = [
      "janvier", "fevrier", "mars", "avril", "mai", "juin",
      "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
    ];
    if (digits.length >= 8) {
      var day = parseInt(digits.slice(6, 8), 10);
      var monthIdx = parseInt(digits.slice(4, 6), 10) - 1;
      if (monthIdx >= 0 && monthIdx < 12 && day > 0) {
        return day + " " + months[monthIdx] + " " + year;
      }
    }
    if (digits.length >= 6) {
      var monthIdx2 = parseInt(digits.slice(4, 6), 10) - 1;
      if (monthIdx2 >= 0 && monthIdx2 < 12) {
        return months[monthIdx2] + " " + year;
      }
    }
    return year;
  }

  function liveFraction(prog) {
    if (!prog || !prog.start || !prog.stop) return null;
    var start = new Date(prog.start).getTime();
    var stop = new Date(prog.stop).getTime();
    if (isNaN(start) || isNaN(stop) || stop <= start) return null;
    var now = Date.now();
    var frac = (now - start) / (stop - start);
    if (frac < 0) frac = 0;
    if (frac > 1) frac = 1;
    return frac;
  }

  var DAY_NAMES_FR = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"];

  function isoDateLocal(d) {
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1).padStart(2, "0");
    var day = String(d.getDate()).padStart(2, "0");
    return y + "-" + m + "-" + day;
  }

  function dayLabelFr(d) {
    var dow = DAY_NAMES_FR[d.getDay()];
    var dd = String(d.getDate()).padStart(2, "0");
    var mm = String(d.getMonth() + 1).padStart(2, "0");
    return dow + " " + dd + "/" + mm;
  }

  function normalizeSearch(s) {
    return (s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }

  function isProgLive(prog) {
    var f = liveFraction(prog);
    return f !== null && f > 0 && f < 1;
  }

  function pickPrimeTimeProgramme(progs, thresholdDate) {
    var sorted = (progs || []).slice().sort(function (a, b) {
      return new Date(a.start).getTime() - new Date(b.start).getTime();
    });
    var t = thresholdDate.getTime();
    for (var i = 0; i < sorted.length; i++) {
      var s = new Date(sorted[i].start).getTime();
      var e = new Date(sorted[i].stop).getTime();
      if (s <= t && t < e) return sorted[i];
    }
    for (var j = 0; j < sorted.length; j++) {
      if (new Date(sorted[j].start).getTime() >= t) return sorted[j];
    }
    return null;
  }

    async function checkCardBackendVersion(context) {
      if (
        context._versionCheckDone ||
        !context._hass ||
        !context._hass.connection
      ) {
        return;
      }
    
      context._versionCheckDone = true;
    
      try {
        const result = await context._hass.connection.sendMessagePromise({
          type: "freebox_homexa/tnt_version",
        });
    
        if (result && result.version && result.version !== CARD_VERSION) {
          context._showVersionMismatch(result.version);
        }
    
        if (
          result &&
          result.channel_order &&
          typeof result.channel_order === "object"
        ) {
          CHANNEL_ORDER = result.channel_order;
          context._render();
        }
      } catch (err) {
        // Best-effort only: an older backend or a transient websocket
        // error must never break the card.
      }
    }

    async function loadBackendChannelOrder(context) {
      if (
        context._channelOrderLoaded ||
        !context._hass ||
        !context._hass.connection
      ) {
        return;
      }
    
      context._channelOrderLoaded = true;
    
      try {
        const result = await context._hass.connection.sendMessagePromise({
          type: "freebox_homexa/tnt_version",
        });
    
        if (
          result &&
          result.channel_order &&
          typeof result.channel_order === "object"
        ) {
          CHANNEL_ORDER = result.channel_order;
          context._render();
        }
      } catch (err) {
        // Keep the local fallback order if the backend does not provide it.
      }
    }

  class ProgrammeTntFrCard extends HTMLElement {
    setConfig(config) {
      this._config = config || {};
      var tntfrCols = Math.max(1, Number(this._config.columns) || 2);
      this.style.setProperty("--tntfr-columns", tntfrCols);
      this._entities = this._config.entities || null;
      this._built = false;
      this._carouselSig = null;
      this._view = this._firstEnabledView();
      this._guideBuilt = false;
      this._guideCache = {};
      this._guideDate = new Date();
      this._guideHourFilter = "";
      this._guideGenreFilter = "";
      this._filmsBuilt = false;
      this._filmsCache = {};
      this._filmsDate = new Date();
      this._render();
    }

    set hass(hass) {
      const firstHass = !this._hass;
    
      this._hass = hass;
      this._render();
    
      if (firstHass) {
        loadBackendChannelOrder(this);
      }
    }

    getCardSize() {
      return 12;
    }

    _resolveEntities(favoritesOnly) {
      var hass = this._hass;
      if (!hass) return [];
      var ids;
      if (this._entities && this._entities.length) {
        ids = this._entities.filter(function (id) {
          return !!hass.states[id];
        });
      } else {
        ids = Object.keys(hass.states).filter(function (id) {
          var st = hass.states[id];
          return id.indexOf("sensor.") === 0 && st.attributes && st.attributes.channel_id && st.attributes.homexa_tnt;
        });
      }
      ids.sort(function (a, b) {
        var ra = channelRank(hass, a);
        var rb = channelRank(hass, b);
        if (ra !== rb) return ra - rb;
        return channelName(hass, a).localeCompare(channelName(hass, b), "fr", { sensitivity: "base" });
      });

      var favorites = this._config.favorite_channels;
      if (favorites && favorites.length) {
        var favSet = {};
        favorites.forEach(function (cid) { favSet[cid] = true; });
        if (favoritesOnly) {
          ids = ids.filter(function (id) {
            var cid = hass.states[id].attributes.channel_id;
            return cid && favSet[cid];
          });
        } else {
          var favIds = [];
          var restIds = [];
          ids.forEach(function (id) {
            var cid = hass.states[id].attributes.channel_id;
            if (cid && favSet[cid]) {
              favIds.push(id);
            } else {
              restIds.push(id);
            }
          });
          ids = favIds.concat(restIds);
        }
      } else if (favoritesOnly) {
        ids = [];
      }

      return ids;
    }

    // Une vue est affichee sauf si sa cle de config vaut explicitement false
    // (meme convention que show_current/show_prime_time/show_second_part).
    // Cas particulier de "show_favorites" : cette vue n'a de sens que si au
    // moins une chaine favorite est configuree, meme si elle n'est pas
    // explicitement masquee.
    _isViewEnabled(configKey) {
      if (configKey === "show_favorites") {
        var favs = this._config.favorite_channels;
        return this._config[configKey] !== false && !!(favs && favs.length);
      }
      return this._config[configKey] !== false;
    }

    _enabledViews() {
      var self = this;
      return VIEW_DEFS.filter(function (def) {
        return self._isViewEnabled(def[2]);
      }).map(function (def) { return def[0]; });
    }

    // Vue de depart / repli : la premiere vue encore activee, ou "carousel"
    // si l'utilisateur a (par erreur ou volontairement) tout masque - on
    // prefere toujours afficher quelque chose plutot qu'une carte vide.
    _firstEnabledView() {
      var enabled = this._enabledViews();
      return enabled.length ? enabled[0] : "carousel";
    }

    _ensureDom() {
      if (this._built) return;
      this.innerHTML = "";
      var self = this;

      var style = document.createElement("style");
      style.textContent = STYLE;
      this.appendChild(style);

      var card = document.createElement("ha-card");
      this.appendChild(card);

      var header = document.createElement("div");
      header.className = "header";

      var actions = document.createElement("div");
      actions.className = "header-actions";

      // 3 boutons fixes (un par vue, cf VIEW_DEFS) plutot que 2 boutons a
      // bascule : chacun mene directement a sa vue, et _updateHeaderButtons()
      // se charge de les masquer/marquer actif selon la config et la vue
      // courante. Reference stockee dans this._els sous <cle>+"Link".
      var viewLinks = {};
      VIEW_DEFS.forEach(function (def) {
        var viewKey = def[0], label = def[1];
        var link = document.createElement("button");
        link.type = "button";
        link.className = "header-guide-link";
        link.textContent = label;
        link.addEventListener("click", function () {
          self._view = viewKey;
          self._updateHeaderButtons();
          self._renderBody();
        });
        actions.appendChild(link);
        viewLinks[viewKey] = link;
      });

      header.appendChild(actions);
      card.appendChild(header);

      var body = document.createElement("div");
      body.className = "body";
      card.appendChild(body);

      var guideRoot = document.createElement("div");
      guideRoot.className = "guide-root";
      guideRoot.hidden = true;
      card.appendChild(guideRoot);

      var filmsRoot = document.createElement("div");
      filmsRoot.className = "films-root";
      filmsRoot.hidden = true;
      card.appendChild(filmsRoot);

      var overlay = document.createElement("div");
      overlay.className = "overlay";
      overlay.hidden = true;
      overlay.innerHTML =
        "<div class=\"modal\">" +
        "<button class=\"close\" aria-label=\"Fermer\">&times;</button>" +
        "<img class=\"modal-icon\" hidden>" +
        "<h3 class=\"modal-title\"></h3>" +
        "<div class=\"modal-subtitle\" hidden></div>" +
        "<div class=\"modal-meta\"></div>" +
        "<div class=\"modal-rating\" hidden></div>" +
        "<div class=\"modal-desc\"></div>" +
        "<a class=\"modal-tmdb-link\" hidden target=\"_blank\" rel=\"noopener noreferrer\">Voir la fiche TMDB</a>" +
        "<div class=\"modal-notify-row\" hidden>" +
        "<span class=\"modal-notify-label\">Me notifier avant :</span>" +
        "<select class=\"modal-notify-profile\" hidden></select>" +
        "<button type=\"button\" class=\"modal-notify-btn\" data-minutes=\"5\">5 min</button>" +
        "<button type=\"button\" class=\"modal-notify-btn\" data-minutes=\"10\">10 min</button>" +
        "<button type=\"button\" class=\"modal-notify-btn\" data-minutes=\"15\">15 min</button>" +
        "<button type=\"button\" class=\"modal-notify-cancel-btn\" hidden>Annuler le rappel</button>" +
        "<span class=\"modal-notify-status\"></span>" +
        "</div>" +
        "</div>";
      this.appendChild(overlay);

      overlay.addEventListener("click", function (e) {
        if (e.target === overlay) self._closeModal();
      });
      overlay.querySelector(".close").addEventListener("click", function () {
        self._closeModal();
      });

      this._els = {
        header: header,
        viewLinks: viewLinks,
        body: body,
        guideRoot: guideRoot,
        filmsRoot: filmsRoot,
        overlay: overlay,
        modalIcon: overlay.querySelector(".modal-icon"),
        modalTitle: overlay.querySelector(".modal-title"),
        modalSubtitle: overlay.querySelector(".modal-subtitle"),
        modalMeta: overlay.querySelector(".modal-meta"),
        modalRating: overlay.querySelector(".modal-rating"),
        modalDesc: overlay.querySelector(".modal-desc"),
        modalTmdbLink: overlay.querySelector(".modal-tmdb-link"),
        modalNotifyRow: overlay.querySelector(".modal-notify-row"),
        modalNotifyBtns: overlay.querySelectorAll(".modal-notify-btn"),
        modalNotifyCancelBtn: overlay.querySelector(".modal-notify-cancel-btn"),
        modalNotifyStatus: overlay.querySelector(".modal-notify-status"),
        modalNotifyProfile: overlay.querySelector(".modal-notify-profile")
      };
      this._built = true;
      this._activeReminders = {};
      this._els.modalNotifyRow.addEventListener("click", function (e) {
        var scheduleBtn = e.target.closest(".modal-notify-btn");
        if (scheduleBtn && self._modalProg) {
          self._scheduleReminder(parseInt(scheduleBtn.dataset.minutes, 10));
          return;
        }
        var cancelBtn = e.target.closest(".modal-notify-cancel-btn");
        if (cancelBtn && self._modalProg) {
          self._cancelReminder();
        }
      });
      this._els.modalNotifyProfile.addEventListener("change", function () {
        self._modalProfile = self._els.modalNotifyProfile.value || null;
        self._refreshReminderStatus();
      });
    }

    _updateHeaderButtons() {
      var self = this;
      var enabled = this._enabledViews();
      // Inutile d'afficher des boutons de navigation s'il n'y a qu'une seule
      // vue activee (rien vers quoi basculer) : la carte se comporte alors
      // comme avant l'ajout de cette fonctionnalite (aucun bouton visible).
      var showButtons = enabled.length > 1;
      VIEW_DEFS.forEach(function (def) {
        var viewKey = def[0];
        var link = self._els.viewLinks[viewKey];
        if (!link) return;
        var isEnabled = enabled.indexOf(viewKey) !== -1;
        link.hidden = !showButtons || !isEnabled;
        link.classList.toggle("active", self._view === viewKey);
      });
    }

    _render() {
      this._ensureDom();
      var els = this._els;

      if (!this._hass) {
        els.body.innerHTML = "";
        return;
      }

      // Si la vue courante vient d'etre masquee (changement de config en
      // direct dans l'editeur, ex: decocher "Afficher le Guide TV" pendant
      // qu'il est ouvert), on bascule vers la premiere vue encore activee
      // plutot que de laisser la carte affichee sur une vue desormais cachee.
      if (this._enabledViews().indexOf(this._view) === -1) {
        this._view = this._firstEnabledView();
      }
      this._updateHeaderButtons();

      var dataSig = this._computeDataSig();
      if (this._dataSig !== dataSig) {
        this._dataSig = dataSig;
        if (this._guideBuilt) {
          this._guideCache = {};
          if (this._view === "guide") {
            this._goToDate(this._guideDate);
          }
        }
        if (this._filmsBuilt) {
          this._filmsCache = {};
          if (this._view === "topfilms") {
            this._goToFilmsDate(this._filmsDate);
          }
        }
      }

      this._renderBody();
    }

    _computeDataSig() {
      var hass = this._hass;
      var ids = this._resolveEntities();
      return ids.map(function (id) {
        var st = hass.states[id];
        return id + ":" + (st ? st.last_changed + ":" + JSON.stringify(st.attributes) : "");
      }).join("|");
    }

    _renderBody() {
      var els = this._els;
      els.body.hidden = this._view !== "carousel" && this._view !== "favorites";
      els.guideRoot.hidden = this._view !== "guide";
      els.filmsRoot.hidden = this._view !== "topfilms";

      if (this._view === "guide") {
        this._ensureGuideBuilt();
      } else if (this._view === "topfilms") {
        this._ensureFilmsBuilt();
      } else {
        this._renderCarousel();
      }
    }

    _renderCarousel() {
      var hass = this._hass;
      var els = this._els;
      var favoritesOnly = this._view === "favorites";

      var carIds = this._resolveEntities(favoritesOnly);
      var carSig = favoritesOnly + "|" + carIds.map(function (id) {
        var st = hass.states[id];
        return id + ":" + (st ? st.last_changed + ":" + JSON.stringify(st.attributes) : "");
      }).join("|");
      if (this._carouselSig === carSig && els.body.children.length) {
        return;
      }
      this._carouselSig = carSig;

      var previousScroll = Array.prototype.map.call(
        els.body.querySelectorAll(".carousel"),
        function (c) { return c.scrollLeft; }
      );

      els.body.innerHTML = "";

      var entities = this._resolveEntities(favoritesOnly);
      var self = this;

      var favorites = this._config.favorite_channels;
      var favSet = null;
      if (favorites && favorites.length) {
        favSet = {};
        favorites.forEach(function (cid) { favSet[cid] = true; });
      }

      var activeSlotDefs = SLOT_DEFS.filter(function (def) {
        var key = def[0];
        if (key === "current" && self._config.show_current === false) return false;
        if (key === "next" && self._config.show_next === false) return false;
        if (key === "prime_time" && self._config.show_prime_time === false) return false;
        if (key === "second_part" && self._config.show_second_part === false) return false;
        return true;
      });

      // Rangees "En ce moment" et "A suivre" solidaires au defilement : la
      // meme colonne (index de chaine) doit rester alignee entre les deux
      // rangees quand on swipe/clique les fleches sur l'une ou l'autre.
      var syncCarousels = {};

      activeSlotDefs.forEach(function (def, index) {
        var slotKey = def[0], sectionTitle = def[1], colorClass = def[2];

        var section = document.createElement("div");
        section.className = "slot-section";

        var titleEl = document.createElement("div");
        titleEl.className = "slot-title-header";
        var icon = document.createElement("span");
        icon.className = "slot-title-icon " + colorClass;
        titleEl.appendChild(icon);
        titleEl.appendChild(document.createTextNode(sectionTitle));
        section.appendChild(titleEl);

        var carousel = document.createElement("div");
        carousel.className = "carousel";
        carousel.id = "slider";
        entities.forEach(function (entityId) {
          var attrs = hass.states[entityId].attributes || {};
          var channelLabel = attrs.channel_name || entityId;
          var channelIcon = attrs.channel_icon || null;
          var prog = attrs[slotKey];
          var isFavorite = !!(favSet && attrs.channel_id && favSet[attrs.channel_id]);
          var card = self._buildPosterCard(channelLabel, slotKey, prog, channelIcon, isFavorite, attrs.channel_id);
          carousel.appendChild(card);
        });

        section.appendChild(self._buildCarouselWrap(carousel));
        els.body.appendChild(section);

        if (previousScroll[index]) {
          carousel.scrollLeft = previousScroll[index];
        }

        if (slotKey === "current" || slotKey === "next") {
          syncCarousels[slotKey] = carousel;
        }
      });

      if (syncCarousels.current && syncCarousels.next) {
        this._linkCarouselScroll(syncCarousels.current, syncCarousels.next);
      }
    }

    // Synchronise le defilement horizontal de deux carrousels (En ce moment
    // / A suivre) pour que la meme chaine reste alignee verticalement entre
    // les deux rangees, quel que soit le cote swipe/clique. Le garde-fou
    // "syncing" evite la boucle infinie provoquee par le mirroring mutuel
    // (le scroll programmatique de l'un declenche son propre evenement
    // "scroll", qui sans garde relancerait un mirroring vers l'autre, etc).
    _linkCarouselScroll(a, b) {
      var syncing = false;
      function mirror(from, to) {
        if (syncing) return;
        syncing = true;
        to.scrollTo({ left: from.scrollLeft, behavior: "instant" });
        syncing = false;
      }
      a.addEventListener("scroll", function () { mirror(a, b); });
      b.addEventListener("scroll", function () { mirror(b, a); });
    }

    _buildPosterCard(channelLabel, slotKey, prog, channelIcon, isFavorite, channelId) {
      var self = this;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "poster-card";

      var imageWrap = document.createElement("div");
      imageWrap.className = "poster-image-wrap";
      var hideNextPoster = slotKey === "next" && self._config && self._config.hide_next_poster === true;
      if (!hideNextPoster) btn.appendChild(imageWrap);

      if (channelIcon) {
        var badge = document.createElement("img");
        badge.className = "poster-channel-badge";
        badge.src = channelIcon;
        badge.alt = "";
        var zapScripts = (self._config && self._config.zap_channel_scripts) || {};
        var zapScript = channelId ? zapScripts[channelId] : null;
        if (zapScript) {
          badge.classList.add("poster-channel-badge-zap");
          badge.title = "Zapper sur " + channelLabel;
          badge.addEventListener("click", function (ev) {
            ev.stopPropagation();
            if (self._hass) {
              self._hass.callService("script", "turn_on", { entity_id: zapScript });
            }
          });
        }
        imageWrap.appendChild(badge);
      }

      if (isFavorite) {
        var favBadge = document.createElement("div");
        favBadge.className = "poster-favorite-badge";
        favBadge.innerHTML = STAR_ICON;
        imageWrap.appendChild(favBadge);
      }

      if (!prog) {
        btn.disabled = true;
        var empty = document.createElement("div");
        empty.className = "poster-empty-msg";
        empty.textContent = "Pas de programme";
        imageWrap.appendChild(empty);
        return btn;
      }

      var artUrl = prog.poster || prog.icon || null;
      if (artUrl) {
        var img = document.createElement("img");
        img.className = "poster-bg";
        img.src = artUrl;
        img.loading = "lazy";
        img.alt = "";
        if (!prog.poster) {
          img.className = "poster-bg poster-bg--contain";
          var bgFill = document.createElement("div");
          bgFill.className = "poster-bg-fill";
          bgFill.style.backgroundImage = "url(" + JSON.stringify(artUrl) + ")";
          imageWrap.insertBefore(bgFill, imageWrap.firstChild);
        }
        img.addEventListener("error", function () {
          img.remove();
          if (channelIcon) {
            var wm = document.createElement("div");
            wm.className = "poster-watermark";
            var wmImg = document.createElement("img");
            wmImg.src = channelIcon;
            wm.appendChild(wmImg);
            imageWrap.insertBefore(wm, imageWrap.firstChild);
          }
        });
        imageWrap.insertBefore(img, imageWrap.firstChild);
      } else if (channelIcon) {
        var wm2 = document.createElement("div");
        wm2.className = "poster-watermark";
        var wmImg2 = document.createElement("img");
        wmImg2.src = channelIcon;
        wm2.appendChild(wmImg2);
        imageWrap.insertBefore(wm2, imageWrap.firstChild);
      }

      var startFmt = formatTime(prog.start);
      var stopFmt = formatTime(prog.stop);

      if (slotKey === "current") {
        var live = document.createElement("div");
        live.className = "poster-live-badge";
        var dot = document.createElement("span");
        dot.className = "poster-live-dot";
        live.appendChild(dot);
        live.appendChild(document.createTextNode("Direct"));
        imageWrap.appendChild(live);
      }

      var content = document.createElement("div");
      content.className = "poster-content";

      var titleEl = document.createElement("div");
      titleEl.className = "poster-title";
      titleEl.textContent = prog.title || "";
      content.appendChild(titleEl);

      var timeEl = document.createElement("div");
      timeEl.className = "poster-time";
      var metaParts = [];
      if (prog.category) metaParts.push(prog.category);
      metaParts.push(channelLabel);
      metaParts.push((startFmt || "?") + " - " + (stopFmt || "?"));
var progDate = formatProgDate(prog.date);
if (progDate) metaParts.push(progDate);
      timeEl.textContent = metaParts.join(" • ");
      content.appendChild(timeEl);
      btn.appendChild(content);

      if (slotKey === "current") {
        var frac = liveFraction(prog);
        if (frac !== null) {
          var track = document.createElement("div");
          track.className = "poster-progress-track";
          var fill = document.createElement("div");
          fill.className = "poster-progress-fill";
          fill.style.width = (frac * 100).toFixed(1) + "%";
          track.appendChild(fill);
          imageWrap.appendChild(track);
        }
      }

      btn.addEventListener("click", function () {
        self._openModal(channelLabel, prog);
      });

      return btn;
    }

    _buildCarouselWrap(carousel) {
      var wrap = document.createElement("div");
      wrap.className = "carousel-wrap";
      wrap.appendChild(carousel);

      var prevBtn = document.createElement("button");
      prevBtn.type = "button";
      prevBtn.className = "carousel-nav prev";
      prevBtn.setAttribute("aria-label", "Précédent");
      prevBtn.innerHTML = CHEVRON_LEFT;

      var nextBtn = document.createElement("button");
      nextBtn.type = "button";
      nextBtn.className = "carousel-nav next";
      nextBtn.setAttribute("aria-label", "Suivant");
      nextBtn.innerHTML = CHEVRON_RIGHT;

      function updateNav() {
        var maxScroll = carousel.scrollWidth - carousel.clientWidth;
        var canScroll = maxScroll > 4;
        prevBtn.classList.toggle("visible", canScroll && carousel.scrollLeft > 4);
        nextBtn.classList.toggle("visible", canScroll && carousel.scrollLeft < maxScroll - 4);
      }

      prevBtn.addEventListener("click", function () {
        carousel.scrollBy({ left: -carousel.clientWidth, behavior: "smooth" });
      });
      nextBtn.addEventListener("click", function () {
        carousel.scrollBy({ left: carousel.clientWidth, behavior: "smooth" });
      });
      carousel.addEventListener("scroll", updateNav);

      wrap.appendChild(prevBtn);
      wrap.appendChild(nextBtn);

      requestAnimationFrame(updateNav);
      return wrap;
    }

    _ensureGuideBuilt() {
      if (this._guideBuilt) return;
      var hass = this._hass;
      var self = this;
      var entities = this._resolveEntities();
      if (!entities.length) return;

      var root = this._els.guideRoot;
      root.innerHTML = "";

      var search = document.createElement("input");
      search.type = "text";
      search.className = "guide-search";
      search.placeholder = "Rechercher une chaîne";
      root.appendChild(search);

      var daybar = document.createElement("div");
      daybar.className = "guide-daybar";

      var prevBtn = document.createElement("button");
      prevBtn.type = "button";
      prevBtn.className = "guide-day-btn";
      prevBtn.innerHTML = CHEVRON_LEFT;
      prevBtn.setAttribute("aria-label", "Jour précédent");

      var dayLabel = document.createElement("button");
      dayLabel.type = "button";
      dayLabel.className = "guide-day-label";

      var dayInput = document.createElement("input");
      dayInput.type = "date";
      dayInput.className = "guide-day-input";

      var nextBtn = document.createElement("button");
      nextBtn.type = "button";
      nextBtn.className = "guide-day-btn";
      nextBtn.innerHTML = CHEVRON_RIGHT;
      nextBtn.setAttribute("aria-label", "Jour suivant");

      var hourFilter = document.createElement("select");
      hourFilter.className = "guide-hour-filter";
      [
        ["", "Toute la journee"],
        ["0-6", "00h-06h"],
        ["6-12", "06h-12h"],
        ["12-16", "12h-16h"],
        ["16-19", "16h-19h"],
        ["19-21", "19h-21h"],
        ["21-24", "21h-00h"]
      ].forEach(function (opt) {
        var option = document.createElement("option");
        option.value = opt[0];
        option.textContent = opt[1];
        hourFilter.appendChild(option);
      });

      daybar.appendChild(prevBtn);
      daybar.appendChild(dayLabel);
      daybar.appendChild(dayInput);
      daybar.appendChild(nextBtn);
      daybar.appendChild(hourFilter);
      root.appendChild(daybar);

      var genreBar = document.createElement("div");
      genreBar.className = "guide-genre-bar";
      var genreFilter = document.createElement("select");
      genreFilter.className = "guide-genre-filter";
      var defaultGenreOpt = document.createElement("option");
      defaultGenreOpt.value = "";
      defaultGenreOpt.textContent = "Tous les genres";
      genreFilter.appendChild(defaultGenreOpt);
      genreBar.appendChild(genreFilter);
      root.appendChild(genreBar);

      var columns = document.createElement("div");
      columns.className = "guide-columns";
      columns.id = "slider";
      root.appendChild(self._buildCarouselWrap(columns));

      var favorites = self._config.favorite_channels;
      var favSet = null;
      if (favorites && favorites.length) {
        favSet = {};
        favorites.forEach(function (cid) {
          favSet[cid] = true;
        });
      }

      var colRefs = {};
      entities.forEach(function (entityId) {
        var attrs = hass.states[entityId].attributes || {};
        var channelId = attrs.channel_id;
        var label = attrs.channel_name || entityId;
        var icon = attrs.channel_icon || null;
        var rank = channelRank(hass, entityId);

        var col = document.createElement("div");
        col.className = "guide-column";
        col.dataset.search = normalizeSearch(label);

        var colHeader = document.createElement("div");
        colHeader.className = "guide-col-header";

        if (icon) {
          var logoWrap = document.createElement("div");
          logoWrap.className = "guide-col-logo-wrap";
          var logo = document.createElement("img");
          logo.className = "guide-col-logo";
                    logo.src = icon;
                    logo.alt = "";
          var guideZapScripts = (self._config && self._config.zap_channel_scripts) || {};
          var guideZapScript = channelId ? guideZapScripts[channelId] : null;
          if (guideZapScript) {
            logo.classList.add("guide-col-logo-zap");
            logo.title = "Zapper sur " + label;
            logo.addEventListener("click", function (ev) {
              ev.stopPropagation();
              if (self._hass) {
                self._hass.callService("script", "turn_on", { entity_id: guideZapScript });
              }
            });
          }
          logoWrap.appendChild(logo);
          if (favSet && favSet[channelId]) {
            var colFavBadge = document.createElement("div");
            colFavBadge.className = "guide-col-favorite-badge";
            colFavBadge.innerHTML = STAR_ICON;
            logoWrap.appendChild(colFavBadge);
          }
          colHeader.appendChild(logoWrap);
        }

        var meta = document.createElement("div");
        meta.className = "guide-col-meta";

        if (rank < 999) {
          var lcn = document.createElement("div");
          lcn.className = "guide-col-lcn";
          lcn.textContent = String(Math.floor(rank)).padStart(3, "0");
          meta.appendChild(lcn);
        }

        var name = document.createElement("div");
        name.className = "guide-col-name";
        name.textContent = label;
        meta.appendChild(name);

        colHeader.appendChild(meta);
        col.appendChild(colHeader);

        var list = document.createElement("div");
        list.className = "guide-col-list";
        var loading = document.createElement("div");
        loading.className = "guide-loading";
        loading.textContent = "Chargement...";
        list.appendChild(loading);
        col.appendChild(list);

        columns.appendChild(col);
        colRefs[channelId] = { column: col, list: list, label: label, icon: icon };
      });

      this._guideEls = { dayLabel: dayLabel, dayInput: dayInput, search: search, columns: columns, hourFilter: hourFilter, genreFilter: genreFilter };
      this._guideColRefs = colRefs;

      search.addEventListener("input", function () {
        self._applySearch(search.value);
      });
      hourFilter.addEventListener("change", function () {
        self._guideHourFilter = hourFilter.value;
        self._applyFilters();
      });
      genreFilter.addEventListener("change", function () {
        self._guideGenreFilter = genreFilter.value;
        self._applyFilters();
      });
      prevBtn.addEventListener("click", function () {
        self._goToDate(new Date(self._guideDate.getTime() - 86400000));
      });
      nextBtn.addEventListener("click", function () {
        self._goToDate(new Date(self._guideDate.getTime() + 86400000));
      });
      dayLabel.addEventListener("click", function () {
        dayInput.value = isoDateLocal(self._guideDate);
        if (dayInput.showPicker) {
          dayInput.showPicker();
        } else {
          dayInput.focus();
          dayInput.click();
        }
      });
      dayInput.addEventListener("change", function () {
        if (!dayInput.value) return;
        var parts = dayInput.value.split("-");
        var d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
        self._goToDate(d);
      });

      this._guideBuilt = true;
      this._goToDate(this._guideDate);
    }

    _applySearch(query) {
      var norm = normalizeSearch(query);
      var cols = this._guideEls.columns.querySelectorAll(".guide-column");
      cols.forEach(function (col) {
        var match = !norm || col.dataset.search.indexOf(norm) !== -1;
        col.classList.toggle("tntfr-hidden", !match);
      });
    }

    _applyFilters() {
      var hourRange = this._guideHourFilter;
      var hourBounds = hourRange ? hourRange.split("-").map(Number) : null;
      var genre = this._guideGenreFilter;
      var items = this._guideEls.columns.querySelectorAll(".guide-item");
      items.forEach(function (item) {
        var hourOk = true;
        if (hourBounds && item.dataset.hour !== "") {
          var hour = Number(item.dataset.hour);
          hourOk = hour >= hourBounds[0] && hour < hourBounds[1];
        }
        var genreOk = !genre || item.dataset.category === genre;
        item.classList.toggle("tntfr-hidden", !(hourOk && genreOk));
      });
    }

    _goToDate(date) {
      this._guideDate = date;
      this._guideEls.dayLabel.textContent = dayLabelFr(date);
      var dateStr = isoDateLocal(date);
      if (this._guideCache[dateStr]) {
        this._renderGuideDay(dateStr);
      } else {
        this._fetchGuideDay(dateStr);
      }
    }

    _fetchGuideDay(dateStr) {
      var self = this;
      var channelIds = Object.keys(this._guideColRefs);
      channelIds.forEach(function (cid) {
        self._guideColRefs[cid].list.innerHTML = "";
        var loading = document.createElement("div");
        loading.className = "guide-loading";
        loading.textContent = "Chargement...";
        self._guideColRefs[cid].list.appendChild(loading);
      });

      this._hass.connection
        .sendMessagePromise({
          type: "freebox_homexa/tnt_programmes",
          channels: channelIds,
          date: dateStr
        })
        .then(function (resp) {
          self._guideCache[dateStr] = (resp && resp.programmes) || {};
          self._renderGuideDay(dateStr);
        })
        .catch(function (err) {
          console.error("homexa-tnt-card: guide fetch failed", err);
          Object.keys(self._guideColRefs).forEach(function (cid) {
            self._guideColRefs[cid].list.innerHTML = "";
            var msg = document.createElement("div");
            msg.className = "guide-empty";
            msg.textContent = "Erreur de chargement";
            self._guideColRefs[cid].list.appendChild(msg);
          });
        });
    }

    _renderGuideDay(dateStr) {
      var self = this;
      var dayData = this._guideCache[dateStr] || {};
      var categories = {};
      var favorites = this._config.favorite_channels;
      var favSet = null;
      if (favorites && favorites.length) {
        favSet = {};
        favorites.forEach(function (cid) { favSet[cid] = true; });
      }
      Object.keys(this._guideColRefs).forEach(function (channelId) {
        var ref = self._guideColRefs[channelId];
        var progs = dayData[channelId] || [];
        ref.list.innerHTML = "";
        if (!progs.length) {
          var empty = document.createElement("div");
          empty.className = "guide-empty";
          empty.textContent = "Aucun programme";
          ref.list.appendChild(empty);
          return;
        }
        var isFavorite = !!(favSet && favSet[channelId]);
        progs.forEach(function (prog) {
          if (prog.category) categories[prog.category] = true;
          ref.list.appendChild(self._buildGuideItem(prog, ref.label, ref.icon, isFavorite));
        });
      });
      this._updateGenreOptions(Object.keys(categories).sort(function (a, b) {
        return a.localeCompare(b, "fr");
      }));
      self._applyFilters();
    }

    _updateGenreOptions(categories) {
      var select = this._guideEls.genreFilter;
      var current = this._guideGenreFilter;
      select.innerHTML = "";
      var defaultOpt = document.createElement("option");
      defaultOpt.value = "";
      defaultOpt.textContent = "Tous les genres";
      select.appendChild(defaultOpt);
      categories.forEach(function (cat) {
        var opt = document.createElement("option");
        opt.value = cat;
        opt.textContent = cat;
        select.appendChild(opt);
      });
      if (categories.indexOf(current) !== -1) {
        select.value = current;
      } else {
        this._guideGenreFilter = "";
        select.value = "";
      }
    }

    _buildGuideItem(prog, channelLabel, channelIcon, isFavorite) {
      var self = this;
      var item = document.createElement("button");
      item.type = "button";
      item.className = "guide-item";
      item.dataset.hour = prog.start ? String(new Date(prog.start).getHours()) : "";
      item.dataset.category = prog.category || "";
      var live = isProgLive(prog);
      if (live) item.classList.add("is-live");

      var imageWrap = document.createElement("div");
      imageWrap.className = "guide-item-image-wrap";
      item.appendChild(imageWrap);

            var artUrl = prog.poster || prog.icon || channelIcon || null;
      if (artUrl) {
        var img = document.createElement("img");
        img.className = "guide-item-img";
        img.src = artUrl;
        img.loading = "lazy";
        img.alt = "";
        if (!prog.poster) {
          img.className = "guide-item-img guide-item-img--contain";
          var guideBgFill = document.createElement("div");
          guideBgFill.className = "guide-item-bg-fill";
          guideBgFill.style.backgroundImage = "url(" + JSON.stringify(artUrl) + ")";
          imageWrap.insertBefore(guideBgFill, imageWrap.firstChild);
        }
        img.addEventListener("error", function () {
          img.hidden = true;
        });
        imageWrap.appendChild(img);
      }

      if (live) {
        var liveBadge = document.createElement("div");
        liveBadge.className = "guide-item-live-badge";
        var dot = document.createElement("span");
        dot.className = "guide-item-live-dot";
        liveBadge.appendChild(dot);
        liveBadge.appendChild(document.createTextNode("Direct"));
        imageWrap.appendChild(liveBadge);

        var frac = liveFraction(prog);
        if (frac !== null) {
          var track = document.createElement("div");
          track.className = "guide-item-progress-track";
          var fill = document.createElement("div");
          fill.className = "guide-item-progress-fill";
          fill.style.width = (frac * 100).toFixed(1) + "%";
          track.appendChild(fill);
          imageWrap.appendChild(track);
        }
      }

      var body = document.createElement("div");
      body.className = "guide-item-body";

      var titleEl = document.createElement("div");
      titleEl.className = "guide-item-title";
      titleEl.textContent = prog.title || "";
      body.appendChild(titleEl);

      var metaEl = document.createElement("div");
      metaEl.className = "guide-item-meta";
      var metaParts = [];
      if (prog.category) metaParts.push(prog.category);
      metaParts.push(channelLabel);
      metaParts.push((formatTime(prog.start) || "?") + " - " + (formatTime(prog.stop) || "?"));
      metaEl.textContent = metaParts.join(" • ");
      body.appendChild(metaEl);

      item.appendChild(body);
      item.addEventListener("click", function () {
        self._openModal(channelLabel, prog);
      });
      return item;
    }

    _ensureFilmsBuilt() {
      if (this._filmsBuilt) return;
      var self = this;
      var root = this._els.filmsRoot;
      root.innerHTML = "";

      var daybar = document.createElement("div");
      daybar.className = "guide-daybar";

      var prevBtn = document.createElement("button");
      prevBtn.type = "button";
      prevBtn.className = "guide-day-btn";
      prevBtn.innerHTML = CHEVRON_LEFT;
      prevBtn.setAttribute("aria-label", "Jour précédent");

      var dayLabel = document.createElement("button");
      dayLabel.type = "button";
      dayLabel.className = "guide-day-label";

      var dayInput = document.createElement("input");
      dayInput.type = "date";
      dayInput.className = "guide-day-input";

      var nextBtn = document.createElement("button");
      nextBtn.type = "button";
      nextBtn.className = "guide-day-btn";
      nextBtn.innerHTML = CHEVRON_RIGHT;
      nextBtn.setAttribute("aria-label", "Jour suivant");

      daybar.appendChild(prevBtn);
      daybar.appendChild(dayLabel);
      daybar.appendChild(dayInput);
      daybar.appendChild(nextBtn);
      root.appendChild(daybar);

      var list = document.createElement("div");
      list.className = "films-list";
      root.appendChild(list);

      this._filmsEls = { dayLabel: dayLabel, dayInput: dayInput, list: list };

      prevBtn.addEventListener("click", function () {
        self._goToFilmsDate(new Date(self._filmsDate.getTime() - 86400000));
      });
      nextBtn.addEventListener("click", function () {
        self._goToFilmsDate(new Date(self._filmsDate.getTime() + 86400000));
      });
      dayLabel.addEventListener("click", function () {
        dayInput.value = isoDateLocal(self._filmsDate);
        if (dayInput.showPicker) {
          dayInput.showPicker();
        } else {
          dayInput.focus();
          dayInput.click();
        }
      });
      dayInput.addEventListener("change", function () {
        if (!dayInput.value) return;
        var parts = dayInput.value.split("-");
        var d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
        self._goToFilmsDate(d);
      });

      this._filmsBuilt = true;
      this._goToFilmsDate(this._filmsDate);
    }

    _filmsDayLabel(date) {
      var dateStr = isoDateLocal(date);
      var todayStr = isoDateLocal(new Date());
      if (dateStr === todayStr) return "Ce soir";
      var tomorrowStr = isoDateLocal(new Date(Date.now() + 86400000));
      if (dateStr === tomorrowStr) return "Demain";
      return dayLabelFr(date);
    }

    _goToFilmsDate(date) {
      this._filmsDate = date;
      this._filmsEls.dayLabel.textContent = this._filmsDayLabel(date);
      var dateStr = isoDateLocal(date);
      if (this._filmsCache[dateStr]) {
        this._renderFilmsDay(dateStr);
      } else {
        this._fetchFilmsDay(dateStr);
      }
    }

    _fetchFilmsDay(dateStr) {
      var self = this;
      var hass = this._hass;
      var els = this._filmsEls;
      els.list.innerHTML = "";
      var loading = document.createElement("div");
      loading.className = "guide-loading";
      loading.textContent = "Chargement...";
      els.list.appendChild(loading);

      var entities = this._resolveEntities();
      var channelIds = entities
        .map(function (id) { return hass.states[id].attributes.channel_id; })
        .filter(Boolean);

      if (!channelIds.length) {
        els.list.innerHTML = "";
        return;
      }

      this._hass.connection
        .sendMessagePromise({
          type: "freebox_homexa/tnt_programmes",
          channels: channelIds,
          date: dateStr
        })
        .then(function (resp) {
          var programmesByChannel = (resp && resp.programmes) || {};
          self._filmsCache[dateStr] = self._computeTopFilms(programmesByChannel, entities, hass, dateStr);
          self._renderFilmsDay(dateStr);
        })
        .catch(function (err) {
          console.error("homexa-tnt-card: films fetch failed", err);
          els.list.innerHTML = "";
          var msg = document.createElement("div");
          msg.className = "guide-empty";
          msg.textContent = "Erreur de chargement";
          els.list.appendChild(msg);
        });
    }

    _computeTopFilms(programmesByChannel, entities, hass, dateStr) {
      var parts = dateStr.split("-");
      var threshold = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]), 21, 15, 0);

      var films = [];
      entities.forEach(function (entityId) {
        var attrs = hass.states[entityId].attributes || {};
        var cid = attrs.channel_id;
        if (!cid) return;
        var progs = programmesByChannel[cid] || [];
        var pick = pickPrimeTimeProgramme(progs, threshold);
        if (!pick) return;

        var category = pick.category || "";
        var mediaType = pick.tmdb_media_type || "";
        var rating = Number(pick.tmdb_rating || 0);
        if (["film","long m\u00e9trage","long metrage","cin\u00e9ma","cinema"].some((k) => (category || "").toLowerCase().includes(k)) && mediaType === "movie" && rating > 0) {
          films.push({
            title: pick.title,
            channel: attrs.channel_name || cid,
            start: pick.start,
            rating: rating,
            votes: pick.tmdb_votes || 0,
            tmdbId: pick.tmdb_id,
            poster: pick.poster,
            prog: pick
          });
        }
      });

      films.sort(function (a, b) { return b.rating - a.rating; });
      return films.slice(0, 3);
    }

    _renderFilmsDay(dateStr) {
      var self = this;
      var els = this._filmsEls;
      var films = this._filmsCache[dateStr] || [];
      els.list.innerHTML = "";

      if (!films.length) {
        var empty = document.createElement("div");
        empty.className = "guide-empty";
        empty.textContent = "Aucun film noté trouvé pour cette soirée.";
        els.list.appendChild(empty);
        return;
      }

      var medals = ["🥇", "🥈", "🥉"];
      films.forEach(function (film, index) {
        var row = document.createElement("div");
        row.className = "film-row";
        row.setAttribute("role", "button");
        row.tabIndex = 0;
        row.addEventListener("click", function () {
          self._openModal(film.channel, film.prog || {});
        });
        row.addEventListener("keydown", function (e) {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            self._openModal(film.channel, film.prog || {});
          }
        });

        var posterWrap = document.createElement("div");
        posterWrap.className = "film-poster-wrap";
        if (film.poster) {
          var img = document.createElement("img");
          img.className = "film-poster";
          img.src = film.poster;
          img.loading = "lazy";
          img.alt = "";
          posterWrap.appendChild(img);
        }
        if (medals[index]) {
          var medalBadge = document.createElement("div");
          medalBadge.className = "film-medal-badge";
          medalBadge.textContent = medals[index];
          posterWrap.appendChild(medalBadge);
        }
        row.appendChild(posterWrap);

        var info = document.createElement("div");
        info.className = "film-info";

        var titleRow = document.createElement("div");
        titleRow.className = "film-title";
        titleRow.textContent = film.title || "";
        info.appendChild(titleRow);

        var metaRow = document.createElement("div");
        metaRow.className = "film-meta";
        var timeFmt = formatTime(film.start);
        metaRow.textContent = film.channel + " • " + (timeFmt || "?") + " • " + film.rating.toFixed(1) + "/10";
        info.appendChild(metaRow);

        row.appendChild(info);
        els.list.appendChild(row);
      });
    }

    _applyReminderState(activeMinutes) {
      var els = this._els;
      for (var bi = 0; bi < els.modalNotifyBtns.length; bi++) {
        els.modalNotifyBtns[bi].hidden = !!activeMinutes;
      }
      els.modalNotifyCancelBtn.hidden = !activeMinutes;
    }

    _openModal(channelLabel, prog) {
      var els = this._els;
      if (prog.icon) {
        els.modalIcon.src = prog.icon;
        els.modalIcon.hidden = false;
      } else {
        els.modalIcon.hidden = true;
        els.modalIcon.removeAttribute("src");
      }
      els.modalTitle.textContent = prog.title || "";
      if (prog.subtitle) {
        els.modalSubtitle.textContent = prog.subtitle;
        els.modalSubtitle.hidden = false;
      } else {
        els.modalSubtitle.hidden = true;
      }
      var metaParts = [channelLabel];
      var startFmt = formatTime(prog.start);
      var stopFmt = formatTime(prog.stop);
      if (startFmt && stopFmt) metaParts.push(startFmt + " - " + stopFmt);
      if (prog.category) metaParts.push(prog.category);
      if (prog.rating) metaParts.push("CSA : " + prog.rating);
      var progDate = formatProgDate(prog.date);
      if (progDate) metaParts.push("Diffusion d'origine : " + progDate);
      els.modalMeta.textContent = metaParts.join(" • ");

      if (prog.tmdb_rating) {
        var votesTxt = prog.tmdb_votes ? " (" + prog.tmdb_votes + " votes)" : "";
        els.modalRating.textContent = "⭐ " + Number(prog.tmdb_rating).toFixed(1) + "/10" + votesTxt + " — TMDB";
        els.modalRating.hidden = false;
      } else {
        els.modalRating.hidden = true;
      }

      els.modalDesc.textContent = prog.description || "";

      if (prog.tmdb_id) {
        var mediaPath = prog.tmdb_media_type === "tv" ? "tv" : "movie";
        els.modalTmdbLink.href = "https://www.themoviedb.org/" + mediaPath + "/" + prog.tmdb_id;
        els.modalTmdbLink.hidden = false;
      } else {
        els.modalTmdbLink.hidden = true;
        els.modalTmdbLink.removeAttribute("href");
      }

      
      // Un programme deja commence (encore en cours ou totalement termine) ne
      // peut plus recevoir de rappel : isProgLive() ne couvre que le cas "en
      // cours" (0 < frac < 1) et laisse donc passer les programmes deja finis
      // (frac = 1), d'ou l'utilisation d'une comparaison directe sur l'heure
      // de debut pour n'autoriser le rappel que sur un programme a venir.
      var notStarted = !!prog.start && Date.now() < new Date(prog.start).getTime();
      if (notStarted) {
        this._modalProg = { channelLabel: channelLabel, title: prog.title, start: prog.start };
        if (this._reminderProfiles === undefined) {
          this._reminderProfiles = [];
          this._loadReminderProfiles();
        }
        this._modalProfile = (this._reminderProfiles.length > 1) ? this._reminderProfiles[0] : null;
        this._renderReminderProfileSelect();
        els.modalNotifyRow.hidden = false;
        this._refreshReminderStatus();
              } else {
        this._modalProg = null;
        els.modalNotifyRow.hidden = true;
      }
      els.modalNotifyStatus.textContent = "";

      els.overlay.hidden = false;
    }

    _closeModal() {
      this._els.overlay.hidden = true;
    }

    _reminderServiceData(ctx, minutes) {
      var data = {
        channel_name: ctx.channelLabel,
        program_title: ctx.title,
        start_time: ctx.start,
        minutes_before: minutes
      };
      if (this._modalProfile) data.profile_name = this._modalProfile;
      return data;
    }

    _reminderKey() {
      var ctx = this._modalProg;
      if (!ctx) return null;
      return ctx.channelLabel + "|" + ctx.title + "|" + ctx.start + "|" + (this._modalProfile || "");
    }

    _loadReminderProfiles() {
      var self = this;
      if (!this._hass || !this._hass.connection) return;
      this._hass.connection.sendMessagePromise({ type: "freebox_homexa/tnt_reminder_profiles" }).then(function (resp) {
        self._reminderProfiles = (resp && resp.profiles) || [];
        if (self._reminderProfiles.length > 1 && !self._modalProfile) { self._modalProfile = self._reminderProfiles[0]; }
        self._renderReminderProfileSelect();
      }).catch(function () {
        self._reminderProfiles = [];
      });
    }

    _renderReminderProfileSelect() {
      var sel = this._els.modalNotifyProfile;
      var profiles = this._reminderProfiles || [];
      if (profiles.length < 2) {
        sel.hidden = true;
        sel.innerHTML = "";
        return;
      }
      var self = this;
      sel.innerHTML = "";
      profiles.forEach(function (name) {
        var opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        sel.appendChild(opt);
      });
      sel.value = this._modalProfile || profiles[0];
      sel.hidden = false;
    }

    _refreshReminderStatus() {
      var self = this;
      var ctx = this._modalProg;
      if (!ctx || !this._hass) return;
      var key = this._reminderKey();
      this._applyReminderState(this._activeReminders[key]);
      var data = { channel_name: ctx.channelLabel, program_title: ctx.title, start_time: ctx.start };
      if (this._modalProfile) data.profile_name = this._modalProfile;
      this._hass
        .callService("freebox_homexa", "get_reminder_status", data, undefined, false, true)
        .then(function (resp) {
          if (self._reminderKey() !== key) return;
          var scheduled = (resp && resp.response && resp.response.scheduled_minutes) || [];
          var minutes = scheduled.length ? scheduled[0] : null;
          self._activeReminders[key] = minutes;
          self._applyReminderState(minutes);
        })
        .catch(function () {});
    }

    _scheduleReminder(minutes) {
      var self = this;
      var ctx = this._modalProg;
      var els = this._els;
      if (!ctx || !this._hass) return;
      els.modalNotifyStatus.textContent = "Programmation...";
      this._hass.callService("freebox_homexa", "schedule_reminder", this._reminderServiceData(ctx, minutes)).then(function () {
        self._activeReminders[self._reminderKey()] = minutes;
        for (var bi = 0; bi < els.modalNotifyBtns.length; bi++) {
          els.modalNotifyBtns[bi].hidden = true;
        }
        els.modalNotifyCancelBtn.hidden = false;
        els.modalNotifyStatus.textContent = "Rappel programme \u2713";
      }).catch(function (err) {
        var msg = (err && err.message) || "Impossible de programmer ce rappel.";
        els.modalNotifyStatus.textContent = msg;
      });
    }

    _cancelReminder() {
      var self = this;
      var ctx = this._modalProg;
      var els = this._els;
      if (!ctx || !this._hass) return;
      var minutes = this._activeReminders[this._reminderKey()];
      if (!minutes) return;
      els.modalNotifyStatus.textContent = "Annulation...";
      this._hass.callService("freebox_homexa", "cancel_reminder", this._reminderServiceData(ctx, minutes)).then(function () {
        delete self._activeReminders[self._reminderKey()];
        for (var bi = 0; bi < els.modalNotifyBtns.length; bi++) {
          els.modalNotifyBtns[bi].hidden = false;
        }
        els.modalNotifyCancelBtn.hidden = true;
        els.modalNotifyStatus.textContent = "";
      }).catch(function (err) {
        var msg = (err && err.message) || "Impossible d'annuler ce rappel.";
        els.modalNotifyStatus.textContent = msg;
      });
    }

    _showVersionMismatch(backendVersion) {
      const message =
        "Homexa TNT : nouvelle version disponible (carte " +
        CARD_VERSION +
        ", integration " +
        backendVersion +
        "). Rechargez la page pour l'appliquer.";
    
      this.dispatchEvent(
        new CustomEvent("hass-notification", {
          detail: {
            message: message,
            duration: -1,
            dismissable: true,
            action: {
              text: "Recharger",
              action: () => this._handleReload(),
            },
          },
          bubbles: true,
          composed: true,
        })
      );
    }
    
    _handleReload() {
      if ("caches" in window) {
        caches.keys().then((names) => {
          Promise.all(names.map((name) => caches.delete(name))).then(() => {
            window.location.reload();
          });
        });
      } else {
        window.location.reload();
      }
    }

    static getStubConfig() {
      return {};
    }

    static getConfigElement() {
      return document.createElement("homexa-tnt-card-editor");
    }
  }

  class ProgrammeTntFrCardEditor extends HTMLElement {
    setConfig(config) {
      this._config = config || {};
      this._render();
    }

    set hass(hass) {
      var hadHass = !!this._hass;
      this._hass = hass;
      if (!hadHass) {
        this._render();
      }
    }

    connectedCallback() {
      this._render();
      this._checkVersion();
    }

    async _checkVersion() {
      return checkCardBackendVersion(this);
    }

    _showVersionMismatch(backendVersion) {
      const message = "Homexa TNT : nouvelle version disponible (carte " + CARD_VERSION + ", integration " + backendVersion + "). Rechargez la page pour l'appliquer.";
      this.dispatchEvent(
        new CustomEvent("hass-notification", {
          detail: {
            message: message,
            duration: -1,
            dismissable: true,
            action: {
              text: "Recharger",
              action: () => this._handleReload(),
            },
          },
          bubbles: true,
          composed: true,
        })
      );
    }

    _handleReload() {
      if ("caches" in window) {
        caches.keys().then((names) => {
          Promise.all(names.map((name) => caches.delete(name))).then(() => {
            window.location.reload();
          });
        });
      } else {
        window.location.reload();
      }
    }

    _render() {
      if (!this._config) return;
      this.innerHTML = "";
      var self = this;
      var wrap = document.createElement("div");
      wrap.style.padding = "12px 16px";

      function addToggle(key, label) {
        var sw = document.createElement("ha-switch");
        var row = _tntSwitchRow(label, sw, "6px 0");
        sw.checked = self._config[key] !== false;
        sw.addEventListener("change", function (ev) {
          var newConfig = Object.assign({}, self._config);
          newConfig[key] = ev.target.checked;
          self._config = newConfig;
          self.dispatchEvent(new CustomEvent("config-changed", {
            detail: { config: newConfig },
            bubbles: true,
            composed: true
          }));
        });
        row.appendChild(sw);
        wrap.appendChild(row);
      }

      addToggle("show_current", "Afficher « En ce moment »");
      addToggle("show_next", "Afficher « À suivre »");
      addToggle("hide_next_poster", "Masquer les jaquettes de « À suivre » (texte seul)");
      addToggle("show_prime_time", "Afficher la 1re partie de soirée");
      addToggle("show_second_part", "Afficher la 2e partie de soirée");

      var carouselTitle = document.createElement("div");
      carouselTitle.textContent = "Carrousel";
      carouselTitle.style.fontWeight = "600";
      carouselTitle.style.margin = "14px 0 4px";
      wrap.appendChild(carouselTitle);
      
      var colsRow = document.createElement("div");
      colsRow.style.display = "flex";
      colsRow.style.alignItems = "center";
      colsRow.style.gap = "10px";
      colsRow.style.padding = "6px 0";
      var colsLabel = document.createElement("div");
      colsLabel.textContent = "Nombre de jaquettes visibles";
      colsLabel.style.flex = "1";
      var colsInput = document.createElement("input");
      colsInput.type = "number";
      colsInput.style.width = "72px";
      colsInput.style.padding = "6px 8px";
      colsInput.style.borderRadius = "4px";
      colsInput.style.border = "1px solid var(--divider-color, #767676)";
      colsInput.style.background = "var(--card-background-color, #fff)";
      colsInput.style.color = "var(--primary-text-color)";
      colsInput.style.fontFamily = "inherit";
      colsInput.style.fontSize = "14px";
      colsInput.min = "1";
      colsInput.max = "4";
      colsInput.value = String(self._config.columns || 2);
      colsInput.addEventListener("change", function (ev) {
        var v = Math.max(1, Math.min(4, Math.round(Number(ev.target.value)) || 2));
        colsInput.value = String(v);
        var newConfig = Object.assign({}, self._config);
        if (v === 2) {
          delete newConfig.columns;
        } else {
          newConfig.columns = v;
        }
        self._config = newConfig;
        self.dispatchEvent(new CustomEvent("config-changed", {
          detail: { config: newConfig },
          bubbles: true,
          composed: true
        }));
      });
      colsRow.appendChild(colsLabel);
      colsRow.appendChild(colsInput);
      wrap.appendChild(colsRow);
      
      var colsHint = document.createElement("div");
      colsHint.textContent = "Entre 1 et 4 jaquettes affichees simultanement (par defaut : 2).";
      colsHint.style.fontSize = "12px";
      colsHint.style.opacity = "0.7";
      colsHint.style.margin = "-4px 0 10px";
      wrap.appendChild(colsHint);
      
      var viewsTitle = document.createElement("div");
      viewsTitle.textContent = "Vues disponibles";
      viewsTitle.style.fontWeight = "600";
      viewsTitle.style.margin = "14px 0 4px";
      wrap.appendChild(viewsTitle);

      addToggle("show_carousel", "Afficher le carrousel");
      addToggle("show_favorites", "Afficher la vue Favoris");
      if (self._config.show_favorites !== false && !((self._config.favorite_channels || []).length)) {
        var favHint = document.createElement("div");
        favHint.textContent = "Cette vue ne s'affiche sur la carte que si au moins une chaine favorite est cochee ci-dessous.";
        favHint.style.fontSize = "12px";
        favHint.style.opacity = "0.7";
        favHint.style.margin = "-4px 0 10px 52px";
        wrap.appendChild(favHint);
      }
      addToggle("show_guide_tv", "Afficher le Guide TV");
      addToggle("show_top_films", "Afficher le Top films");

      if (self._hass) {
        var hass = self._hass;
        var ids;
        var entities = self._config.entities || null;
        if (entities && entities.length) {
          ids = entities.filter(function (id) { return !!hass.states[id]; });
        } else {
          ids = Object.keys(hass.states).filter(function (id) {
            var st = hass.states[id];
            return id.indexOf("sensor.") === 0 && st.attributes && st.attributes.channel_id && st.attributes.homexa_tnt;
          });
        }
        ids.sort(function (a, b) {
          var ra = channelRank(hass, a);
          var rb = channelRank(hass, b);
          if (ra !== rb) return ra - rb;
          return channelName(hass, a).localeCompare(channelName(hass, b), "fr", { sensitivity: "base" });
        });

        if (ids.length) {
          var favTitle = document.createElement("div");
          favTitle.textContent = "Chaînes favorites (épinglées en premier)";
          favTitle.style.fontWeight = "600";
          favTitle.style.margin = "14px 0 4px";
          wrap.appendChild(favTitle);

          var currentFavorites = self._config.favorite_channels || [];
          var favSet = {};
          currentFavorites.forEach(function (cid) { favSet[cid] = true; });

          // Petit separateur visuel quand la liste (triee par CHANNEL_ORDER,
          // qui place les chaines belges apres les francaises) passe des
          // chaines françaises (.fr) aux chaines belges (.be), pour qu'on
          // distingue les deux groupes sans avoir a deviner a l'oeil.
          var lastCountryGroup = null;
          function countryGroupLabel(cid) {
            if (cid.slice(-3) === ".be") return "Chaînes belges";
            if (cid.slice(-3) === ".fr") return "Chaînes françaises";
            return null;
          }

          ids.forEach(function (id) {
            var attrs = hass.states[id].attributes || {};
            var cid = attrs.channel_id;
            if (!cid) return;

            var group = countryGroupLabel(cid);
            if (group && group !== lastCountryGroup) {
              lastCountryGroup = group;
              var groupHeader = document.createElement("div");
              groupHeader.textContent = group;
              groupHeader.style.fontSize = "12px";
              groupHeader.style.fontWeight = "600";
              groupHeader.style.opacity = "0.65";
              groupHeader.style.margin = "8px 0 2px";
              wrap.appendChild(groupHeader);
            }

            var sw = document.createElement("ha-switch");
            var row = _tntSwitchRow(attrs.channel_name || id, sw, "4px 0");
            sw.checked = !!favSet[cid];
            sw.addEventListener("change", function (ev) {
              var current = (self._config.favorite_channels || []).slice();
              var idx = current.indexOf(cid);
              if (ev.target.checked) {
                if (idx === -1) current.push(cid);
              } else if (idx !== -1) {
                current.splice(idx, 1);
              }
              var newConfig = Object.assign({}, self._config, { favorite_channels: current });
              self._config = newConfig;
              self.dispatchEvent(new CustomEvent("config-changed", {
                detail: { config: newConfig },
                bubbles: true,
                composed: true
              }));
            });
            row.appendChild(sw);
            wrap.appendChild(row);
          });
        }
      }

      this.appendChild(wrap);
    }
  }

  // Garde defensive : si ce script s'execute deux fois dans la meme session
  // (rechargement de carte, re-enregistrement de ressource...), un second
  // appel a customElements.define() pour un tag deja enregistre leve une
  // exception qui interrompt le reste du fichier - empechant potentiellement
  // le second define() de s'executer et provoquant "Custom element doesn't
  // exist: homexa-tnt-card" (voir issues #1 et #5 du depot). On ignore
  // simplement un second enregistrement plutot que de planter.
  if (!customElements.get("homexa-tnt-card-editor")) {
    customElements.define("homexa-tnt-card-editor", ProgrammeTntFrCardEditor);
  }

  if (!customElements.get("homexa-tnt-card")) {
    customElements.define("homexa-tnt-card", ProgrammeTntFrCard);
  }

  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "homexa-tnt-card",
    name: "Homexa TNT",
    description: "Programme TV des chaînes françaises et belges (RTBF) en carrousels horizontaux (en ce moment / à suivre / 1re et 2e partie de soirée, les deux premiers solidaires au défilement), avec chaînes favorites épinglables, un bouton Guide TV (recherche, jour, horaire, genre) et un bouton Top films pour voir le classement des films les mieux notés sur plusieurs jours."
  });
})();
