"""Constants adapted from cyclope205/programme-tnt-fr (MIT)."""
from datetime import time

DOMAIN = "programme_tnt_fr"
XMLTV_URL = "https://xmltvfr.fr/xmltv/xmltv_fr.xml"
CONF_CHANNELS = "channels"
CONF_REMINDER_PROFILES = "reminder_profiles"
UPDATE_INTERVAL_MINUTES = 5
FETCH_MIN_INTERVAL_MINUTES = 60
PRIME_TIME_START = time(21, 15)
LATE_NIGHT_START = time(22, 40)
DAY_RESET = time(5, 0)

TNT_CHANNELS = {
    "TF1.fr": "TF1",
    "France2.fr": "France 2",
    "France3.fr": "France 3",
    "CanalPlus.fr": "Canal+",
    "France5.fr": "France 5",
    "M6.fr": "M6",
    "Arte.fr": "Arte",
    "W9.fr": "W9",
    "TMC.fr": "TMC",
    "NT1.fr": "TFX",
    "LaChaineParlementaire.fr": "LCP",
    "France4.fr": "France 4",
    "BFMTV.fr": "BFM TV",
    "CNews.fr": "CNews",
    "CStar.fr": "CStar",
    "Gulli.fr": "Gulli",
    "T18.fr": "T18",
    "NOVO19.fr": "NOVO19",
    "TF1SeriesFilms.fr": "TF1 Series Films",
    "LEquipe21.fr": "L'Equipe",
    "6ter.fr": "6ter",
    "Numero23.fr": "RMC Story",
    "RMCDecouverte.fr": "RMC Decouverte",
    "Cherie25.fr": "RMC Life",
    "LCI.fr": "LCI",
    "FranceInfo.fr": "franceinfo",
    "ParisPremiere.fr": "Paris Premiere",
    "CanalPlusSport.fr": "Canal+ Sport",
    "CanalPlusCinema.fr": "Canal+ Cinema",
    "PlanetePlus.fr": "Planete+",
}
DEFAULT_CHANNELS = list(TNT_CHANNELS.keys())

# Chaînes belges RTBF et chaînes hors TNT (adapted from cyclope205/programme-tnt-fr v3.0.8, MIT)
RTBF_CHANNELS = {
    "LaUne.be": "La Une",
    "LaDeux.be": "Tipik",
    "LaTrois.be": "La Trois",
}

EXTRA_CHANNELS = {
    "CanalPlusSeries.fr": "Canal+ Series",
    "CanalPlusDocs.fr": "Canal+ Docs",
    "CanalPlusKIDS.fr": "Canal+ Kids",
    "CanalPlusGrandEcran.fr": "Canal+ Grand Ecran",
    "CanalPlusBoxOffice.fr": "Canal+ Box Office",
    "CanalPlusFoot.fr": "Canal+ Foot",
    "CanalPlusSport360.fr": "Canal+ Sport 360",
    "CanalPlusLigue1.fr": "Canal+ Ligue 1",
    "CanalPlusPremierLeague.fr": "Canal+ Premier League",
    "CinePlusPremier.fr": "OCS",
    "CinePlusClassic.fr": "Cine+ Classic",
    "CinePlusClub.fr": "Cine+ Festival",
    "CinePlusEmotion.fr": "Cine+ Emotion",
    "CinePlusFamiz.fr": "Cine+ Family",
    "CinePlusFrisson.fr": "Cine+ Frisson",
    "Eurosport1.fr": "Eurosport 1",
    "Eurosport2.fr": "Eurosport 2",
    "beINSPORTS1.fr": "beIN Sports 1",
    "beINSPORTS2.fr": "beIN Sports 2",
    "beINSPORTS3.fr": "beIN Sports 3",
    "RMCSport1.fr": "RMC Sport 1",
    "RMCSport2.fr": "RMC Sport 2",
    "RMCSport3.fr": "RMC Sport 3",
    "DAZN.fr": "DAZN 1",
    "InfosportPlus.fr": "Infosport+",
    "GolfPlus.fr": "Golf+",
    "ChasseEtPeche.fr": "Chasse et Peche",
    "Equidia.fr": "Equidia",
    "ChevalTV.fr": "Cheval TV",
    "DiscoveryChannel.fr": "Discovery Channel",
    "DiscoveryInvestigation.fr": "Discovery Investigation",
    "DiscoveryScience.fr": "TLC",
    "NatGeoWild.fr": "NatGeoWild",
    "NationalGeographic.fr": "National Geographic",
    "Histoire.fr": "Histoire",
    "TouteHistoire.fr": "Toute l'Histoire",
    "UshuaiaTV.fr": "Ushuaia TV",
    "Animaux.fr": "Animaux",
    "Seasons.fr": "Seasons",
    "DisneyChannel.fr": "Disney Channel",
    "DisneyJunior.fr": "Disney Junior",
    "DisneyXD.fr": "Disney XD",
    "Nickelodeon.fr": "Nickelodeon",
    "NickelodeonJunior.fr": "Nickelodeon Junior",
    "Nickelodeon4Teen.fr": "Nickelodeon Teen",
    "CartoonNetwork.fr": "Cartoon Network",
    "Boomerang.fr": "Boomerang",
    "CanalJ.fr": "Canal J",
    "PIWI.fr": "Piwi+",
    "TIJI.fr": "TiJi",
    "Mangas.fr": "Mangas",
    "TeleToonPlus.fr": "TeleToon+",
    "MTV.fr": "MTV",
    "MCM.fr": "MCM",
    "M6Music.fr": "M6 Music",
    "NRJHits.fr": "NRJ Hits",
    "Mezzo.fr": "Mezzo",
    "ComediePlus.fr": "Comedie+",
    "ComedyCentral.fr": "Comedy Central",
    "CrimeDistrict.fr": "Crime District",
    "WarnerTV.fr": "WarnerTV",
    "Syfy.fr": "Syfy",
    "Euronews.fr": "Euronews",
    "France24.fr": "France 24",
    # Ajouts : 6 chaines thematiques les plus regardees (Mediamat Semestriel Mediametrie, janv-juin 2026)
    "RTL9.fr": "RTL9",
    "TvBreizh.fr": "TV Breizh",
    "PolarPlus.fr": "Polar+",
    "Teva.fr": "Teva",
    "serieclub.fr": "Serie Club",
    "AB1.fr": "AB1",
}

FRANCE_CHANNELS = {**TNT_CHANNELS, **EXTRA_CHANNELS}
ALL_CHANNELS = {**TNT_CHANNELS, **EXTRA_CHANNELS, **RTBF_CHANNELS}

# Options Homexa (Configurer → Guide TNT)
CONF_TNT_CHANNELS = "tnt_channels"
CONF_TNT_CHANNELS_FRANCE = "tnt_channels_france"
CONF_TNT_CHANNELS_BELGIQUE = "tnt_channels_belgique"
# Clé TMDB personnelle : stockée dès maintenant, utilisée pour les affiches.
# Aucune clé par défaut n'est fournie.
CONF_TMDB_API_KEY = "tnt_tmdb_api_key"


def selected_channels(options) -> list[str]:
    """Chaînes suivies d'après les options de l'entrée (30 TNT par défaut)."""
    channels = options.get(CONF_TNT_CHANNELS)
    if not channels:
        return list(DEFAULT_CHANNELS)
    return [c for c in channels if c in ALL_CHANNELS]
