"""Affiches, notes et votes TMDB pour le guide TNT Freebox Homexa.

Adapted from cyclope205/programme-tnt-fr v3.0.8 (MIT), coordinator.py
(recherche TMDB, nettoyage des titres, cache, lots, reprise après échec).
Différence majeure : uniquement avec la clé TMDB personnelle de
l'utilisateur. Aucune clé par défaut n'est fournie ni utilisée.
Toutes les requêtes passent par la session aiohttp partagée de Home
Assistant (non bloquantes) et tournent en tâche de fond.
"""
from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

TMDB_SEARCH_MOVIE_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_SEARCH_TV_URL = "https://api.themoviedb.org/3/search/tv"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

# Bruit frequent dans les titres du flux XMLTV pour les series : sous-titre
# d'episode entre parentheses, numero de saison, position dans la saison
# (ex: "Candice Renoir (Faute avouee a demi-pardonnee) S5 (1/10)"), et
# marqueur d'annee pour distinguer un reboot (ex: "Magnum *2018" du Magnum
# original des annees 1980). Verifie sur le flux xmltvfr.fr reel : environ
# un quart des titres suivent ce format. On les retire avant d'interroger
# TMDB, car la requete brute (bruitee de mots sans rapport avec le vrai
# titre) degrade nettement la pertinence du moteur de recherche TMDB et
# peut faire disparaitre le bon resultat de la premiere page de reponses.
_EPISODE_SUFFIX_RE = re.compile(
    r"\s*\([^()]*\)\s*S\d{1,2}\s*(?:\(\d+/\d+\)|\(n°\d+\))\s*$", re.IGNORECASE
)
_SEASON_SUFFIX_RE = re.compile(
    r"\s*S\d{1,2}\s*(?:\(\d+/\d+\)|\(n°\d+\))\s*$", re.IGNORECASE
)
# Autre format d'episode rencontre sur le flux (ex: "Zig & Sharko - S04E61",
# "Mr Bean - S04E14") : code saison+episode colle, precede d'un tiret, sans
# parentheses ni fraction.
_DASH_EPISODE_CODE_RE = re.compile(r"\s*-\s*S\d{1,2}E\d{1,3}\s*$", re.IGNORECASE)
# Autre variante rencontree (ex: "Planete chefs - Saison 1") : "Saison"
# ecrit en toutes lettres plutot que "S<n>", sans numero d'episode.
_DASH_SAISON_WORD_RE = re.compile(r"\s*-\s*Saison\s+\d{1,2}\s*$", re.IGNORECASE)
# Repli le plus large, tente en dernier seulement : simple marqueur de
# saison en fin de titre, sans parentheses ni tiret (ex: "90' Enquetes S17",
# "Reporters S1", "Appels d'urgence S22" - tous verifies avec une vraie
# fiche TMDB). Comme il est peu specifique, il n'est essaye que si aucun
# des motifs plus precis ci-dessus n'a matche.
_BARE_SEASON_SUFFIX_RE = re.compile(r"\s+S\d{1,2}\s*$")
# Feuilletons quotidiens de tres longue duree, sans notion de saison :
# double numero d'episode cumulatif en fin de titre (ex: "Amour, gloire et
# beaute (9709) (n°9709)", verifie sur TMDB).
_CUMULATIVE_EPISODE_RE = re.compile(r"\s*\(\d+\)\s*\(n°\d+\)\s*$")
# Sous-titre d'episode descriptif suivi du marqueur "(n°N)", sans marqueur
# de saison entre les deux (ex: "Cuisines des terroirs (La Macedoine du
# Nord) (n°311)" -> "Cuisines des terroirs", "Tom et Jerry Show
# (Chat-acombes) (n°224)" -> "Tom et Jerry Show" - tous verifies avec de
# vraies fiches TMDB). Chevauche partiellement _CUMULATIVE_EPISODE_RE
# (sans-objet ici puisque ce dernier est tente en premier) mais couvre en
# plus les sous-titres non numeriques que celui-ci ne capture pas.
_SUBTITLE_NUMBER_MARKER_RE = re.compile(r"\s*\([^()]*\)\s*\(n°\d+\)\s*$")
# Qualificatif de version en fin de titre, absent de la fiche TMDB (ex:
# "Le bateau (version realisateur)" -> "Le Bateau", "Rencontres du
# troisieme type (Director's Cut)" -> "Rencontres du troisieme type" -
# tous verifies avec une vraie fiche TMDB).
_VERSION_QUALIFIER_RE = re.compile(
    r"\s*\((?:version (?:réalisateur|restaurée|longue|intégrale|non censurée)"
    r"|director'?s cut|extended(?: cut)?|uncut)\)\s*$",
    re.IGNORECASE,
)
_YEAR_MARKER_RE = re.compile(r"\s*\*(\d{4})\b")
# Decoupage d'un programme en plusieurs parties dans le flux XMLTV, sans que
# TMDB ne liste cette subdivision (ex: "Quotidien, deuxieme partie" -> TMDB
# n'a qu'une seule fiche "Quotidien" pour l'emission entiere - verifie en
# direct). On retire ce suffixe pour retrouver le titre de la fiche TMDB.
_PART_SUFFIX_RE = re.compile(
    r"\s*,\s*(?:premi[eè]re|deuxi[eè]me|1[eè]re|2[eè]me)\s+partie\s*$",
    re.IGNORECASE,
)

# De nombreux titres XMLTV omettent l'article de tete que TMDB inclut
# systematiquement (ex: XMLTV "Meilleur Patissier" vs TMDB "Le Meilleur
# Patissier" ; "Voix" vs "La Voix" ; "Grande Librairie" vs "La Grande
# Librairie" - verifie sur des recherches TMDB reelles). On retire cet
# article des DEUX cotes avant comparaison (symetrique, comme pour la
# ponctuation) : la comparaison stricte par prefixe qui suit reste le
# garde-fou contre les faux positifs, ce n'est pas un relachement du
# critere d'acceptation. Meme logique pour l'anglais "the" (ex: XMLTV
# "Big Bang Theory" vs TMDB "The Big Bang Theory" - verifie en direct).
_LEADING_ARTICLE_RE = re.compile(r"^(?:le|la|les|the)\s+|^l'")

# TMDB prefixe certaines emissions "en direct/en continu" (ex: talk-shows
# d'actualite) d'un marqueur "LIVE:" absent du titre XMLTV correspondant
# (verifie sur TMDB : "C dans l'air" -> "LIVE: C dans l'air", avec une
# vraie affiche). Retire uniquement ce marqueur precis en tete, pas le mot
# "live" en general, pour eviter de perturber un titre qui commencerait
# reellement par ce mot.
_LIVE_PREFIX_RE = re.compile(r"^live\s*:\s*", re.IGNORECASE)


class _TmdbTransientError(Exception):
    """Raised for TMDB failures that should be retried, not cached as no-poster.

    Covers auth failures (revoked/invalid API key), rate limiting, and
    server errors - none of these mean "this title has no TMDB match", so
    they must not be cached as such in _tmdb_poster_cache.
    """


# "un"/"une" sont volontairement absents : ce sont des articles francais
# omnipresents (ex: "Un diner presque parfait"), pas seulement des nombres -
# les convertir en "1" corromprait la comparaison de la plupart des titres.
_FR_NUMBER_WORDS = {
    "zero": "0",
    "deux": "2",
    "trois": "3",
    "quatre": "4",
    "cinq": "5",
    "six": "6",
    "sept": "7",
    "huit": "8",
    "neuf": "9",
    "dix": "10",
    "onze": "11",
    "douze": "12",
    "treize": "13",
    "quatorze": "14",
    "quinze": "15",
    "seize": "16",
    "vingt": "20",
    "trente": "30",
    "quarante": "40",
    "cinquante": "50",
    "soixante": "60",
}


@dataclass(frozen=True)
class TmdbMatch:
    """Une correspondance TMDB unique : affiche + donnees de notation.

    Regroupees dans un seul objet (plutot que de faire grossir le cache en
    plusieurs dicts paralleles) pour que _tmdb_poster_cache reste une simple
    map titre -> resultat, comme avant l'ajout de la notation.
    """

    poster: str
    tmdb_id: int | None
    media_type: str | None
    rating: float
    votes: int



TmdbKey = tuple[str, "str | None", "str | None"]


class TmdbResolver:
    """Résout et met en cache les fiches TMDB des programmes XMLTV."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_key: str,
        on_resolved: Callable[[], Awaitable[Any]],
    ) -> None:
        self.hass = hass
        self._tmdb_api_key = api_key
        self._on_resolved = on_resolved
        self._session = async_get_clientsession(hass)
        self._tmdb_poster_cache: dict[TmdbKey, TmdbMatch | None] = {}
        self._tmdb_pending_titles: set[TmdbKey] = set()
        self._tmdb_auth_warned = False
        self._tmdb_failure_counts: dict[TmdbKey, int] = {}
        self._tmdb_retry_after: dict[TmdbKey, Any] = {}

    @staticmethod
    def key(programme: Any) -> TmdbKey:
        return (programme.title, programme.category, getattr(programme, "date", None))

    def get(self, programme: Any) -> TmdbMatch | None:
        return self._tmdb_poster_cache.get(self.key(programme))

    def prune(self, programmes: Iterable[Any]) -> None:
        """Oublie les titres qui ne sont plus dans le flux (évite une croissance mémoire sans fin)."""
        current_keys = {self.key(p) for p in programmes if p is not None and p.title}
        for key in self._tmdb_poster_cache.keys() - current_keys:
            del self._tmdb_poster_cache[key]
        for key in self._tmdb_failure_counts.keys() - current_keys:
            del self._tmdb_failure_counts[key]
        for key in self._tmdb_retry_after.keys() - current_keys:
            del self._tmdb_retry_after[key]

    def schedule(self, programmes: Iterable[Any], now) -> None:
        """Lance en tâche de fond la résolution des nouveaux titres (J+2 d'abord)."""
        near: dict[TmdbKey, str | None] = {}
        far: dict[TmdbKey, str | None] = {}
        near_cutoff = now + timedelta(days=2)
        for programme in programmes:
            if programme is None or not programme.title or programme.stop <= now:
                continue
            cache_key = self.key(programme)
            if (
                cache_key in self._tmdb_poster_cache
                or cache_key in near
                or cache_key in far
                or cache_key in self._tmdb_pending_titles
                or (
                    cache_key in self._tmdb_retry_after
                    and now < self._tmdb_retry_after[cache_key]
                )
            ):
                continue
            if programme.start <= near_cutoff:
                near[cache_key] = cache_key[2]
            else:
                far[cache_key] = cache_key[2]
        if near or far:
            self._tmdb_pending_titles.update(near)
            self._tmdb_pending_titles.update(far)
            self.hass.async_create_background_task(
                self._background_resolve_tmdb_posters_staged(near, far),
                "freebox_homexa_tnt_tmdb",
            )

    async def _background_resolve_tmdb_posters_staged(
        self,
        near_titles: dict[tuple[str, str | None, str | None], str | None],
        far_titles: dict[tuple[str, str | None, str | None], str | None],
    ) -> None:
        """Resolve near-term (today/tomorrow) TMDB posters first, then the rest.

        Splits what used to be a single large batch into two waves so a
        first setup with many channels does not fire hundreds of TMDB
        lookups at once: the near-term wave resolves (and triggers a
        refresh) first, so posters for what is actually about to be shown
        appear quickly, then the remaining days resolve afterward at the
        same bounded concurrency as before. Every title still eventually
        gets resolved - this only changes the order/timing, not the total
        number of lookups.
        """
        if near_titles:
            await self._background_resolve_tmdb_posters(near_titles)
        if far_titles:
            await self._background_resolve_tmdb_posters(far_titles)

    async def _background_resolve_tmdb_posters(
        self, title_categories: dict[tuple[str, str | None, str | None], str | None]
    ) -> None:
        """Resolve TMDB posters in the background, then push a refresh once done.

        Runs outside of _async_update_data's await chain so a large batch of
        new titles (e.g. a whole day's guide on first setup) can never delay
        or cancel config entry setup again.
        """
        try:
            await self._resolve_tmdb_posters(title_categories)
        finally:
            self._tmdb_pending_titles.difference_update(title_categories)
        await self._on_resolved()

    async def _resolve_tmdb_posters(
        self, title_categories: dict[tuple[str, str | None, str | None], str | None]
    ) -> None:
        """Look up a poster on TMDB (film ou serie selon la categorie) pour chaque nouveau titre.

        Runs lookups concurrently (bounded) instead of one at a time, since
        this can now cover a full day's programmes instead of just 3 picks.
        """
        semaphore = asyncio.Semaphore(5)

        async def _resolve_one(title: str, category: str | None, date: str | None) -> None:
            async with semaphore:
                try:
                    match = await self._lookup_tmdb_poster(title, category, date)
                except Exception as err:  # noqa: BLE001
                    # Erreur temporaire (reseau, cle invalide, rate limit...) :
                    # on ne met PAS en cache pour que ce titre soit retente,
                    # avec un delai progressif (_tmdb_retry_after) plutot
                    # qu'a CHAQUE cycle de 5 min indefiniment.
                    key = (title, category, date)
                    fail_count = self._tmdb_failure_counts.get(key, 0) + 1
                    self._tmdb_failure_counts[key] = fail_count
                    backoff_minutes = min(5 * (2 ** min(fail_count - 1, 6)), 240)
                    self._tmdb_retry_after[key] = dt_util.now() + timedelta(
                        minutes=backoff_minutes
                    )
                    _LOGGER.debug(
                        "Recherche TMDB reportee pour %s (erreur temporaire, "
                        "nouvelle tentative dans %s min): %s",
                        title,
                        backoff_minutes,
                        err,
                    )
                    return
                self._tmdb_failure_counts.pop((title, category, date), None)
                self._tmdb_retry_after.pop((title, category, date), None)
                self._tmdb_poster_cache[(title, category, date)] = match

        await asyncio.gather(
            *(
                _resolve_one(title, category, date)
                for (title, category, date) in title_categories
            )
        )

    async def _lookup_tmdb_poster(
        self, title: str, category: str | None = None, date: str | None = None
    ) -> TmdbMatch | None:
        # Formats recurrents (magazine, information, journal, meteo, sport,
        # divertissement, religion, jeu, talk-show, telerealite...) : ces
        # categories n'ont pas d'oeuvre unique de fiction correspondante, donc
        # la recherche TMDB reste limitee a une fiche serie (jamais film) pour
        # eviter le faux positif historiquement documente sur cette garde -
        # ex. "A l origine" (Magazine de societe) matchait a tort avec le
        # film "A l origine" (2009) de Xavier Giannoli. Une recherche cote
        # serie uniquement affiche la jaquette quand une fiche legitime
        # existe (ex. "C a vous", "Arte Journal", "Le 19.45") sans exposer a
        # ce risque, grace aux garde-fous existants (correspondance de titre
        # + jaquette obligatoire).
        tv_format_only = self._is_non_fiction_category(category)
        clean_title, year = self._clean_search_query(title)
        if not year:
            # Repli sur l'annee fournie par le champ <date> du flux XMLTV
            # (quand disponible) : un signal plus fiable et bien plus
            # frequent que le marqueur manuel "*AAAA" dans le titre, pour
            # le meme usage (distinguer un remake/reboot homonyme).
            year = self._extract_year_from_xmltv_date(date)
        if tv_format_only:
            search_order = (TMDB_SEARCH_TV_URL,)
        elif self._is_movie_category(category):
            search_order = (TMDB_SEARCH_MOVIE_URL, TMDB_SEARCH_TV_URL)
        else:
            search_order = (TMDB_SEARCH_TV_URL, TMDB_SEARCH_MOVIE_URL)
        if year:
            # Recherche avec l'annee en priorite quand elle est disponible (issue du
            # marqueur "*AAAA" ou du champ <date> XMLTV) : sur un homonyme (plusieurs
            # films/series portant le meme titre), une recherche sans annee peut
            # retenir le premier resultat qui matche le titre et possede un poster,
            # meme si ce n'est pas la bonne annee (ex: mauvaise fiche "Nikita").
            for url in search_order:
                match = await self._tmdb_search(url, clean_title, year)
                if match:
                    return replace(match, poster=TMDB_IMAGE_BASE_URL + match.poster)
            # Repli sans annee si la recherche filtree n'a rien donne (l'annee XMLTV
            # peut etre legerement decalee, ex: rediffusion, erreur de flux).
            for url in search_order:
                match = await self._tmdb_search(url, clean_title)
                if match:
                    return replace(match, poster=TMDB_IMAGE_BASE_URL + match.poster)
        else:
            for url in search_order:
                match = await self._tmdb_search(url, clean_title)
                if match:
                    return replace(match, poster=TMDB_IMAGE_BASE_URL + match.poster)
        # Dernier repli : une description libre apres une virgule/deux-points
        # (ex: "Nomade des mers, les escales de l'innovation", pas un format
        # d'episode structure donc non couvert par _clean_search_query) peut a
        # elle seule faire retourner zero resultat TMDB. On retente avec
        # uniquement la partie avant, seulement en dernier recours.
        truncated = self._truncate_at_first_separator(clean_title)
        if truncated and truncated != clean_title:
            for url in search_order:
                match = await self._tmdb_search(url, truncated)
                if match:
                    return replace(match, poster=TMDB_IMAGE_BASE_URL + match.poster)
        return None

    @staticmethod
    def _is_movie_category(category: str | None) -> bool:
        """Return True if the XMLTV category explicitly indicates a movie.

        Le flux XMLTV tague systematiquement les films avec "Film" (ou
        variantes), alors que les series n'ont pas toujours de categorie
        "Serie" explicite (parfois seulement un genre comme "Action"). On ne
        bascule donc en recherche film que si la categorie le confirme
        explicitement ; sinon on cherche d'abord cote serie, avec repli
        automatique sur film si la recherche serie ne trouve rien.
        """
        if not category:
            return False
        normalized = category.strip().lower()
        movie_keywords = (
            "film",
            "long m\u00e9trage",
            "long metrage",
            "cin\u00e9ma",
            "cinema",
        )
        return any(keyword in normalized for keyword in movie_keywords)

    @staticmethod
    def _is_non_fiction_category(category: str | None) -> bool:
        """Return True for XMLTV categories where a bare-title TMDB match
        is unreliable and prone to false positives.

        Recurring non-fiction formats (magazine, news, game shows...) are
        not unique fiction works, so a title-only TMDB search can land on
        an unrelated homonymous film or series - ex: "A l origine" (a 2026
        "Magazine de societe" episode) wrongly matched the 2009 film "A
        l origine" by Xavier Giannoli, since the previous logic fell back
        to a Movie search for every non-movie category. These categories
        are skipped entirely rather than falling back to Movie/TV search.
        """
        if not category:
            return False
        normalized = category.strip().lower()
        non_fiction_keywords = (
            "magazine",
            "société",
            "societe",
            "information",
            "journal",
            "m\u00e9t\u00e9o",
            "meteo",
            "sport",
            "divertissement",
            "religion",
            "jeu",
            "talk-show",
            "talk show",
            "t\u00e9l\u00e9r\u00e9alit\u00e9",
            "telerealite",
        )
        return any(keyword in normalized for keyword in non_fiction_keywords)

    async def _tmdb_search(self, url: str, title: str, year: str | None = None) -> TmdbMatch | None:
        params = {
            "api_key": self._tmdb_api_key,
            "query": title,
            "language": "fr-FR",
            "include_adult": "false",
        }
        if year:
            if url == TMDB_SEARCH_TV_URL:
                params["first_air_date_year"] = year
            elif url == TMDB_SEARCH_MOVIE_URL:
                params["primary_release_year"] = year
        async with self._session.get(url, params=params, timeout=10) as resp:
            if resp.status in (401, 403):
                if not self._tmdb_auth_warned:
                    self._tmdb_auth_warned = True
                    _LOGGER.warning(
                        "TMDB a rejete la requete (cle API invalide ou revoquee, code %s) : "
                        "les affiches TMDB resteront indisponibles tant que ce n'est pas "
                        "corrige (Freebox Homexa → Configurer → Guide TNT).",
                        resp.status,
                    )
                raise _TmdbTransientError(f"TMDB auth error {resp.status}")
            if resp.status == 429:
                raise _TmdbTransientError("TMDB rate limited (429)")
            if resp.status >= 500:
                raise _TmdbTransientError(f"TMDB server error {resp.status}")
            if resp.status != 200:
                return None
            data = await resp.json()
        results = data.get("results") or []
        if not results:
            return None
        query_norm = self._normalize_title(title)
        media_type = "movie" if url == TMDB_SEARCH_MOVIE_URL else "tv"
        # TMDB peut lister plusieurs fiches homonymes exactes avec le meme
        # titre (ex: la comedie "Le Prenom" de 2012 vs un drame senegalais
        # de 2023 du meme nom - verifie en direct sur l'API). Prendre la
        # premiere correspondance de titre avec affiche, comme avant, faisait
        # gagner n'importe quelle fiche obscure simplement parce qu'elle
        # arrivait en tete de la reponse TMDB, sans rapport avec sa
        # pertinence reelle. On parcourt donc TOUTES les fiches dont le titre
        # correspond et on retient celle avec le plus de vote_count (le
        # nombre de votes TMDB est un bien meilleur indicateur de "laquelle
        # est le vrai programme diffuse ce soir" que l'ordre de reponse de
        # l'API, qui n'est pas trie par popularite).
        best_result = None
        best_votes = -1
        for result in results:
            candidate = result.get("title") or result.get("name") or ""
            candidate_norm = self._normalize_title(candidate)
            matched = False
            if candidate_norm and self._titles_match(query_norm, candidate_norm):
                matched = True
            else:
                # Repli sur le titre original (non localise) : le titre fr-FR peut
                # diverger du nom XMLTV alors que le titre original correspond.
                original = result.get("original_title") or result.get("original_name") or ""
                original_norm = self._normalize_title(original)
                if (
                    original_norm
                    and original_norm != candidate_norm
                    and self._titles_match(query_norm, original_norm)
                ):
                    matched = True
            if matched and result.get("poster_path"):
                votes = int(result.get("vote_count") or 0)
                if votes > best_votes:
                    best_votes = votes
                    best_result = result
        if best_result:
            return self._build_tmdb_match(best_result, media_type)
        return None

    @staticmethod
    def _build_tmdb_match(result: dict, media_type: str) -> TmdbMatch:
        """Construit un TmdbMatch a partir d'un resultat brut de l'API TMDB.

        Isole la conversion (valeurs par defaut, casts) du reste de
        _tmdb_search pour rester testable sans appel reseau, comme les
        autres methodes statiques de matching de ce module.
        """
        return TmdbMatch(
            poster=result.get("poster_path") or "",
            tmdb_id=result.get("id"),
            media_type=media_type,
            rating=float(result.get("vote_average") or 0),
            votes=int(result.get("vote_count") or 0),
        )

    @staticmethod
    def _extract_year_from_xmltv_date(date: str | None) -> str | None:
        """Extrait l'annee (AAAA) d'un champ <date> XMLTV.

        Le standard XMLTV autorise plusieurs granularites pour cet element
        (AAAA, AAAAMM ou AAAAMMJJ) : les 4 premiers chiffres correspondent
        toujours a l'annee quelle que soit la granularite fournie par la
        source.
        """
        if not date:
            return None
        match = re.match(r"(\d{4})", date.strip())
        return match.group(1) if match else None

    @staticmethod
    def _truncate_at_first_separator(title: str) -> str | None:
        """Retourne la partie avant la premiere virgule/deux-points d'un
        titre, seulement s'il y a au moins deux mots avant ce separateur
        (evite de tronquer des titres courts comme "Amour, gloire et
        beaute" ou la virgule fait partie du vrai nom). None si aucun
        separateur pertinent n'est trouve.
        """
        match = re.match(r"^(\S+\s+\S.*?)\s*[,:]\s", title or "")
        return match.group(1) if match else None

    @staticmethod
    def _clean_search_query(title: str) -> tuple[str, str | None]:
        """Retire le bruit episode/saison d'un titre XMLTV avant de le
        soumettre a TMDB (voir les regex ci-dessus pour des exemples reels).
        Retourne (titre_nettoye, annee) : annee (extraite d'un marqueur
        "*AAAA") aide a distinguer un reboot de l'original du meme nom.
        Si aucun motif ne correspond, retourne le titre original inchange -
        aucun effet de bord pour les titres deja propres (films, etc.).
        """
        working = title or ""
        year = None
        year_match = _YEAR_MARKER_RE.search(working)
        if year_match:
            year = year_match.group(1)
            working = _YEAR_MARKER_RE.sub("", working)
        before = working
        working = _EPISODE_SUFFIX_RE.sub("", working)
        if working == before:
            working = _SEASON_SUFFIX_RE.sub("", working)
        if working == before:
            working = _DASH_EPISODE_CODE_RE.sub("", working)
        if working == before:
            working = _DASH_SAISON_WORD_RE.sub("", working)
        if working == before:
            working = _BARE_SEASON_SUFFIX_RE.sub("", working)
        if working == before:
            working = _CUMULATIVE_EPISODE_RE.sub("", working)
        if working == before:
            working = _SUBTITLE_NUMBER_MARKER_RE.sub("", working)
        if working == before:
            working = _VERSION_QUALIFIER_RE.sub("", working)
        if working == before:
            working = _PART_SUFFIX_RE.sub("", working)
        working = working.strip()
        return (working or title or "", year)

    @staticmethod
    def _titles_match(query_norm: str, candidate_norm: str) -> bool:
        """Return True if a normalized TMDB candidate matches a normalized query.

        A prefix match in either direction, but only at a word boundary:
        handles XMLTV titles with episode suffixes (ex: "Koh-Lanta - S29E01"
        matching TMDB's "Koh-Lanta") while rejecting loose full-text matches
        where neither is a prefix of the other (ex: "Meteo" vs "Miss Meteo"),
        and rejecting a prefix that merely shares leading letters with an
        unrelated, longer title - ex: XMLTV "Lucifer" (serie) matchait a
        tort avec le film TMDB "Luciferina" (2018), car "luciferina"
        commence par "lucifer" mais en plein milieu d'un mot, pas a une
        coupure de mot - verifie en direct.
        """

        def _boundary_after(text: str, idx: int) -> bool:
            return idx >= len(text) or not text[idx].isalnum()

        if query_norm == candidate_norm:
            return True
        if query_norm.startswith(candidate_norm) and _boundary_after(
            query_norm, len(candidate_norm)
        ):
            return True
        if candidate_norm.startswith(query_norm) and _boundary_after(
            candidate_norm, len(query_norm)
        ):
            return True
        return False

    @staticmethod
    def _normalize_title(value: str) -> str:
        """Normalise un titre pour comparaison (minuscules, sans accents).

        Utilise pour verifier qu'un resultat TMDB correspond vraiment au
        titre recherche avant d'accepter son affiche, plutot que de
        prendre le premier resultat les yeux fermes : une recherche
        plein texte comme "Meteo" matchait a tort la serie "Miss Meteo"
        alors que le bulletin meteo generique n'a pas de fiche TMDB.
        """
        value = _LIVE_PREFIX_RE.sub("", value or "")
        # "&" et "et" sont utilises indifferemment d'une source a l'autre
        # pour le meme titre, dans les deux sens (ex: XMLTV "Superman et
        # Loïs" vs TMDB "Superman & Loïs" ; XMLTV "Tom & Jerry et le
        # haricot geant" vs TMDB "Tom et Jerry et le haricot geant" -
        # verifies avec de vraies fiches TMDB). On unifie vers "et" des
        # les deux cotes (meme normalisation, donc pas de faux positif).
        value = (value or "").replace("&", " et ")
        # TMDB utilise parfois l'apostrophe courbe typographique (’)
        # la ou XMLTV utilise l'apostrophe droite ASCII (ex: TMDB "Le
        # combat d’Alice" vs XMLTV "Le combat d'Alice" - verifie sur une
        # vraie fiche TMDB). On unifie vers l'apostrophe droite des les
        # deux cotes.
        for curly in ("’", "‘", "‛"):
            value = value.replace(curly, "'")
        # TMDB utilise parfois la ligature "oe"/"ae" (œ/æ) la ou XMLTV ecrit
        # "oe"/"ae" en toutes lettres (ex: TMDB "La Villa des Cœurs Brisés" vs
        # XMLTV "La villa des coeurs brises" - verifie sur une vraie fiche
        # TMDB). NFD ne decompose pas ces ligatures (ce ne sont pas des
        # caracteres combines), donc on les deplie explicitement avant NFD.
        for ligature, expanded in (("œ", "oe"), ("Œ", "OE"), ("æ", "ae"), ("Æ", "AE")):
            value = value.replace(ligature, expanded)
        normalized = unicodedata.normalize("NFD", value or "")
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        normalized = normalized.lower().strip()
        normalized = (
            normalized.replace("dix-sept", "17")
            .replace("dix-huit", "18")
            .replace("dix-neuf", "19")
        )
        # XMLTV et TMDB ne separent pas titre/sous-titre avec la meme
        # ponctuation pour le meme programme (ex: XMLTV "Sisteron : citadelle
        # de tous les defis" vs TMDB "Sisteron, la citadelle de tous les
        # defis" ; "Irish Celtic : le chemin des legendes" vs TMDB "Irish
        # Celtic - Le Chemin des Legendes") : on normalise tous ces
        # separateurs en simple espace pour que la comparaison ne depende pas
        # du signe de ponctuation utilise par chaque source.
        for separator in ("-", ":", ",", ";", "!", "?", ".", "/"):
            normalized = normalized.replace(separator, " ")
        words = [_FR_NUMBER_WORDS.get(word, word) for word in normalized.split()]
        result = " ".join(words)
        return _LEADING_ARTICLE_RE.sub("", result, count=1)
