"""Configuratie voor de Muziek-app.

Kopieer dit bestand naar `speakers_config.py` en vul het in. Die kopie is
gitignored, want er staat een Spotify refresh token in, en dat is een sleutel
tot het account. Alleen dit sjabloon hoort in de repo.

    cp tech.weyn.muziek/speakers_config.example.py tech.weyn.muziek/speakers_config.py

Zonder `speakers_config.py` werkt de app gewoon, alleen zonder de playlists uit
het Spotify-account. Wat er dan overblijft zijn de favorieten die in het
Sonos-systeem zelf staan, en die hebben geen login nodig. De knop bovenaan het
lijstscherm wisselt tussen beide.
"""

# --- Spotify --------------------------------------------------------------
#
# De badge haalt alleen de lijst met playlists op. Afspelen doet de Sonos zelf,
# met het Spotify-account dat daar gekoppeld is. De badge stuurt enkel een
# spotify:playlist:-URI door.
#
# Waarom niet gewoon de Spotify-API laten afspelen: Sonos is daar een
# restricted device. De speakers verschijnen niet in GET /v1/me/player/devices
# en er valt dus geen playback naartoe te sturen. Dat is beleid van Spotify.
#
# Zo kom je aan de twee waarden hieronder:
#
#   1. Maak een app op developer.spotify.com/dashboard, met Web API aangevinkt
#      en als redirect URI exact:  http://127.0.0.1:8888/callback
#      Let op: "localhost" wordt sinds 2025 geweigerd, en http mag alleen op
#      een loopback-adres.
#   2. Draai op je computer:  python3 tools/spotify_auth.py auth <client_id>
#      Dat opent de browser, jij logt in, en het script drukt het refresh token
#      af. Dat token verloopt niet, dus dit is een eenmalige oefening.
#
# Nodige scopes doet het script zelf: playlist-read-private en
# playlist-read-collaborative. Premium is hier niet voor nodig; de Sonos-kant
# heeft het wel nodig om Spotify te kunnen spelen.
SPOTIFY_CLIENT_ID = ""
SPOTIFY_REFRESH_TOKEN = ""

# --- Sonos ----------------------------------------------------------------
#
# De badge vindt de speakers zelf met SSDP. Dat werkt op een plat thuisnetwerk,
# maar niet op gastwifi of een netwerk dat multicast tussen clients blokkeert.
# Vul dan hier het IP van een willekeurige speaker in: een enkele speler kent de
# hele topologie en vertelt waar de rest staat.
SONOS_IP = ""

# Hoe lang op SSDP-antwoorden gewacht wordt. Drie seconden is genoeg gebleken
# voor vijf speakers op een gewoon thuisnetwerk. Korter maakt de kans groter dat
# een speaker die net wakker wordt gemist wordt.
DISCOVER_MS = 3000

# Een playlist in willekeurige volgorde starten. Aan is meestal wat je wil bij
# een lijst van tientallen nummers; uit als je albums als playlist bewaart en de
# volgorde bedoeld is.
SHUFFLE = True
