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
