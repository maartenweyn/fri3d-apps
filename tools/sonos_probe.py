#!/usr/bin/env python3
"""
sonos_probe.py - Sonos verkennen en Spotify-playlists starten, met alleen de
standaardbibliotheek. Bedoeld om op de Mac te draaien voordat er ook maar een
regel MicroPython voor de badge geschreven wordt.

Alles wat hier staat is met opzet zo geschreven dat de port naar MicroPython
mechanisch is: geen XML-parser, geen requests, geen f-string-magie in de
protocollaag. Vervang urllib door urequests en het draait op de ESP32.

Gebruik:
    ./sonos_probe.py discover
    ./sonos_probe.py info      192.168.0.42
    ./sonos_probe.py services  192.168.0.42     # welk SID heeft Spotify hier?
    ./sonos_probe.py now       192.168.0.42
    ./sonos_probe.py play      192.168.0.42 https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M
    ./sonos_probe.py play      192.168.0.42 spotify:playlist:37i9dQZF1DXcBWIGoYBM5M --shuffle
    ./sonos_probe.py pause     192.168.0.42
    ./sonos_probe.py resume    192.168.0.42
    ./sonos_probe.py next      192.168.0.42
    ./sonos_probe.py prev      192.168.0.42
    ./sonos_probe.py volume    192.168.0.42 35
    ./sonos_probe.py favorites 192.168.0.42
    ./sonos_probe.py accounts  192.168.0.42     # welke Spotify-accounts staan erop?
"""

import re
import socket
import sys
import urllib.error
import urllib.request

PORT = 1400
SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900
SSDP_ST = "urn:schemas-upnp-org:device:ZonePlayer:1"

AV_TRANSPORT = ("/MediaRenderer/AVTransport/Control",
                "urn:schemas-upnp-org:service:AVTransport:1")
RENDERING = ("/MediaRenderer/RenderingControl/Control",
             "urn:schemas-upnp-org:service:RenderingControl:1")
CONTENT_DIR = ("/MediaServer/ContentDirectory/Control",
               "urn:schemas-upnp-org:service:ContentDirectory:1")
MUSIC_SERVICES = ("/MusicServices/Control",
                  "urn:schemas-upnp-org:service:MusicServices:1")

# Spotify-service-id zoals SoCo hem kent. 2311 is de gangbare (EU/wereld),
# 3079 is Spotify US. Welke van de twee jouw huishouden gebruikt zie je met
# het subcommando `services`. Bij twijfel probeert play() ze allebei.
SPOTIFY_SIDS = (2311, 3079)

# Per soort gedeelde inhoud een prefix voor de enqueue-URI, een sleutel die
# voor de item-id komt, en de upnp:class. Overgenomen uit soco/plugins/sharelink.py.
MAGIC = {
    "playlist": ("x-rincon-cpcontainer:1006206c", "1006206c",
                 "object.container.playlistContainer"),
    "album":    ("x-rincon-cpcontainer:1004206c", "00040000",
                 "object.container.album.musicAlbum"),
    "show":     ("x-rincon-cpcontainer:1006206c", "1006206c",
                 "object.container.playlistContainer"),
    "track":    ("", "00032020", "object.item.audioItem.musicTrack"),
    "episode":  ("", "00032020", "object.item.audioItem.musicTrack"),
}


# --------------------------------------------------------------------------
# XML zonder parser
# --------------------------------------------------------------------------

def xml_escape(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def xml_unescape(text):
    return (text.replace("&lt;", "<").replace("&gt;", ">")
                .replace("&quot;", '"').replace("&apos;", "'")
                .replace("&amp;", "&"))


def tag(body, name):
    """Inhoud van het eerste <name>...</name>, of None. Negeert namespaces.

    De naam moet eindigen op ">" of een spatie. Zonder die eis matcht "album"
    ook op <upnp:albumArtURI> en krijg je een URL waar een albumtitel hoort."""
    m = re.search(r"<(?:\w+:)?" + name + r">(.*?)</(?:\w+:)?" + name + r">", body, re.S)
    if not m:
        m = re.search(r"<(?:\w+:)?" + name + r" [^>]*>(.*?)</(?:\w+:)?" + name + r">",
                      body, re.S)
    return xml_unescape(m.group(1)) if m else None


# --------------------------------------------------------------------------
# SOAP
# --------------------------------------------------------------------------

def soap(ip, service, action, args, timeout=6):
    """Eén SOAP-call. args is een lijst van (naam, waarde) tuples, op volgorde."""
    path, urn = service
    inner = "".join("<{0}>{1}</{0}>".format(k, xml_escape(str(v))) for k, v in args)
    envelope = (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        '<s:Body><u:{action} xmlns:u="{urn}">{inner}</u:{action}></s:Body>'
        '</s:Envelope>'
    ).format(action=action, urn=urn, inner=inner)

    req = urllib.request.Request(
        "http://{0}:{1}{2}".format(ip, PORT, path),
        data=envelope.encode("utf-8"),
        headers={
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPACTION": '"{0}#{1}"'.format(urn, action),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", "replace")
        code = tag(body, "errorCode") or str(err.code)
        raise RuntimeError("UPnP-fout {0} bij {1}".format(code, action))


def http_get(url, timeout=6):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


# --------------------------------------------------------------------------
# Ontdekken
# --------------------------------------------------------------------------

def discover(timeout=3.0):
    """M-SEARCH naar de multicastgroep. Antwoorden komen unicast terug, dus een
    gewone UDP-socket volstaat; multicast *ontvangen* hoeft niet."""
    msg = (
        "M-SEARCH * HTTP/1.1\r\n"
        "HOST: {0}:{1}\r\n"
        'MAN: "ssdp:discover"\r\n'
        "MX: 1\r\n"
        "ST: {2}\r\n\r\n"
    ).format(SSDP_ADDR, SSDP_PORT, SSDP_ST).encode()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(0.6)
    found = {}
    for _ in range(3):
        sock.sendto(msg, (SSDP_ADDR, SSDP_PORT))
    deadline = timeout
    while deadline > 0:
        try:
            data, addr = sock.recvfrom(2048)
        except socket.timeout:
            deadline -= 0.6
            continue
        text = data.decode("utf-8", "replace")
        uid = re.search(r"uuid:(RINCON_\w+)", text)
        if uid and addr[0] not in found:
            found[addr[0]] = uid.group(1)
    sock.close()
    return found


def room_name(ip):
    try:
        xml = http_get("http://{0}:{1}/xml/device_description.xml".format(ip, PORT))
        return tag(xml, "roomName") or "?"
    except Exception:
        return "?"


def coordinator_of(ip):
    """Als deze speler in een groep zit als slaaf, staat zijn CurrentURI op
    x-rincon:RINCON_<uid van de baas>. Alleen de baas accepteert Play."""
    body = soap(ip, AV_TRANSPORT, "GetMediaInfo", [("InstanceID", 0)])
    uri = tag(body, "CurrentURI") or ""
    m = re.match(r"x-rincon:(RINCON_\w+)", uri)
    return m.group(1) if m else None


# --------------------------------------------------------------------------
# Spotify op Sonos
# --------------------------------------------------------------------------

def parse_spotify(uri):
    """https://open.spotify.com/playlist/xxx of spotify:playlist:xxx
    -> ('playlist', 'spotify%3aplaylist%3axxx')"""
    m = re.search(r"spotify.*[:/](album|episode|playlist|show|track)[:/](\w+)", uri)
    if not m:
        return None, None
    canonical = "spotify:" + m.group(1) + ":" + m.group(2)
    return m.group(1), canonical.replace(":", "%3a")


def spotify_metadata(share_type, encoded_uri, sid, title=""):
    prefix, key, item_class = MAGIC[share_type]
    return (
        '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/"'
        ' xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"'
        ' xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/"'
        ' xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
        '<item id="{item_id}" parentID="-1" restricted="true">'
        "<dc:title>{title}</dc:title>"
        "<upnp:class>{item_class}</upnp:class>"
        '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">'
        "SA_RINCON{sn}_X_#Svc{sn}-0-Token</desc></item></DIDL-Lite>"
    ).format(item_id=key + encoded_uri, title=xml_escape(title),
             item_class=item_class, sn=sid)


def music_services(ip):
    """(Id, naam) van alle muziekdiensten die de speler kent."""
    raw = xml_unescape(tag(soap(ip, MUSIC_SERVICES, "ListAvailableServices", []),
                           "AvailableServiceDescriptorList") or "")
    return [(int(a), b) for a, b in
            re.findall(r'<Service Id="(\d+)" Name="([^"]+)"', raw)]


def spotify_sids(ip):
    """Het nummer in de cdudn is het service-Id maal 256 plus 7. Gemeten:
    Spotify heeft Id 9 en dus 2311, Spotify US Id 12 en dus 3079. Uitrekenen
    is betrouwbaarder dan 2311 hardcoderen."""
    try:
        for sid, naam in music_services(ip):
            if naam == "Spotify":
                return [sid * 256 + 7]
    except Exception:
        pass
    return list(SPOTIFY_SIDS)


def play_spotify(ip, uri, shuffle=False, title=""):
    share_type, encoded = parse_spotify(uri)
    if not share_type:
        raise SystemExit("Geen herkenbare Spotify-link: " + uri)

    boss = coordinator_of(ip)
    if boss:
        raise SystemExit(
            "Deze speler is gegroepeerd onder {0}. Stuur het commando naar de "
            "baas van de groep, niet naar de slaaf.".format(boss))

    uid = re.search(r"uuid:(RINCON_\w+)",
                    http_get("http://{0}:{1}/xml/device_description.xml".format(ip, PORT)))
    if not uid:
        raise SystemExit("Geen RINCON-uid gevonden op " + ip)
    uid = uid.group(1)

    prefix = MAGIC[share_type][0]
    enqueue_uri = prefix + encoded

    soap(ip, AV_TRANSPORT, "RemoveAllTracksFromQueue", [("InstanceID", 0)])

    last = None
    for sid in spotify_sids(ip):
        meta = spotify_metadata(share_type, encoded, sid, title)
        try:
            soap(ip, AV_TRANSPORT, "AddURIToQueue", [
                ("InstanceID", 0),
                ("EnqueuedURI", enqueue_uri),
                ("EnqueuedURIMetaData", meta),
                ("DesiredFirstTrackNumberEnqueued", 0),
                ("EnqueueAsNext", 0),
            ])
            print("  service-id {0} aanvaard".format(sid))
            last = None
            break
        except RuntimeError as err:
            last = err
            print("  service-id {0} geweigerd: {1}".format(sid, err))
    if last:
        raise SystemExit("Geen enkele service-id werkte. " + str(last))

    # Eerst de wachtrij tot bron maken. SetPlayMode daarvoor geeft UPnP 712:
    # de speelmodus hoort bij de wachtrij, niet bij de speler.
    soap(ip, AV_TRANSPORT, "SetAVTransportURI", [
        ("InstanceID", 0),
        ("CurrentURI", "x-rincon-queue:{0}#0".format(uid)),
        ("CurrentURIMetaData", ""),
    ])
    soap(ip, AV_TRANSPORT, "SetPlayMode",
         [("InstanceID", 0), ("NewPlayMode", "SHUFFLE" if shuffle else "NORMAL")])
    soap(ip, AV_TRANSPORT, "Seek",
         [("InstanceID", 0), ("Unit", "TRACK_NR"), ("Target", 1)])
    soap(ip, AV_TRANSPORT, "Play", [("InstanceID", 0), ("Speed", 1)])


# --------------------------------------------------------------------------
# Bediening en uitlezen
# --------------------------------------------------------------------------

def now_playing(ip):
    body = soap(ip, AV_TRANSPORT, "GetPositionInfo",
                [("InstanceID", 0), ("Channel", "Master")])
    meta = xml_unescape(tag(body, "TrackMetaData") or "")
    return {
        "titel": tag(meta, "title") or "?",
        "artiest": tag(meta, "creator") or "?",
        "album": tag(meta, "album") or "?",
        "positie": tag(body, "RelTime") or "?",
        "duur": tag(body, "TrackDuration") or "?",
        "nummer": tag(body, "Track") or "?",
    }


def transport_state(ip):
    body = soap(ip, AV_TRANSPORT, "GetTransportInfo", [("InstanceID", 0)])
    return tag(body, "CurrentTransportState") or "?"


def get_volume(ip):
    body = soap(ip, RENDERING, "GetVolume",
                [("InstanceID", 0), ("Channel", "Master")])
    return int(tag(body, "CurrentVolume") or 0)


def set_volume(ip, level):
    level = max(0, min(100, int(level)))
    soap(ip, RENDERING, "SetVolume",
         [("InstanceID", 0), ("Channel", "Master"), ("DesiredVolume", level)])
    return level


def favorites(ip):
    """Sonos-favorieten. Handig als terugval wanneer de Spotify-API niet
    beschikbaar is: de gebruiker beheert de lijst dan in de Sonos-app."""
    body = soap(ip, CONTENT_DIR, "Browse", [
        ("ObjectID", "FV:2"),
        ("BrowseFlag", "BrowseDirectChildren"),
        ("Filter", "*"),
        ("StartingIndex", 0),
        ("RequestedCount", 100),
        ("SortCriteria", ""),
    ])
    didl = xml_unescape(tag(body, "Result") or "")
    out = []
    for item in re.findall(r"<item .*?</item>", didl, re.S):
        out.append((tag(item, "title") or "?", tag(item, "res") or ""))
    return out


def accounts(ip):
    """De accounts die op dit huishouden staan.

    Een gezinsabonnement zet vier Spotify-accounts op dezelfde Sonos. Ze delen
    dan een service-id, en het serienummer is het enige dat ze uit elkaar houdt.
    Dat nummer hoort achteraan in de cdudn, en het is dus ook wat een badge moet
    bewaren om de playlists van zijn eigen account te spelen.

    Geen SOAP: een gewone GET op /status/accounts.
    """
    body = http_get("http://%s:%d/status/accounts" % (ip, PORT))
    out = []
    for blok in re.findall(r"<Account .*?(?:</Account>|/>)", body, re.S):
        soort = re.search(r'Type="([0-9]+)"', blok)
        serie = re.search(r'SerialNum="([0-9]+)"', blok)
        naam = re.search(r"<UN>(.*?)</UN>", blok)
        out.append({"type": soort.group(1) if soort else "?",
                    "serial": serie.group(1) if serie else "?",
                    "user": xml_unescape(naam.group(1)) if naam else ""})
    return out


# --------------------------------------------------------------------------

def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]

    if cmd == "discover":
        players = discover()
        if not players:
            print("Niets gevonden. Zit je op hetzelfde subnet, en staat "
                  "multicast aan op dit netwerk?")
            return 1
        for ip, uid in sorted(players.items()):
            boss = coordinator_of(ip)
            rol = "slaaf van " + boss if boss else "baas"
            print("{0:<16} {1:<26} {2:<18} {3}".format(
                ip, uid, room_name(ip), rol))
        return 0

    if len(argv) < 3:
        print(__doc__)
        return 1
    ip = argv[2]

    if cmd == "info":
        print("kamer     ", room_name(ip))
        print("staat     ", transport_state(ip))
        print("volume    ", get_volume(ip))
        boss = coordinator_of(ip)
        print("groep     ", "slaaf van " + boss if boss else "baas")
        for k, v in now_playing(ip).items():
            print("{0:<10}".format(k), v)
    elif cmd == "services":
        body = soap(ip, MUSIC_SERVICES, "ListAvailableServices", [])
        raw = xml_unescape(tag(body, "AvailableServiceDescriptorList") or "")
        for m in re.finditer(r"<Service ([^>]*)>", raw):
            attrs = m.group(1)
            if "Spotify" in attrs or "Id=" in attrs:
                name = re.search(r'Name="([^"]*)"', attrs)
                sid = re.search(r'Id="(\d+)"', attrs)
                if name and sid:
                    print("{0:<8} {1}".format(sid.group(1), name.group(1)))
    elif cmd == "now":
        for k, v in now_playing(ip).items():
            print("{0:<10}".format(k), v)
    elif cmd == "play":
        if len(argv) < 4:
            print("play <ip> <spotify-link> [--shuffle]")
            return 1
        play_spotify(ip, argv[3], shuffle="--shuffle" in argv)
        print("gestart op", room_name(ip))
    elif cmd == "pause":
        soap(ip, AV_TRANSPORT, "Pause", [("InstanceID", 0)])
    elif cmd == "resume":
        soap(ip, AV_TRANSPORT, "Play", [("InstanceID", 0), ("Speed", 1)])
    elif cmd == "next":
        soap(ip, AV_TRANSPORT, "Next", [("InstanceID", 0)])
    elif cmd == "prev":
        soap(ip, AV_TRANSPORT, "Previous", [("InstanceID", 0)])
    elif cmd == "volume":
        if len(argv) < 4:
            print(get_volume(ip))
        else:
            print(set_volume(ip, argv[3]))
    elif cmd == "favorites":
        for title, res in favorites(ip):
            print("{0:<40} {1}".format(title[:40], res[:60]))
    elif cmd == "accounts":
        gevonden = accounts(ip)
        if not gevonden:
            print("geen accounts gemeld door deze speler")
        for a in gevonden:
            print("type {0:<6} serial {1:<4} {2}".format(
                a["type"], a["serial"], a["user"]))
        print()
        print("Het serienummer hierboven is wat een badge bewaart als")
        print("spotify_account. Welke van deze bij Spotify hoort zie je aan het")
        print("type; vergelijk met: ./sonos_probe.py services " + ip)
    else:
        print(__doc__)
        return 1
    return 0


class Onbereikbaar(RuntimeError):
    """Er antwoordde niets op dit adres."""


def _uitleg_onbereikbaar(argv):
    ip = argv[2] if len(argv) > 2 else "<ip>"
    print("Geen antwoord van {0} op poort {1}.".format(ip, PORT))
    print()
    print("Drie dingen die dit meestal zijn:")
    print("  1. Het is geen Sonos-speler. Zoek het adres met")
    print("     ./sonos_probe.py discover, of kijk in Home Assistant bij de")
    print("     Sonos-integratie welk IP een speler heeft.")
    print("  2. Je zit niet op hetzelfde netwerk. Een Tailscale-exitnode")
    print("     routeert internetverkeer, geen LAN: daarvoor moet de knoop")
    print("     thuis het subnet adverteren (--advertise-routes) en moet deze")
    print("     machine die route aannemen (--accept-routes).")
    print("  3. De speler staat uit.")
    print()
    print("Let op: discover gebruikt multicast en werkt dus alleen op het")
    print("netwerk zelf, ook met een subnetroute erbij.")


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except (socket.timeout, TimeoutError, urllib.error.URLError, OSError) as e:
        # Een kale traceback met "timed out" zegt niet welke van de drie het is.
        _uitleg_onbereikbaar(sys.argv)
        print()
        print("(", type(e).__name__, e, ")")
        sys.exit(1)
