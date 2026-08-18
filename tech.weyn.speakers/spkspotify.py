"""De Spotify-kant: alleen de lijst met playlists ophalen.

Afspelen gebeurt niet hier. Spotify's Web API kan Sonos niet aansturen, want
Sonos is daar een restricted device: de speakers verschijnen niet in
GET /v1/me/player/devices en er valt dus geen playback naartoe te sturen. De
badge haalt hier alleen op wat er te kiezen valt, en geeft de gekozen URI door
aan de Sonos zelf. Zie spksonos.play_spotify.

Auth is PKCE met een refresh token, dus zonder client secret op de badge. Het
refresh token verloopt niet en wordt een keer op een computer gehaald met
tools/spotify_auth.py. Het staat in speakers_config.py, dat gitignored is.
"""

import json
import os

import spksonos
from spksonos import SonosError, ticks_ms, ticks_diff, ticks_add

ACCOUNTS = "accounts.spotify.com"
API = "api.spotify.com"

# /cache bestaat niet op deze badge, ook al noemen de docs het. Zoek een map
# die er wel is of aan te maken valt, en zonder ook maar iets: een cache die
# niet weggeschreven kan worden is geen fout, alleen een trager scherm.
CACHE_MAPPEN = ("/cache", "/data")
CACHE_BESTAND = "muziek_playlists.json"


def cache_pad():
    for d in CACHE_MAPPEN:
        try:
            os.stat(d)
            return d + "/" + CACHE_BESTAND
        except OSError:
            pass
        try:
            os.mkdir(d)
            return d + "/" + CACHE_BESTAND
        except OSError:
            continue
    return None


CACHE = cache_pad()

_token = None
_token_tot = None       # ticks_ms waarop het token verloopt, None is onbekend


class SpotifyError(Exception):
    pass


def _post_form(path, velden):
    body = "&".join("%s=%s" % (k, _quote(str(v))) for k, v in velden.items())
    return body


def _quote(s):
    """urlencode zonder urllib. Alleen wat in tokens en ids kan voorkomen."""
    veilig = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    uit = []
    for c in s:
        if c in veilig:
            uit.append(c)
        else:
            for b in c.encode():
                uit.append("%%%02X" % b)
    return "".join(uit)


async def access_token(client_id, refresh_token, force=False):
    """Een geldig access token, met het vorige hergebruikt tot het verloopt."""
    global _token, _token_tot
    if not client_id or not refresh_token:
        raise SpotifyError("Spotify is niet ingesteld")
    if _token and not force and _token_tot is not None:
        if ticks_diff(_token_tot, ticks_ms()) > 30_000:
            return _token
    body = _post_form("", {"grant_type": "refresh_token",
                           "refresh_token": refresh_token,
                           "client_id": client_id})
    try:
        st, tekst = await spksonos.http(ACCOUNTS, "POST", "/api/token", body,
                               {"Content-Type": "application/x-www-form-urlencoded"},
                               port=443, tls=True, timeout=15)
    except SonosError as e:
        raise SpotifyError(str(e))
    if st != 200:
        boodschap = "Spotify weigert de login"
        try:
            boodschap = json.loads(tekst).get("error_description") or boodschap
        except Exception:
            pass
        raise SpotifyError(boodschap)
    data = json.loads(tekst)
    _token = data.get("access_token")
    seconden = int(data.get("expires_in") or 3600)
    _token_tot = ticks_add(ticks_ms(), seconden * 1000)
    if not _token:
        raise SpotifyError("geen token gekregen")
    return _token


async def playlists(client_id, refresh_token, maximum=60):
    """Naam en URI van de playlists van de gebruiker.

    Alleen naam en uri worden bijgehouden; de rest van het antwoord is beeldjes
    en eigenaars die de badge toch niet toont."""
    token = await access_token(client_id, refresh_token)
    uit = []
    pad = "/v1/me/playlists?limit=50"
    while pad and len(uit) < maximum:
        st, tekst = await spksonos.http(API, "GET", pad,
                               headers={"Authorization": "Bearer " + token},
                               port=443, tls=True, timeout=20)
        if st == 401:
            token = await access_token(client_id, refresh_token, force=True)
            continue
        if st != 200:
            raise SpotifyError("Spotify antwoordde %d" % st)
        data = json.loads(tekst)
        for item in data.get("items") or []:
            if not item:
                continue
            uit.append({"naam": item.get("name") or "?",
                        "uri": item.get("uri") or "",
                        "aantal": ((item.get("tracks") or {}).get("total")) or 0})
        volgende = data.get("next")
        if volgende and volgende.startswith("https://" + API):
            pad = volgende[len("https://" + API):]
        else:
            pad = None
    return uit


def cache_lezen():
    if not CACHE:
        return []
    try:
        with open(CACHE) as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def cache_schrijven(items):
    """Zodat het scherm gevuld is voor het netwerk antwoordt. Mislukken mag:
    de map mag door het OS opgeruimd worden en dan halen we het gewoon opnieuw."""
    if not CACHE:
        return False
    try:
        with open(CACHE, "w") as f:
            json.dump(items, f)
        return True
    except Exception as e:
        print("speakers: playlistcache niet geschreven:", e)
        return False
