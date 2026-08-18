"""Sonos over het lokale netwerk, asynchroon.

Alles hier is coroutine, omdat alles op dezelfde thread als LVGL draait. Een
blokkerende socket bevriest het scherm; `asyncio.open_connection` niet. Gemeten
op de badge: tijdens een call van 129 ms liep de loop gewoon door.

Zes dingen die op hardware zijn tegengekomen en die je niet uit documentatie
haalt. Ze staan hier als commentaar bij de code die ze afvangt:

  1. De ingebouwde `requests` struikelt over Transfer-Encoding: chunked, en
     Sonos gebruikt dat. Vandaar eigen HTTP met een chunk-decoder.
  2. `re.finditer` bestaat niet in MicroPython.
  3. SetPlayMode moet na SetAVTransportURI, anders UPnP 712.
  4. Een tag-regex zonder naamgrens matcht <upnp:album> op <upnp:albumArtURI>.
  5. IP_MULTICAST_TTL kan lwip niet zetten; SSDP werkt toch, want de antwoorden
     komen unicast terug.
  6. device_description.xml is de traagste call van allemaal. GetZoneGroupState
     geeft in een fractie daarvan het hele huishouden.
"""

import asyncio
import re
import socket
import time

# --- compatibiliteit ------------------------------------------------------
# ticks_ms en sleep_ms bestaan alleen in MicroPython. De offline tests draaien
# op gewone Python, dus staan hier vervangers. De echte versies blijven in
# gebruik op de badge: ticks_diff daar is bewust wrap-veilig en dat willen we
# niet weggooien voor een aftrekking die na negen dagen negatief wordt.
try:
    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff
    ticks_add = time.ticks_add
except AttributeError:                                # pragma: no cover
    def ticks_ms():
        return int(time.monotonic() * 1000)

    def ticks_diff(a, b):
        return a - b

    def ticks_add(a, b):
        return a + b

try:
    sleep_ms = asyncio.sleep_ms
except AttributeError:                                # pragma: no cover
    async def sleep_ms(ms):
        await asyncio.sleep(ms / 1000.0)

PORT = 1400

AV = ("/MediaRenderer/AVTransport/Control",
      "urn:schemas-upnp-org:service:AVTransport:1")
RC = ("/MediaRenderer/RenderingControl/Control",
      "urn:schemas-upnp-org:service:RenderingControl:1")
CD = ("/MediaServer/ContentDirectory/Control",
      "urn:schemas-upnp-org:service:ContentDirectory:1")
MS = ("/MusicServices/Control",
      "urn:schemas-upnp-org:service:MusicServices:1")
ZGT = ("/ZoneGroupTopology/Control",
       "urn:schemas-upnp-org:service:ZoneGroupTopology:1")
AC = ("/AlarmClock/Control",
      "urn:schemas-upnp-org:service:AlarmClock:1")

# Het nummer in de cdudn is het service-Id maal 256 plus 7. Gemeten: Spotify
# heeft Id 9 en dus 2311; Spotify US heeft Id 12 en dus 3079. Uitrekenen is
# betrouwbaarder dan 2311 hardcoderen zoals SoCo doet.
SPOTIFY_FALLBACK = 2311

MAGIC = {
    "playlist": ("1006206c", "object.container.playlistContainer"),
    "show":     ("1006206c", "object.container.playlistContainer"),
    "album":    ("1004206c", "object.container.album.musicAlbum"),
    "track":    ("00032020", "object.item.audioItem.musicTrack"),
    "episode":  ("00032020", "object.item.audioItem.musicTrack"),
}
CONTAINERS = ("playlist", "show", "album")


class SonosError(Exception):
    """Iets ging mis in het protocol. De boodschap is voor het scherm."""


# ------------------------------------------------------------------- XML

def esc(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def unesc(t):
    return (t.replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&apos;", "'")
             .replace("&amp;", "&"))


def tag(body, name):
    """Inhoud van de eerste <name>...</name>. De naam moet eindigen op ">" of
    een spatie: zonder die grens matcht "album" ook op <upnp:albumArtURI> en
    krijg je een CDN-URL waar een albumtitel hoort."""
    m = re.search("<(?:[a-zA-Z]+:)?" + name + ">(.*?)</(?:[a-zA-Z]+:)?" + name + ">", body)
    if not m:
        m = re.search("<(?:[a-zA-Z]+:)?" + name + " [^>]*>(.*?)</(?:[a-zA-Z]+:)?" + name + ">", body)
    return unesc(m.group(1)) if m else None


def scan(text, pattern):
    """Alle treffers van een patroon, als lijst van group-tuples.

    `re.finditer` bestaat niet in MicroPython, en `re.findall` evenmin op deze
    build, dus dit is de vervanging. Loopt over een steeds kortere string."""
    uit, pos, pat = [], 0, re.compile(pattern)
    while pos < len(text):
        m = pat.search(text[pos:])
        if not m:
            break
        groepen = []
        i = 1
        while True:
            try:
                groepen.append(m.group(i))
            except Exception:
                break
            i += 1
        uit.append(tuple(groepen))
        heel = m.group(0)
        stap = text[pos:].find(heel)
        if stap < 0:
            break
        pos += stap + max(1, len(heel))
    return uit


def attrs(opening_tag):
    """Attributen uit een openingstag als dict. Waarden blijven XML-geescapet
    zoals ze binnenkwamen, want ze gaan bij UpdateAlarm ongewijzigd terug.

    Met de hand geparst, niet met een regex. Een alarm heeft een
    ProgramMetaData van meer dan duizend tekens, en de re-engine van
    MicroPython backtrackt recursief: `[^"]*` daarover geeft
    RuntimeError: maximum recursion depth exceeded. Op desktop niet, want daar
    is het een andere engine. str.find heeft dat probleem niet.

    Binnen een attribuutwaarde staan alleen geescapete aanhalingstekens
    (`&quot;`), dus een rauwe `="` markeert altijd het begin van een nieuw
    attribuut."""
    uit = {}
    i = 0
    while True:
        gelijk = opening_tag.find('="', i)
        if gelijk < 0:
            return uit
        begin = gelijk
        while begin > 0:
            c = opening_tag[begin - 1]
            if c.isalpha() or c.isdigit() or c == ":" or c == "_" or c == "-":
                begin -= 1
            else:
                break
        eind = opening_tag.find('"', gelijk + 2)
        if eind < 0:
            return uit
        naam = opening_tag[begin:gelijk]
        if naam:
            uit[naam] = opening_tag[gelijk + 2:eind]
        i = eind + 1


# ------------------------------------------------------------------ HTTP

async def http(host, method, path, body=b"", headers=None, port=PORT,
               timeout=10, tls=False):
    """HTTP zonder de ingebouwde requests, omdat die op chunked stukloopt."""
    if isinstance(body, str):
        body = body.encode()
    hdr = {"Host": host if tls else "%s:%d" % (host, port),
           "Connection": "close",
           "Content-Length": str(len(body))}
    if headers:
        hdr.update(headers)
    req = "%s %s HTTP/1.1\r\n" % (method, path)
    req += "".join("%s: %s\r\n" % kv for kv in hdr.items()) + "\r\n"

    reader = writer = None
    try:
        if tls:
            import ssl
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            try:
                ctx.verify_mode = ssl.CERT_NONE
            except Exception:
                pass
            coro = asyncio.open_connection(host, port, ssl=ctx,
                                           server_hostname=host)
        else:
            coro = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(coro, timeout)
        writer.write(req.encode() + body)
        await writer.drain()
        buf = b""
        while True:
            stuk = await asyncio.wait_for(reader.read(1024), timeout)
            if not stuk:
                break
            buf += stuk
    except asyncio.TimeoutError:
        raise SonosError("geen antwoord van " + host)
    except OSError as e:
        raise SonosError("%s onbereikbaar (%s)" % (host, e))
    finally:
        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    head, _, raw = buf.partition(b"\r\n\r\n")
    if not head:
        raise SonosError("leeg antwoord van " + host)
    status = int(head.split(b" ")[1])
    if b"chunked" in head.lower():
        out = b""
        while raw:
            regel, _, raw = raw.partition(b"\r\n")
            try:
                n = int(regel.split(b";")[0].strip(), 16)
            except ValueError:
                break
            if n == 0:
                break
            out += raw[:n]
            raw = raw[n + 2:]
        raw = out
    return status, raw.decode("utf-8", "replace") if hasattr(raw, "decode") else raw


async def soap(ip, svc, action, args, timeout=10):
    path, urn = svc
    inner = "".join("<%s>%s</%s>" % (k, esc(str(v)), k) for k, v in args)
    env = ('<?xml version="1.0"?><s:Envelope '
           'xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
           's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
           '<s:Body><u:%s xmlns:u="%s">%s</u:%s></s:Body></s:Envelope>'
           % (action, urn, inner, action))
    st, body = await http(ip, "POST", path, env, {
        "Content-Type": 'text/xml; charset="utf-8"',
        "SOAPACTION": '"%s#%s"' % (urn, action)}, timeout=timeout)
    if st != 200:
        raise SonosError("UPnP %s bij %s" % (tag(body, "errorCode"), action))
    return body


# ------------------------------------------------------------- ontdekken

MSEARCH = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
           'MAN: "ssdp:discover"\r\nMX: 1\r\n'
           "ST: urn:schemas-upnp-org:device:ZonePlayer:1\r\n\r\n")


async def discover(ms=3000):
    """SSDP met een niet-blokkerende socket, zodat de UI blijft tekenen.

    IP_MULTICAST_TTL is op deze ESP32 niet te zetten en lwip zegt dat ook. Op
    een plat subnet maakt het niet uit: de antwoorden komen unicast terug, dus
    multicast hoeft alleen uitgaand te werken."""
    try:
        addr = socket.getaddrinfo("239.255.255.250", 1900)[0][-1]
    except OSError:
        raise SonosError("geen netwerk")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setblocking(False)
    gevonden = {}
    try:
        for _ in range(3):
            try:
                s.sendto(MSEARCH.encode(), addr)
            except OSError:
                pass
            await sleep_ms(20)
        t0 = ticks_ms()
        while ticks_diff(ticks_ms(), t0) < ms:
            try:
                data, src = s.recvfrom(1024)
            except OSError:
                await sleep_ms(50)
                continue
            m = re.search("uuid:(RINCON_[A-Za-z0-9]+)", data.decode())
            if m:
                gevonden[src[0]] = m.group(1)
    finally:
        s.close()
    return gevonden


async def zones(ip):
    """Alle kamers, uids en groepen in een enkele call.

    Per speler device_description.xml ophalen is de traagste call in het hele
    protocol. Deze geeft hetzelfde in een fractie daarvan, plus de
    groepsstructuur."""
    raw = unesc(tag(await soap(ip, ZGT, "GetZoneGroupState", []),
                    "ZoneGroupState") or "")
    uit, pos = [], 0
    pat_g = re.compile('<ZoneGroup Coordinator="([^"]+)"')
    pat_m = ('<ZoneGroupMember UUID="([^"]+)" '
             'Location="http://([0-9.]+):1400[^"]*" ZoneName="([^"]+)"')
    while pos < len(raw):
        m = pat_g.search(raw[pos:])
        if not m:
            break
        coord = m.group(1)
        start = pos + raw[pos:].find(m.group(0))
        eind = raw.find("</ZoneGroup>", start)
        blok = raw[start:eind if eind > 0 else len(raw)]
        for uuid, lid_ip, naam in scan(blok, pat_m):
            uit.append({"uid": uuid, "ip": lid_ip, "naam": unesc(naam),
                        "baas": uuid == coord, "coordinator": coord})
        pos = eind if eind > 0 else len(raw)
    uit.sort(key=lambda z: z["naam"])
    return uit


async def uid(ip):
    st, d = await http(ip, "GET", "/xml/device_description.xml")
    u = tag(d, "UDN") or ""
    return u[5:] if u.startswith("uuid:") else None


# -------------------------------------------------------------- bedienen

async def state(ip):
    return tag(await soap(ip, AV, "GetTransportInfo", [("InstanceID", 0)]),
               "CurrentTransportState") or "?"


def lijkt_stream_id(titel):
    """Bij radio zet Sonos geen liedtitel in dc:title maar de naam van het
    streambestand, compleet met querystring. Gemeten op VRT Radio 1:

        vrt-radio1-aac-128-4855518?sABC=6n835oqs#0#3n4n...&amsparams=...

    Dat is geen titel maar een URL-fragment, en het hoort niet op het scherm."""
    if not titel:
        return False
    if "://" in titel or "?" in titel or "&" in titel:
        return True
    return len(titel) > 28 and " " not in titel


async def zendernaam(ip):
    """De naam van de zender staat in GetMediaInfo, niet in GetPositionInfo."""
    mi = await soap(ip, AV, "GetMediaInfo", [("InstanceID", 0)])
    return tag(tag(mi, "CurrentURIMetaData") or "", "title") or ""


async def now(ip):
    b = await soap(ip, AV, "GetPositionInfo",
                   [("InstanceID", 0), ("Channel", "Master")])
    meta = tag(b, "TrackMetaData") or ""
    titel = tag(meta, "title") or ""
    artiest = tag(meta, "creator") or ""
    # r:streamContent draagt bij radio wat er nu klinkt. Bij Spotify uit de
    # wachtrij is hij leeg en klopt dc:title gewoon.
    stroom = tag(meta, "streamContent") or ""
    if stroom:
        titel = stroom
        if not artiest:
            artiest = await zendernaam(ip)
    elif lijkt_stream_id(titel):
        titel = await zendernaam(ip) or titel
    return {"titel": titel,
            "artiest": artiest,
            "album": tag(meta, "album") or "",
            "positie": tag(b, "RelTime") or "",
            "duur": tag(b, "TrackDuration") or ""}


async def get_volume(ip):
    return int(tag(await soap(ip, RC, "GetVolume",
                              [("InstanceID", 0), ("Channel", "Master")]),
                   "CurrentVolume") or 0)


async def set_volume(ip, level):
    level = max(0, min(100, int(level)))
    await soap(ip, RC, "SetVolume",
               [("InstanceID", 0), ("Channel", "Master"),
                ("DesiredVolume", level)])
    return level


async def play(ip):
    await soap(ip, AV, "Play", [("InstanceID", 0), ("Speed", 1)])


async def pause(ip):
    await soap(ip, AV, "Pause", [("InstanceID", 0)])


async def stop(ip):
    await soap(ip, AV, "Stop", [("InstanceID", 0)])


async def nxt(ip):
    await soap(ip, AV, "Next", [("InstanceID", 0)])


async def prev(ip):
    await soap(ip, AV, "Previous", [("InstanceID", 0)])


async def clear_queue(ip):
    await soap(ip, AV, "RemoveAllTracksFromQueue", [("InstanceID", 0)])


# --------------------------------------------------------------- Spotify

async def services(ip):
    raw = tag(await soap(ip, MS, "ListAvailableServices", []),
              "AvailableServiceDescriptorList") or ""
    return [(int(a), unesc(b))
            for a, b in scan(raw, '<Service Id="([0-9]+)" Name="([^"]+)"')]


async def spotify_sn(ip):
    """Het nummer voor de cdudn, uitgerekend uit het service-Id."""
    try:
        for sid, naam in await services(ip):
            if naam == "Spotify":
                return sid * 256 + 7
    except Exception:
        pass
    return SPOTIFY_FALLBACK


async def accounts(ip):
    """De accounts die op dit huishouden staan, per dienst.

    Geen SOAP maar een gewone GET op /status/accounts. Geeft een lijst dicts met
    type, serienummer en gebruikersnaam. Het serienummer is wat in de cdudn
    hoort; welke van de vier Spotify-accounts een badge gebruikt is daarmee een
    voorkeur per badge.
    """
    status, body = await http(ip, "GET", "/status/accounts", port=1400)
    if status != 200:
        raise SonosError("accounts: HTTP %s" % status)
    uit = []
    pos = 0
    while True:
        i = body.find("<Account ", pos)
        if i < 0:
            return uit
        j = body.find("</Account>", i)
        if j < 0:
            j = body.find("/>", i)
            if j < 0:
                return uit
        blok = body[i:j]
        soort = re.search('Type="([0-9]+)"', blok)
        serie = re.search('SerialNum="([0-9]+)"', blok)
        naam = re.search("<UN>(.*?)</UN>", blok)
        uit.append({"type": int(soort.group(1)) if soort else 0,
                    "serial": serie.group(1) if serie else "0",
                    "gebruiker": unesc(naam.group(1)) if naam else ""})
        pos = j + 1


def parse_spotify(uri):
    m = re.search("spotify.*[:/](album|episode|playlist|show|track)[:/]([A-Za-z0-9]+)", uri)
    if not m:
        return None, None
    return m.group(1), ("spotify:%s:%s" % (m.group(1), m.group(2))).replace(":", "%3a")


def metadata(soort, encoded, sn, titel="", account="0"):
    """De cdudn zegt welke dienst en welk account de muziek levert.

    Het laatste veld is het accountnummer binnen die dienst. Bij een gezin met
    vier Spotify-accounts op hetzelfde huishouden is dat het enige verschil
    tussen "speel de lijst van papa" en "speel de lijst van de kinderen". Nul is
    het account dat Sonos zelf als eerste noemt, en dat was hiervoor de enige
    mogelijkheid."""
    key, cls = MAGIC[soort]
    return ('<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/"'
            ' xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"'
            ' xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/"'
            ' xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            '<item id="%s" parentID="-1" restricted="true">'
            "<dc:title>%s</dc:title><upnp:class>%s</upnp:class>"
            '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">'
            "SA_RINCON%d_X_#Svc%d-%s-Token</desc></item></DIDL-Lite>"
            % (key + encoded, esc(titel), cls, sn, sn, account))


async def play_spotify(ip, uri, shuffle=False, titel="", speler_uid=None,
                       sn=None, account="0"):
    """Wachtrij vervangen door deze playlist of dit album, en starten."""
    soort, encoded = parse_spotify(uri)
    if not soort:
        raise SonosError("geen Spotify-link")
    if sn is None:
        sn = await spotify_sn(ip)
    if speler_uid is None:
        speler_uid = await uid(ip)
    await clear_queue(ip)
    if soort in CONTAINERS:
        enqueued = "x-rincon-cpcontainer:" + MAGIC[soort][0] + encoded
    else:
        enqueued = "x-sonos-spotify:" + encoded
    try:
        r = await soap(ip, AV, "AddURIToQueue", [
            ("InstanceID", 0), ("EnqueuedURI", enqueued),
            ("EnqueuedURIMetaData",
             metadata(soort, encoded, sn, titel, account)),
            ("DesiredFirstTrackNumberEnqueued", 0), ("EnqueueAsNext", 0)])
    except SonosError as e:
        # 804 komt in de praktijk van een playlist die niet meer bestaat, niet
        # van kapotte metadata. Gemeten: acht favorieten werkten, de negende gaf
        # 804 omdat de playlist bij Spotify weg was.
        if "804" in str(e):
            raise SonosError("Spotify kent deze lijst niet meer")
        raise
    aantal = int(tag(r, "NumTracksAdded") or 0)
    # Eerst de wachtrij tot bron maken. SetPlayMode daarvoor geeft UPnP 712,
    # want de speelmodus hoort bij de wachtrij, niet bij de speler.
    await soap(ip, AV, "SetAVTransportURI",
               [("InstanceID", 0),
                ("CurrentURI", "x-rincon-queue:%s#0" % speler_uid),
                ("CurrentURIMetaData", "")])
    await soap(ip, AV, "SetPlayMode",
               [("InstanceID", 0),
                ("NewPlayMode", "SHUFFLE" if shuffle else "NORMAL")])
    await soap(ip, AV, "Seek",
               [("InstanceID", 0), ("Unit", "TRACK_NR"), ("Target", 1)])
    await play(ip)
    return aantal


# Een favoriet is of iets dat in de wachtrij hoort, of een stream. Radio hoort
# nooit in een wachtrij: Sonos neemt de AddURIToQueue aan en speelt vervolgens
# niets, wat lijkt op een kapotte favoriet en het niet is. Het onderscheid staat
# in de resMD als upnp:class ...audioBroadcast, en anders in het schema van de
# res.
STREAM_SCHEMES = ("x-sonosapi-stream:", "x-sonosapi-radio:",
                  "x-sonosapi-hls:", "x-sonosapi-hls-static:",
                  "x-rincon-mp3radio:", "hls-radio:", "aac:", "mms:", "rtsp:")


def is_stream(fav):
    """Is dit een zender in plaats van een lijst met nummers?"""
    if "audioBroadcast" in (fav.get("resmd") or ""):
        return True
    res = fav.get("res") or ""
    for scheme in STREAM_SCHEMES:
        if res.startswith(scheme):
            return True
    return False


async def favorites(ip):
    """Sonos-favorieten met hun eigen res en resMD. Werkt zonder Spotify-login,
    want Sonos bewaart hier precies wat op dit huishouden werkt."""
    b = await soap(ip, CD, "Browse", [("ObjectID", "FV:2"),
                                      ("BrowseFlag", "BrowseDirectChildren"),
                                      ("Filter", "*"), ("StartingIndex", 0),
                                      ("RequestedCount", 100),
                                      ("SortCriteria", "")])
    didl = unesc(tag(b, "Result") or "")
    uit, pos = [], 0
    while True:
        i = didl.find("<item ", pos)
        if i < 0:
            return uit
        j = didl.find("</item>", i)
        blok = didl[i:j]
        t = re.search("<dc:title>(.*?)</dc:title>", blok)
        r = re.search('<res protocolInfo="[^"]*">(.*?)</res>', blok)
        k = blok.find("<r:resMD>")
        res = unesc(r.group(1)) if r else ""
        if res:
            uit.append({"titel": unesc(t.group(1)) if t else "?", "res": res,
                        "resmd": blok[k + 9:] + "</item></DIDL-Lite>" if k >= 0 else ""})
        pos = j + 7


async def play_favorite(ip, fav, speler_uid=None):
    if is_stream(fav):
        # Rechtstreeks op de speler. Geen wachtrij, geen Seek: een zender heeft
        # geen nummer 1 om naartoe te springen.
        await soap(ip, AV, "SetAVTransportURI",
                   [("InstanceID", 0), ("CurrentURI", fav["res"]),
                    ("CurrentURIMetaData", fav.get("resmd") or "")])
        await play(ip)
        return
    await clear_queue(ip)
    await soap(ip, AV, "AddURIToQueue", [
        ("InstanceID", 0), ("EnqueuedURI", fav["res"]),
        ("EnqueuedURIMetaData", fav.get("resmd") or ""),
        ("DesiredFirstTrackNumberEnqueued", 0), ("EnqueueAsNext", 0)])
    if speler_uid is None:
        speler_uid = await uid(ip)
    await soap(ip, AV, "SetAVTransportURI",
               [("InstanceID", 0),
                ("CurrentURI", "x-rincon-queue:%s#0" % speler_uid),
                ("CurrentURIMetaData", "")])
    await soap(ip, AV, "Seek",
               [("InstanceID", 0), ("Unit", "TRACK_NR"), ("Target", 1)])
    await play(ip)


# ---------------------------------------------------------------- wekker

RECURRENCE_NL = {
    "DAILY": "elke dag",
    "ONCE": "eenmalig",
    "WEEKDAYS": "weekdagen",
    "WEEKENDS": "weekend",
}

DAGEN = "zmdwdvz"     # zondag eerst, zoals Sonos ON_0123456 nummert


def recurrence_text(recurrence):
    """Sonos schrijft of een sleutelwoord, of ON_ met dagnummers erachter."""
    if recurrence in RECURRENCE_NL:
        return RECURRENCE_NL[recurrence]
    if recurrence.startswith("ON_"):
        cijfers = recurrence[3:]
        if not cijfers:
            return "eenmalig"
        letters = []
        for c in cijfers:
            if c.isdigit() and int(c) < 7:
                letters.append(DAGEN[int(c)])
        return "".join(letters) if letters else recurrence
    return recurrence


async def alarms(ip, room_uuid=None):
    """Alle alarmen van het huishouden, eventueel gefilterd op een kamer.

    De lijst is systeembreed: elke speler geeft dezelfde terug, met RoomUUID om
    te zeggen waar hij hoort."""
    b = await soap(ip, AC, "ListAlarms", [])
    raw = tag(b, "CurrentAlarmList") or ""
    uit, pos = [], 0
    while True:
        i = raw.find("<Alarm ", pos)
        if i < 0:
            break
        j = raw.find(">", i)
        if j < 0:
            break
        a = attrs(raw[i:j])
        pos = j + 1
        if not a.get("ID"):
            continue
        if room_uuid and a.get("RoomUUID") != room_uuid:
            continue
        titel = ""
        md = a.get("ProgramMetaData") or ""
        if md:
            titel = tag(unesc(md), "title") or ""
        uit.append({
            "id": a["ID"],
            "tijd": (a.get("StartTime") or "00:00:00")[:5],
            "duur": a.get("Duration") or "",
            "herhaling": a.get("Recurrence") or "ONCE",
            "aan": a.get("Enabled") == "1",
            "room": a.get("RoomUUID") or "",
            "volume": int(a.get("Volume") or 0),
            "bron": titel or "wekgeluid",
            "_ruw": a,
        })
    uit.sort(key=lambda x: x["tijd"])
    return uit


def _shift_time(hhmm, minuten):
    """'07:30' plus of min een aantal minuten, rond de klok."""
    uur, minuut = int(hhmm[:2]), int(hhmm[3:5])
    totaal = (uur * 60 + minuut + minuten) % (24 * 60)
    return "%02d:%02d" % (totaal // 60, totaal % 60)


async def update_alarm(ip, alarm, aan=None, tijd=None):
    """Een alarm bijwerken. UpdateAlarm is een volledige vervanging, dus alle
    velden gaan onveranderd terug behalve wat hier meegegeven is.

    Let op: ListAlarms noemt het veld StartTime, UpdateAlarm noemt het
    StartLocalTime. Wie dat over het hoofd ziet, stuurt een leeg tijdveld."""
    a = alarm["_ruw"]
    nieuw_aan = alarm["aan"] if aan is None else bool(aan)
    nieuwe_tijd = alarm["tijd"] if tijd is None else tijd
    await soap(ip, AC, "UpdateAlarm", [
        ("ID", a["ID"]),
        ("StartLocalTime", nieuwe_tijd + ":00"),
        ("Duration", a.get("Duration") or ""),
        ("Recurrence", a.get("Recurrence") or "ONCE"),
        ("Enabled", "1" if nieuw_aan else "0"),
        ("RoomUUID", a.get("RoomUUID") or ""),
        ("ProgramURI", a.get("ProgramURI") or "x-rincon-buzzer:0"),
        # Deze komt XML-geescapet uit ListAlarms en moet ontescapet terug: soap()
        # escapet zelf opnieuw. Twee keer escapen maakt er &amp;lt; van en dan
        # verliest het alarm zijn bron.
        ("ProgramMetaData", unesc(a.get("ProgramMetaData") or "")),
        ("PlayMode", a.get("PlayMode") or "NORMAL"),
        ("Volume", a.get("Volume") or "25"),
        ("IncludeLinkedZones", a.get("IncludeLinkedZones") or "0"),
    ])
    alarm["aan"] = nieuw_aan
    alarm["tijd"] = nieuwe_tijd
    a["Enabled"] = "1" if nieuw_aan else "0"
    a["StartTime"] = nieuwe_tijd + ":00"
    return alarm
