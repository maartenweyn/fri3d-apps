"""Gedeelde toestand tussen de vier schermen.

De schermen tekenen alleen; het netwerk gebeurt hier, in taken. Elk scherm
kijkt per frame naar `seq` en tekent alleen opnieuw als dat getal veranderd is.
Dezelfde opzet als Berichtjes, om dezelfde reden: een coroutine kan niet in de
UI grijpen, en een UI die op elk frame LVGL-tekst herschrijft flikkert.
"""

import asyncio
import time

import spksonos
import spkspotify

PREFS_APP_ID = "tech.weyn.speakers"

try:
    from mpos import SharedPreferences
except Exception:                                    # pragma: no cover
    try:
        from mpos.config import SharedPreferences
    except Exception:
        SharedPreferences = None

# speakers_config.py is gitignored, want daar staan de Spotify-sleutels in.
# Zonder dat bestand werkt de app nog steeds, alleen met de Sonos-favorieten
# in plaats van de playlists uit het account.
try:
    import speakers_config as _cfg
except Exception:                                    # pragma: no cover
    _cfg = None


def _conf(naam, standaard):
    return getattr(_cfg, naam, standaard) if _cfg else standaard


SPOTIFY_CLIENT_ID = _conf("SPOTIFY_CLIENT_ID", "")
SPOTIFY_REFRESH_TOKEN = _conf("SPOTIFY_REFRESH_TOKEN", "")
SONOS_IP = _conf("SONOS_IP", "")
SHUFFLE = bool(_conf("SHUFFLE", True))
DISCOVER_MS = int(_conf("DISCOVER_MS", 3000))

# --- toestand -------------------------------------------------------------

seq = 0                  # hoger na elke wijziging; de schermen kijken hiernaar
status = ""              # eenregelige boodschap onderaan het scherm
bezig = 0                # aantal lopende taken

zones = []               # [{uid, ip, naam, baas, coordinator}]
zone = None              # de gekozen zone, een van bovenstaande dicts

speler = {"staat": "", "titel": "", "artiest": "", "volume": 0}
lijsten = []             # [{naam, uri, aantal}] van Spotify
favorieten = []          # [{titel, res, resmd}] van Sonos
wekkers = []             # [{id, tijd, aan, herhaling, bron, volume, _ruw}]

spotify_klaar = False    # is de playlistlijst ooit opgehaald deze sessie
_sn = 0                  # servicenummer van Spotify, zie zorg_voor_sn


def _wijzig(boodschap=None):
    global seq, status
    seq += 1
    if boodschap is not None:
        status = boodschap


def spotify_ingesteld():
    return bool(SPOTIFY_CLIENT_ID and SPOTIFY_REFRESH_TOKEN)


# --- taken ----------------------------------------------------------------

def taak(coro, klaar=None):
    """Start een coroutine en vang alles op wat eruit komt.

    Een taak die stilletjes sterft is op een badge onzichtbaar: er is geen
    console open. Elke fout eindigt daarom in de statusregel."""
    async def wikkel():
        global bezig
        bezig += 1
        _wijzig()
        try:
            uitkomst = await coro
            if klaar is not None:
                klaar(uitkomst)
        except spksonos.SonosError as e:
            _wijzig(str(e))
        except spkspotify.SpotifyError as e:
            _wijzig(str(e))
        except Exception as e:                        # pragma: no cover
            print("speakers: taak mislukt:", e)
            _wijzig("er ging iets mis")
        finally:
            bezig -= 1
            _wijzig()
    try:
        return asyncio.create_task(wikkel())
    except Exception:                                 # pragma: no cover
        print("speakers: geen asyncio-loop, taak niet gestart")
        return None


# --- voorkeuren -----------------------------------------------------------

# Nieuwste eerst. De app heette be.weyn.muziek, vanmiddag kort
# tech.weyn.muziek, en heet nu tech.weyn.speakers: wat hij aanstuurt zijn de
# boxen, en muziek is maar een van de dingen die eruit komt.
LEGACY_PREFS_APP_IDS = ("tech.weyn.muziek", "be.weyn.muziek")


def prefs_migreren():
    """Overnemen wat er onder de oude app-id stond, een keer.

    Anders is de gekozen box na de hernoeming weg, en dat merk je pas als de
    muziek in de verkeerde kamer begint.
    """
    if SharedPreferences is None:
        return False
    try:
        p = SharedPreferences(PREFS_APP_ID)
        if p.get_string("zone_uid", ""):
            return False
        for oud_id in LEGACY_PREFS_APP_IDS:
            oud = SharedPreferences(oud_id)
            e = None
            for key in ("zone_uid", "zone_ip", "zone_naam"):
                waarde = oud.get_string(key, "")
                if not waarde:
                    continue
                if e is None:
                    e = p.edit()
                e.put_string(key, waarde)
            sn = oud.get_int("spotify_sn", 0)
            if sn:
                if e is None:
                    e = p.edit()
                e.put_int("spotify_sn", sn)
            if e is None:
                continue
            e.commit()
            print("speakers: voorkeuren overgenomen van", oud_id)
            return True
        return False
    except Exception as exc:
        print("speakers: oude voorkeuren niet overgenomen:", exc)
        return False


prefs_migreren()


def prefs_lezen():
    if SharedPreferences is None:
        return {}
    try:
        p = SharedPreferences(PREFS_APP_ID)
        return {"uid": p.get_string("zone_uid", ""),
                "ip": p.get_string("zone_ip", ""),
                "naam": p.get_string("zone_naam", ""),
                "sn": p.get_int("spotify_sn", 0),
                # Welk Spotify-account van het huishouden deze badge gebruikt.
                # "0" is wat Sonos als eerste noemt, en was hiervoor de enige
                # mogelijkheid.
                "account": p.get_string("spotify_account", "0")}
    except Exception as e:
        print("speakers: voorkeuren niet gelezen:", e)
        return {}


def spotify_account():
    return (prefs_lezen() or {}).get("account") or "0"


def kies_spotify_account(serial):
    """Welk account van het gezin deze badge gebruikt. Per badge dus anders."""
    if SharedPreferences is None:
        return False
    try:
        SharedPreferences(PREFS_APP_ID).edit().put_string(
            "spotify_account", str(serial)).commit()
        return True
    except Exception as e:
        print("speakers: account niet bewaard:", e)
        return False


def prefs_schrijven(z):
    if SharedPreferences is None or not z:
        return False
    try:
        e = SharedPreferences(PREFS_APP_ID).edit()
        e.put_string("zone_uid", z.get("uid") or "")
        e.put_string("zone_ip", z.get("ip") or "")
        e.put_string("zone_naam", z.get("naam") or "")
        e.commit()
        return True
    except Exception as e:
        print("speakers: voorkeuren niet bewaard:", e)
        return False


def prefs_sn_schrijven(sn):
    if SharedPreferences is None or not sn:
        return False
    try:
        SharedPreferences(PREFS_APP_ID).edit().put_int("spotify_sn", int(sn)).commit()
        return True
    except Exception as e:
        print("speakers: servicenummer niet bewaard:", e)
        return False


async def zorg_voor_sn(ip):
    """Het Spotify-servicenummer, een keer opgevraagd en dan onthouden.

    `ListAvailableServices` geeft de hele cataloog van Sonos terug, honderd
    diensten lang, en dat kostte gemeten 3,5 van de 7,4 seconden die het
    starten van een playlist duurde. Het nummer hangt aan het huishouden en
    verandert niet, dus het hoort in de voorkeuren en niet in elke start."""
    global _sn
    if _sn:
        return _sn
    bewaard = prefs_lezen().get("sn") or 0
    if bewaard:
        _sn = int(bewaard)
        return _sn
    _sn = await spksonos.spotify_sn(ip)
    prefs_sn_schrijven(_sn)
    return _sn


# --- zones ----------------------------------------------------------------

async def zoek_zones():
    """SSDP, dan een enkele topologie-call. Valt terug op het vaste IP uit de
    config, want op netwerken die multicast blokkeren vindt SSDP niets."""
    global zones
    gevonden = {}
    try:
        gevonden = await spksonos.discover(DISCOVER_MS)
    except spksonos.SonosError:
        pass
    ips = sorted(gevonden)
    if SONOS_IP and SONOS_IP not in ips:
        ips.insert(0, SONOS_IP)
    if not ips:
        zones = []
        _wijzig("geen Sonos gevonden")
        return []
    laatste = None
    for ip in ips:
        try:
            gevraagd = await spksonos.zones(ip)
            if gevraagd:
                zones = gevraagd
                _wijzig("%d boxen" % len(zones))
                _herstel_keuze()
                return zones
        except spksonos.SonosError as e:
            laatste = e
    zones = []
    _wijzig(str(laatste) if laatste else "geen antwoord")
    return []


def _herstel_keuze():
    """De vorige keuze terugvinden, op uid en niet op IP: DHCP verhuist een
    speler, zijn uid verandert nooit."""
    global zone
    bewaard = prefs_lezen()
    if zone is not None:
        for z in zones:
            if z["uid"] == zone["uid"]:
                zone = z
                return
    uid = bewaard.get("uid")
    if uid:
        for z in zones:
            if z["uid"] == uid:
                zone = z
                return
    zone = zones[0] if zones else None


def kies_zone(z):
    global zone, wekkers
    zone = z
    wekkers = []
    prefs_schrijven(z)
    _wijzig("")


def zone_baas():
    """De speler die commando's aanneemt. Een slaaf in een groep weigert Play,
    dus stuur alles naar de baas van zijn groep."""
    if zone is None:
        return None
    if zone.get("baas"):
        return zone
    for z in zones:
        if z["uid"] == zone.get("coordinator"):
            return z
    return zone


# --- speler ---------------------------------------------------------------

async def ververs_speler():
    z = zone_baas()
    if z is None:
        return
    ip = z["ip"]
    staat = await spksonos.state(ip)
    nu = await spksonos.now(ip)
    vol = await spksonos.get_volume(ip)
    speler["staat"] = staat
    speler["titel"] = nu["titel"]
    speler["artiest"] = nu["artiest"]
    speler["volume"] = vol
    _wijzig()


async def wissel_afspelen():
    z = zone_baas()
    if z is None:
        return
    if speler["staat"] == "PLAYING":
        await spksonos.pause(z["ip"])
        speler["staat"] = "PAUSED_PLAYBACK"
    else:
        await spksonos.play(z["ip"])
        speler["staat"] = "PLAYING"
    _wijzig()
    await spksonos.sleep_ms(400)
    await ververs_speler()


async def spring(vooruit):
    z = zone_baas()
    if z is None:
        return
    if vooruit:
        await spksonos.nxt(z["ip"])
    else:
        await spksonos.prev(z["ip"])
    await spksonos.sleep_ms(600)
    await ververs_speler()


async def zet_volume(delta):
    z = zone_baas()
    if z is None:
        return
    nieuw = await spksonos.set_volume(z["ip"], speler["volume"] + delta)
    speler["volume"] = nieuw
    _wijzig()


# --- lijsten --------------------------------------------------------------

async def ververs_lijsten(force=False):
    """Playlists uit het Spotify-account, met de cache als eerste vulling."""
    global lijsten, spotify_klaar
    if not lijsten:
        gecached = spkspotify.cache_lezen()
        if gecached:
            lijsten = gecached
            _wijzig()
    if not spotify_ingesteld():
        _wijzig("Spotify niet ingesteld")
        return lijsten
    if spotify_klaar and not force:
        return lijsten
    verse = await spkspotify.playlists(SPOTIFY_CLIENT_ID, SPOTIFY_REFRESH_TOKEN)
    if verse:
        lijsten = verse
        spotify_klaar = True
        spkspotify.cache_schrijven(verse)
    _wijzig("%d playlists" % len(lijsten))
    return lijsten


async def ververs_favorieten():
    global favorieten
    z = zone_baas()
    if z is None:
        return []
    favorieten = await spksonos.favorites(z["ip"])
    _wijzig("%d favorieten" % len(favorieten))
    return favorieten


async def speel_lijst(uri, titel=""):
    z = zone_baas()
    if z is None:
        return
    _wijzig("bezig met " + titel)
    sn = await zorg_voor_sn(z["ip"])
    aantal = await spksonos.play_spotify(z["ip"], uri, shuffle=SHUFFLE,
                                        titel=titel, speler_uid=z["uid"], sn=sn,
                                        account=spotify_account())
    _wijzig("%s, %d nummers" % (titel, aantal))
    await spksonos.sleep_ms(700)
    await ververs_speler()


def radiozenders():
    """De favorieten die een zender zijn en geen lijst met nummers.

    Sonos bewaart radio en playlists door elkaar in FV:2. Voor een knop op het
    spelerscherm wil je alleen het eerste."""
    return [f for f in favorieten if spksonos.is_stream(f)]


async def speel_favoriet(fav):
    z = zone_baas()
    if z is None:
        return
    _wijzig("bezig met " + fav["titel"])
    await spksonos.play_favorite(z["ip"], fav, speler_uid=z["uid"])
    _wijzig(fav["titel"])
    await spksonos.sleep_ms(700)
    await ververs_speler()


# --- wekkers --------------------------------------------------------------

async def ververs_wekkers():
    global wekkers
    if zone is None:
        return []
    wekkers = await spksonos.alarms(zone["ip"], room_uuid=zone["uid"])
    _wijzig("%d wekkers" % len(wekkers) if wekkers
            else "geen wekkers voor deze box")
    return wekkers


async def zet_wekker(alarm, aan=None, minuten=0):
    if zone is None:
        return
    tijd = spksonos._shift_time(alarm["tijd"], minuten) if minuten else None
    await spksonos.update_alarm(zone["ip"], alarm, aan=aan, tijd=tijd)
    _wijzig("%s %s" % (alarm["tijd"], "aan" if alarm["aan"] else "uit"))


# --- opstarten ------------------------------------------------------------

async def opstarten():
    """Eenmalig per sessie: zones zoeken en de gekozen box uitlezen."""
    if not zones:
        await zoek_zones()
    if zone is not None:
        await ververs_speler()
