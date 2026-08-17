"""Offline tests voor de Muziek-app (be.weyn.muziek).

Draait op gewone Python tegen de stubs in tests/stubs/, zodat het protocol en de
schermlogica na te kijken zijn zonder badge en zonder Sonos.

    python3 tests/test_muziek.py

Het netwerk wordt vervangen door mzsonos.http, die hier canned antwoorden
teruggeeft. De voorbeelden zijn geen verzinsels: de alarmen, de topologie en de
favorieten hieronder komen woordelijk van een echt Sonos-systeem, inclusief de
dubbele XML-escaping die de valstrik van UpdateAlarm is.
"""

import asyncio
import json
import os
import sys
import types

sys.dont_write_bytecode = True   # nooit __pycache__ in de app-map achterlaten

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.join(ROOT, "be.weyn.muziek"))

# muziek_config.py is gitignored, dus de app-map heeft er misschien geen. Zet er
# een bekende in plaats van af te hangen van wat deze machine toevallig heeft.
_config = types.ModuleType("muziek_config")
_config.SPOTIFY_CLIENT_ID = "test-client"
_config.SPOTIFY_REFRESH_TOKEN = "test-refresh"
_config.SONOS_IP = ""
_config.DISCOVER_MS = 10
_config.SHUFFLE = True
sys.modules["muziek_config"] = _config

import lvgl as lv                                     # noqa: E402
import mpos                                           # noqa: E402
import mpos.ui                                        # noqa: E402

import mzsonos                                        # noqa: E402
import mzspotify                                      # noqa: E402
import mzstate as state                               # noqa: E402
import mzui as ui                                     # noqa: E402
from muziek import Muziek                             # noqa: E402
from mzzones import MuziekZones                       # noqa: E402
from mzplaylists import MuziekLijsten                 # noqa: E402
from mzalarms import MuziekWekkers                    # noqa: E402

FAILURES = []
CHECKS = {"n": 0}


def check(label, conditie):
    CHECKS["n"] += 1
    if not conditie:
        FAILURES.append(label)
        print("FAIL:", label)


def equal(label, got, want):
    check("%s (kreeg %r, wilde %r)" % (label, got, want), got == want)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# --- echte antwoorden, woordelijk overgenomen ------------------------------

ZONE_STATE = (
    '<ZoneGroups>'
    '<ZoneGroup Coordinator="RINCON_AAA01400" ID="RINCON_AAA01400:1">'
    '<ZoneGroupMember UUID="RINCON_AAA01400" '
    'Location="http://192.168.68.113:1400/xml/device_description.xml" '
    'ZoneName="Bathroom" Icon="x-rincon-roomicon:bathroom"/>'
    '</ZoneGroup>'
    '<ZoneGroup Coordinator="RINCON_BBB01400" ID="RINCON_BBB01400:7">'
    '<ZoneGroupMember UUID="RINCON_BBB01400" '
    'Location="http://192.168.68.129:1400/xml/device_description.xml" '
    'ZoneName="Kitchen" Icon="x-rincon-roomicon:kitchen"/>'
    '<ZoneGroupMember UUID="RINCON_CCC01400" '
    'Location="http://192.168.68.119:1400/xml/device_description.xml" '
    'ZoneName="Bedroom" Icon="x-rincon-roomicon:bedroom"/>'
    '</ZoneGroup>'
    '</ZoneGroups>'
)

# Uit ListAlarms op de echte installatie. Let op de dubbele escaping in
# ProgramMetaData: het is XML in een attribuut van XML.
ALARM_LIST = (
    '<Alarms>'
    '<Alarm ID="1" StartTime="06:59:00" Duration="00:25:00" '
    'Recurrence="WEEKDAYS" Enabled="0" RoomUUID="RINCON_CCC01400" '
    'ProgramURI="x-sonosapi-stream:tunein%3a7369?sid=303&amp;flags=8232&amp;sn=6" '
    'ProgramMetaData="&lt;DIDL-Lite&gt;&lt;item&gt;&lt;dc:title&gt;VRT Radio 1'
    '&lt;/dc:title&gt;&lt;/item&gt;&lt;/DIDL-Lite&gt;" '
    'PlayMode="NORMAL" Volume="5" IncludeLinkedZones="0">'
    '<Content type="stream" serviceId="303"/></Alarm>'
    '<Alarm ID="71" StartTime="08:01:00" Duration="00:15:00" '
    'Recurrence="ONCE" Enabled="1" RoomUUID="RINCON_AAA01400" '
    'ProgramURI="x-rincon-buzzer:0" ProgramMetaData="" '
    'PlayMode="NORMAL" Volume="25" IncludeLinkedZones="0"/>'
    '<Alarm ID="9" StartTime="07:15:00" Duration="00:30:00" '
    'Recurrence="ON_06" Enabled="1" RoomUUID="RINCON_CCC01400" '
    'ProgramURI="x-rincon-buzzer:0" ProgramMetaData="" '
    'PlayMode="SHUFFLE" Volume="18" IncludeLinkedZones="1"/>'
    '</Alarms>'
)

POSITION_INFO = (
    "<Track>1</Track><TrackDuration>0:03:11</TrackDuration>"
    "<TrackMetaData>&lt;DIDL-Lite&gt;&lt;item&gt;"
    "&lt;upnp:albumArtURI&gt;https://i.scdn.co/image/abc&lt;/upnp:albumArtURI&gt;"
    "&lt;dc:title&gt;FE!N&lt;/dc:title&gt;"
    "&lt;dc:creator&gt;Travis Scott&lt;/dc:creator&gt;"
    "&lt;upnp:album&gt;UTOPIA&lt;/upnp:album&gt;"
    "&lt;/item&gt;&lt;/DIDL-Lite&gt;</TrackMetaData>"
    "<RelTime>0:00:07</RelTime>"
)

FAVORITES_DIDL = (
    "&lt;DIDL-Lite&gt;"
    "&lt;item id=&quot;FV:2/20&quot;&gt;&lt;dc:title&gt;Oki&lt;/dc:title&gt;"
    "&lt;res protocolInfo=&quot;x-rincon-cpcontainer:*:*:*&quot;&gt;"
    "x-rincon-cpcontainer:1006286cspotify%3Aplaylist%3AOKI1&amp;amp;sn=2"
    "&lt;/res&gt;&lt;r:resMD&gt;&lt;DIDL-Lite&gt;&lt;item&gt;"
    "&lt;dc:title&gt;Oki&lt;/dc:title&gt;&lt;/item&gt;"
    "&lt;/r:resMD&gt;&lt;/item&gt;"
    "&lt;item id=&quot;FV:2/21&quot;&gt;&lt;dc:title&gt;Sonos Radio&lt;/dc:title&gt;"
    "&lt;/item&gt;"
    "&lt;/DIDL-Lite&gt;"
)


# --- nepnetwerk ------------------------------------------------------------

class Net:
    """Vervangt mzsonos.http. Onthoudt elke call en antwoordt uit een tabel."""

    def __init__(self):
        self.calls = []          # (host, method, path, body)
        self.acties = []         # SOAP-actienamen op volgorde
        self.antwoorden = {}     # actienaam -> (status, body) of Exception
        self.http_antwoorden = {}   # (host, path) -> (status, tekst)
        self.status = 200

    def __call__(self, host, method, path, body=b"", headers=None, port=None,
                 timeout=None, tls=False):
        return self._async(host, method, path, body, headers)

    async def _async(self, host, method, path, body, headers):
        if isinstance(body, bytes):
            body = body.decode()
        self.calls.append((host, method, path, body))
        sleutel = (host, path.split("?")[0])
        if sleutel in self.http_antwoorden:
            return self.http_antwoorden[sleutel]
        actie = ""
        if headers and "SOAPACTION" in headers:
            actie = headers["SOAPACTION"].split("#")[-1].strip('"')
            self.acties.append(actie)
        antwoord = self.antwoorden.get(actie)
        if isinstance(antwoord, Exception):
            raise antwoord
        if antwoord is not None:
            return antwoord
        return (200, "<u:%sResponse></u:%sResponse>" % (actie, actie))

    def soap_body(self, actie):
        for host, method, path, body in self.calls:
            if ("#" + actie) in body or ("<u:%s " % actie) in body:
                return body
        return ""


def soap_antwoord(inhoud):
    return (200, "<s:Envelope><s:Body>" + inhoud + "</s:Body></s:Envelope>")


async def _nep_discover(ms=0):
    return {"192.168.68.113": "RINCON_AAA01400"}


def verse_net():
    net = Net()
    mzsonos.http = net
    mzsonos.discover = _nep_discover
    return net


ECHTE_HTTP = mzsonos.http
ECHTE_DISCOVER = mzsonos.discover


# --- 1. XML-helpers --------------------------------------------------------

def test_xml():
    meta = ("<upnp:albumArtURI>https://x/y</upnp:albumArtURI>"
            "<dc:title>T</dc:title><upnp:album>Echt Album</upnp:album>")
    # De regressie die op hardware gevonden is: zonder naamgrens matcht
    # "album" op <upnp:albumArtURI> en krijg je een CDN-URL.
    equal("tag album pakt niet albumArtURI", mzsonos.tag(meta, "album"), "Echt Album")
    equal("tag title", mzsonos.tag(meta, "title"), "T")
    equal("tag met attributen",
          mzsonos.tag('<res protocolInfo="a">X</res>', "res"), "X")
    equal("tag ontbreekt", mzsonos.tag("<a>1</a>", "b"), None)

    equal("esc en unesc heen en terug",
          mzsonos.unesc(mzsonos.esc('a&b<c>"d"')), 'a&b<c>"d"')
    equal("unesc doet amp als laatste",
          mzsonos.unesc("&amp;lt;"), "&lt;")

    equal("scan vindt alles",
          mzsonos.scan("<a x=\"1\"/><a x=\"2\"/>", '<a x="([0-9])"'),
          [("1",), ("2",)])
    equal("scan op lege tekst", mzsonos.scan("", "(a)"), [])
    a = mzsonos.attrs('<Alarm ID="7" Enabled="1" Recurrence="ONCE"')
    equal("attrs leest ID", a["ID"], "7")
    equal("attrs leest Recurrence", a["Recurrence"], "ONCE")

    # Een echt alarm heeft een ProgramMetaData van meer dan duizend tekens. Met
    # een regex viel de badge daarop om: de re-engine van MicroPython backtrackt
    # recursief en raakt door zijn stack. Desktop merkt dat niet, dus wordt hier
    # tenminste de uitkomst vastgelegd.
    lang = "&lt;DIDL-Lite&gt;" + ("&quot;x&quot; " * 300) + "&lt;/DIDL-Lite&gt;"
    b = mzsonos.attrs('<Alarm ID="9" ProgramMetaData="' + lang + '" Volume="18"')
    equal("attrs overleeft een heel lange waarde", b["ProgramMetaData"], lang)
    equal("en leest wat erachter staat nog", b["Volume"], "18")
    check("de lange waarde is meer dan duizend tekens", len(lang) > 1000)

    c = mzsonos.attrs('<A x-y="1" ns:z="2" A1="3"')
    equal("attrs kent koppeltekens in namen", c["x-y"], "1")
    equal("attrs kent namespaces", c["ns:z"], "2")
    equal("attrs kent cijfers in namen", c["A1"], "3")


# --- 2. Spotify-URI en metadata -------------------------------------------

def test_spotify_uri():
    for gegeven, soort, sleutel in (
        ("https://open.spotify.com/playlist/4EqxTAkrFlaaHE25P9w0IG?si=x",
         "playlist", "4EqxTAkrFlaaHE25P9w0IG"),
        ("spotify:playlist:4EqxTAkrFlaaHE25P9w0IG", "playlist",
         "4EqxTAkrFlaaHE25P9w0IG"),
        ("spotify:album:6wiUBliPe76YAVpNEdidpY", "album",
         "6wiUBliPe76YAVpNEdidpY"),
        ("https://open.spotify.com/track/1301WleyT98MSxVHPZCA6M", "track",
         "1301WleyT98MSxVHPZCA6M"),
    ):
        s, enc = mzsonos.parse_spotify(gegeven)
        equal("soort van " + gegeven[:34], s, soort)
        equal("gecodeerde uri van " + gegeven[:24], enc,
              "spotify%3a" + soort + "%3a" + sleutel)
    equal("niet-Spotify wordt geweigerd",
          mzsonos.parse_spotify("https://youtube.com/x"), (None, None))

    # Deze string is teken voor teken vergeleken met wat SoCo genereert, en die
    # is op vijf echte spelers aanvaard. Verandert hij, dan is dat een bug.
    meta = mzsonos.metadata("playlist", "spotify%3aplaylist%3aXYZ", 2311, "")
    check("metadata heeft de juiste item-id",
          'id="1006206cspotify%3aplaylist%3aXYZ"' in meta)
    check("metadata heeft parentID -1", 'parentID="-1"' in meta)
    check("metadata heeft de cdudn",
          "SA_RINCON2311_X_#Svc2311-0-Token" in meta)
    check("metadata heeft de playlistklasse",
          "object.container.playlistContainer" in meta)
    album = mzsonos.metadata("album", "spotify%3aalbum%3aQ", 2311, "")
    check("album gebruikt 1004206c", 'id="1004206cspotify%3aalbum%3aQ"' in album)
    titel = mzsonos.metadata("playlist", "e", 2311, 'A & B <c>')
    check("titel wordt geescapet in de metadata",
          "A &amp; B &lt;c&gt;" in titel)


# --- 3. zones en transport -------------------------------------------------

def test_zones():
    net = verse_net()
    net.antwoorden["GetZoneGroupState"] = soap_antwoord(
        "<ZoneGroupState>" + mzsonos.esc(ZONE_STATE) + "</ZoneGroupState>")
    zs = run(mzsonos.zones("1.2.3.4"))
    equal("drie zones", len(zs), 3)
    op_naam = dict((z["naam"], z) for z in zs)
    equal("zones staan op naam gesorteerd", [z["naam"] for z in zs],
          ["Bathroom", "Bedroom", "Kitchen"])
    equal("Bathroom is baas", op_naam["Bathroom"]["baas"], True)
    equal("Bedroom is geen baas", op_naam["Bedroom"]["baas"], False)
    equal("Bedroom wijst naar de Kitchen",
          op_naam["Bedroom"]["coordinator"], "RINCON_BBB01400")
    equal("ip komt uit Location", op_naam["Kitchen"]["ip"], "192.168.68.129")


def test_nu_speelt():
    net = verse_net()
    net.antwoorden["GetPositionInfo"] = soap_antwoord(POSITION_INFO)
    nu = run(mzsonos.now("1.2.3.4"))
    equal("titel", nu["titel"], "FE!N")
    equal("artiest", nu["artiest"], "Travis Scott")
    equal("album is de albumtitel, niet de hoes-URL", nu["album"], "UTOPIA")
    equal("duur", nu["duur"], "0:03:11")


def test_radio_titel():
    """Bij radio is dc:title de bestandsnaam van de stream, niet de zender."""
    check("een streambestandsnaam wordt herkend",
          mzsonos.lijkt_stream_id(
              "vrt-radio1-aac-128-4855518?sABC=6n8&amsparams=x"))
    check("een gewone titel niet", not mzsonos.lijkt_stream_id("FE!N"))
    check("een lange titel met spaties ook niet",
          not mzsonos.lijkt_stream_id("Bohemian Rhapsody, remastered edition"))
    check("leeg is geen stream-id", not mzsonos.lijkt_stream_id(""))

    net = verse_net()
    net.antwoorden["GetPositionInfo"] = soap_antwoord(
        "<TrackMetaData>" + mzsonos.esc(
            "<DIDL-Lite><item><r:streamContent></r:streamContent>"
            "<dc:title>vrt-radio1-aac-128-4855518?sABC=6n8</dc:title>"
            "</item></DIDL-Lite>") + "</TrackMetaData>")
    net.antwoorden["GetMediaInfo"] = soap_antwoord(
        "<CurrentURIMetaData>" + mzsonos.esc(
            "<DIDL-Lite><item><dc:title>VRT Radio 1</dc:title>"
            "<upnp:class>object.item.audioItem.audioBroadcast</upnp:class>"
            "</item></DIDL-Lite>") + "</CurrentURIMetaData>")
    nu = run(mzsonos.now("1.2.3.4"))
    equal("de zendernaam komt op het scherm", nu["titel"], "VRT Radio 1")

    net = verse_net()
    net.antwoorden["GetPositionInfo"] = soap_antwoord(
        "<TrackMetaData>" + mzsonos.esc(
            "<DIDL-Lite><item>"
            "<r:streamContent>Yasmine - Ik hou van u</r:streamContent>"
            "<dc:title>vrt-radio1-aac-128?x=1</dc:title></item></DIDL-Lite>")
        + "</TrackMetaData>")
    net.antwoorden["GetMediaInfo"] = soap_antwoord(
        "<CurrentURIMetaData>" + mzsonos.esc(
            "<DIDL-Lite><item><dc:title>VRT Radio 1</dc:title></item></DIDL-Lite>")
        + "</CurrentURIMetaData>")
    nu = run(mzsonos.now("1.2.3.4"))
    equal("wat er klinkt staat voorop", nu["titel"], "Yasmine - Ik hou van u")
    equal("en de zender als artiest", nu["artiest"], "VRT Radio 1")

    # Spotify uit de wachtrij: geen streamContent, dc:title klopt gewoon, en er
    # mag dan geen extra call naar GetMediaInfo gaan.
    net = verse_net()
    net.antwoorden["GetPositionInfo"] = soap_antwoord(POSITION_INFO)
    nu = run(mzsonos.now("1.2.3.4"))
    equal("een gewone titel blijft staan", nu["titel"], "FE!N")
    check("en er is geen extra call nodig",
          "GetMediaInfo" not in net.acties)


def test_upnp_fout():
    net = verse_net()
    net.antwoorden["Play"] = (500, "<errorCode>701</errorCode>")
    try:
        run(mzsonos.play("1.2.3.4"))
        check("UPnP-fout wordt opgegooid", False)
    except mzsonos.SonosError as e:
        check("de foutcode staat in de boodschap", "701" in str(e))


# --- 4. afspelen: de volgorde is de test ----------------------------------

def test_play_spotify_volgorde():
    net = verse_net()
    net.antwoorden["AddURIToQueue"] = soap_antwoord(
        "<NumTracksAdded>16</NumTracksAdded>")
    net.antwoorden["ListAvailableServices"] = soap_antwoord(
        "<AvailableServiceDescriptorList>"
        + mzsonos.esc('<Service Id="9" Name="Spotify"/>')
        + "</AvailableServiceDescriptorList>")
    aantal = run(mzsonos.play_spotify("1.2.3.4", "spotify:playlist:XYZ",
                                      shuffle=True, titel="Oki",
                                      speler_uid="RINCON_ZZZ01400"))
    equal("aantal toegevoegde nummers", aantal, 16)

    volgorde = [a for a in net.acties if a in (
        "RemoveAllTracksFromQueue", "AddURIToQueue", "SetAVTransportURI",
        "SetPlayMode", "Seek", "Play")]
    equal("de volgorde van de vijf calls", volgorde,
          ["RemoveAllTracksFromQueue", "AddURIToQueue", "SetAVTransportURI",
           "SetPlayMode", "Seek", "Play"])
    # Op hardware: SetPlayMode voor SetAVTransportURI geeft UPnP 712, omdat de
    # speelmodus bij de wachtrij hoort en die dan nog niet de bron is.
    check("SetPlayMode komt na SetAVTransportURI",
          volgorde.index("SetPlayMode") > volgorde.index("SetAVTransportURI"))

    body = net.soap_body("AddURIToQueue")
    check("de enqueue-uri heeft de containerprefix",
          "x-rincon-cpcontainer:1006206cspotify%3aplaylist%3aXYZ" in body)
    # De DIDL zit in de envelope en moet dus geescapet zijn; rauw meesturen
    # levert een envelope op die de speler aanneemt en dan negeert.
    check("de metadata is geescapet in de envelope", "&lt;DIDL-Lite" in body)
    check("er staat geen rauwe DIDL in de envelope",
          "<DIDL-Lite" not in body)
    check("het servicenummer is uitgerekend uit Id 9",
          "SA_RINCON2311" in body)

    speelmodus = net.soap_body("SetPlayMode")
    check("shuffle wordt doorgegeven", "SHUFFLE" in speelmodus)
    transport = net.soap_body("SetAVTransportURI")
    check("de wachtrij wordt de bron",
          "x-rincon-queue:RINCON_ZZZ01400#0" in transport)


def test_verdwenen_playlist():
    """804 komt in de praktijk van een playlist die bij Spotify weg is."""
    net = verse_net()
    net.antwoorden["ListAvailableServices"] = soap_antwoord(
        "<AvailableServiceDescriptorList></AvailableServiceDescriptorList>")
    net.antwoorden["AddURIToQueue"] = (500, "<errorCode>804</errorCode>")
    try:
        run(mzsonos.play_spotify("1.2.3.4", "spotify:playlist:WEG",
                                 speler_uid="RINCON_Z"))
        check("804 wordt opgegooid", False)
    except mzsonos.SonosError as e:
        equal("804 krijgt een leesbare boodschap", str(e),
              "Spotify kent deze lijst niet meer")


def test_servicenummer():
    net = verse_net()
    net.antwoorden["ListAvailableServices"] = soap_antwoord(
        "<AvailableServiceDescriptorList>"
        + mzsonos.esc('<Service Id="12" Name="Spotify"/>'
                      '<Service Id="254" Name="TuneIn"/>')
        + "</AvailableServiceDescriptorList>")
    equal("Id 12 geeft 3079", run(mzsonos.spotify_sn("1.2.3.4")), 3079)
    net = verse_net()
    net.antwoorden["ListAvailableServices"] = soap_antwoord(
        "<AvailableServiceDescriptorList>"
        + mzsonos.esc('<Service Id="254" Name="TuneIn"/>')
        + "</AvailableServiceDescriptorList>")
    equal("zonder Spotify de terugval", run(mzsonos.spotify_sn("1.2.3.4")), 2311)


def test_favorieten():
    net = verse_net()
    net.antwoorden["Browse"] = soap_antwoord("<Result>" + FAVORITES_DIDL + "</Result>")
    favs = run(mzsonos.favorites("1.2.3.4"))
    equal("alleen favorieten met een res", len(favs), 1)
    equal("titel", favs[0]["titel"], "Oki")
    check("res is een containerlink",
          favs[0]["res"].startswith("x-rincon-cpcontainer:1006286c"))
    check("resMD is meegenomen", "Oki" in favs[0]["resmd"])


# --- 5. wekkers ------------------------------------------------------------

def test_alarmen_lezen():
    net = verse_net()
    net.antwoorden["ListAlarms"] = soap_antwoord(
        "<CurrentAlarmList>" + mzsonos.esc(ALARM_LIST) + "</CurrentAlarmList>")
    allemaal = run(mzsonos.alarms("1.2.3.4"))
    equal("drie alarmen in het huishouden", len(allemaal), 3)

    net = verse_net()
    net.antwoorden["ListAlarms"] = soap_antwoord(
        "<CurrentAlarmList>" + mzsonos.esc(ALARM_LIST) + "</CurrentAlarmList>")
    mijne = run(mzsonos.alarms("1.2.3.4", room_uuid="RINCON_CCC01400"))
    equal("twee voor deze kamer", len(mijne), 2)
    equal("op tijd gesorteerd", [a["tijd"] for a in mijne], ["06:59", "07:15"])
    equal("tijd zonder seconden", mijne[0]["tijd"], "06:59")
    equal("uit staat uit", mijne[0]["aan"], False)
    equal("bron uit de metadata", mijne[0]["bron"], "VRT Radio 1")
    equal("zonder metadata het wekgeluid", mijne[1]["bron"], "wekgeluid")
    equal("volume", mijne[0]["volume"], 5)


def test_herhaling_tekst():
    equal("weekdagen", mzsonos.recurrence_text("WEEKDAYS"), "weekdagen")
    equal("eenmalig", mzsonos.recurrence_text("ONCE"), "eenmalig")
    equal("elke dag", mzsonos.recurrence_text("DAILY"), "elke dag")
    equal("ON_06 is het weekend", mzsonos.recurrence_text("ON_06"), "zz")
    equal("ON_12345 zijn de weekdagen",
          mzsonos.recurrence_text("ON_12345"), "mdwdv")
    equal("leeg ON_ is eenmalig", mzsonos.recurrence_text("ON_"), "eenmalig")


def test_tijd_verschuiven():
    equal("vijf erbij", mzsonos._shift_time("07:00", 5), "07:05")
    equal("vijf eraf", mzsonos._shift_time("07:00", -5), "06:55")
    equal("over het uur", mzsonos._shift_time("07:55", 10), "08:05")
    equal("over middernacht", mzsonos._shift_time("23:58", 5), "00:03")
    equal("onder middernacht", mzsonos._shift_time("00:02", -5), "23:57")


def test_alarm_bijwerken():
    net = verse_net()
    net.antwoorden["ListAlarms"] = soap_antwoord(
        "<CurrentAlarmList>" + mzsonos.esc(ALARM_LIST) + "</CurrentAlarmList>")
    alarm = run(mzsonos.alarms("1.2.3.4", room_uuid="RINCON_CCC01400"))[0]

    net.acties = []
    net.calls = []
    run(mzsonos.update_alarm("1.2.3.4", alarm, aan=True, tijd="07:30"))
    body = net.soap_body("UpdateAlarm")

    # ListAlarms noemt het veld StartTime, UpdateAlarm noemt het
    # StartLocalTime. Wie dat verwart stuurt een leeg tijdveld en het alarm
    # springt naar middernacht.
    check("UpdateAlarm gebruikt StartLocalTime",
          "<StartLocalTime>07:30:00</StartLocalTime>" in body)
    check("StartTime staat er niet in", "<StartTime>" not in body)
    check("aan wordt 1", "<Enabled>1</Enabled>" in body)
    check("het ID gaat mee", "<ID>1</ID>" in body)
    for veld in ("Duration", "Recurrence", "RoomUUID", "ProgramURI",
                 "ProgramMetaData", "PlayMode", "Volume", "IncludeLinkedZones"):
        check("UpdateAlarm stuurt %s terug" % veld, ("<%s>" % veld) in body)
    check("de duur blijft staan", "<Duration>00:25:00</Duration>" in body)
    check("de herhaling blijft staan", "<Recurrence>WEEKDAYS</Recurrence>" in body)

    # ProgramMetaData komt geescapet uit ListAlarms en moet ontescapet mee, want
    # soap() escapet zelf. Twee keer escapen maakt er &amp;lt; van en dan
    # verliest het alarm zijn radiozender.
    check("de metadata is precies een keer geescapet",
          "&lt;DIDL-Lite&gt;" in body and "&amp;lt;DIDL-Lite" not in body)

    equal("de lokale kopie is bijgewerkt", alarm["tijd"], "07:30")
    equal("en staat aan", alarm["aan"], True)

    net.calls = []
    run(mzsonos.update_alarm("1.2.3.4", alarm, aan=False))
    body = net.soap_body("UpdateAlarm")
    check("uitschakelen laat de tijd staan",
          "<StartLocalTime>07:30:00</StartLocalTime>" in body)
    check("en zet Enabled op 0", "<Enabled>0</Enabled>" in body)


# --- 6. Spotify Web API ----------------------------------------------------

def test_spotify_playlists():
    net = verse_net()
    mzspotify._token = None
    mzspotify._token_tot = None
    net.http_antwoorden[("accounts.spotify.com", "/api/token")] = (
        200, json.dumps({"access_token": "AT", "expires_in": 3600}))
    pagina2 = "https://api.spotify.com/v1/me/playlists?offset=50&limit=50"
    net.http_antwoorden[("api.spotify.com", "/v1/me/playlists")] = (
        200, json.dumps({"items": [
            {"name": "Oki", "uri": "spotify:playlist:OKI", "tracks": {"total": 16}},
            None,
            {"name": "Ochtend", "uri": "spotify:playlist:OCH", "tracks": {"total": 20}},
        ], "next": None}))
    lijst = run(mzspotify.playlists("cid", "rt"))
    equal("twee playlists, de None overgeslagen", len(lijst), 2)
    equal("naam", lijst[0]["naam"], "Oki")
    equal("uri", lijst[0]["uri"], "spotify:playlist:OKI")
    equal("aantal nummers", lijst[0]["aantal"], 16)

    token_call = [c for c in net.calls if c[2] == "/api/token"][0]
    check("het refresh token gaat in de body mee",
          "grant_type=refresh_token" in token_call[3] and "refresh_token=rt" in token_call[3])
    lijst_call = [c for c in net.calls if c[2].startswith("/v1/me/playlists")][0]
    equal("de playlists gaan naar api.spotify.com", lijst_call[0], "api.spotify.com")
    check("pagina2 is opgezet maar niet nodig", pagina2 is not None)


def test_spotify_zonder_config():
    mzspotify._token = None
    try:
        run(mzspotify.access_token("", ""))
        check("zonder sleutels een nette fout", False)
    except mzspotify.SpotifyError as e:
        equal("de boodschap is voor het scherm", str(e), "Spotify is niet ingesteld")


def test_cache_pad():
    """De badge heeft geen /cache, ook al noemen de docs het. Gemeten:
    [Errno 2] ENOENT bij elke poging de playlists te bewaren."""
    oud = mzspotify.CACHE_MAPPEN
    try:
        mzspotify.CACHE_MAPPEN = ("/bestaat/niet", "/tmp")
        pad = mzspotify.cache_pad()
        check("valt terug op een map die er wel is",
              pad == "/tmp/" + mzspotify.CACHE_BESTAND)
        mzspotify.CACHE_MAPPEN = ("/bestaat/niet/en/valt/niet/te/maken",)
        equal("zonder bruikbare map geeft hij None", mzspotify.cache_pad(), None)
    finally:
        mzspotify.CACHE_MAPPEN = oud


def test_cache_zonder_pad_zwijgt():
    oud = mzspotify.CACHE
    try:
        mzspotify.CACHE = None
        equal("lezen zonder cache geeft leeg", mzspotify.cache_lezen(), [])
        equal("schrijven zonder cache is geen fout",
              mzspotify.cache_schrijven([{"naam": "A"}]), False)
    finally:
        mzspotify.CACHE = oud


def test_spotify_cache(tmp="/tmp/muziek_playlists_test.json"):
    oud = mzspotify.CACHE
    mzspotify.CACHE = tmp
    try:
        check("schrijven lukt", mzspotify.cache_schrijven([{"naam": "A"}]))
        equal("en lezen geeft het terug", mzspotify.cache_lezen(), [{"naam": "A"}])
        mzspotify.CACHE = "/nergens/dat/bestaat/x.json"
        equal("een onleesbare cache is geen fout", mzspotify.cache_lezen(), [])
        equal("een onschrijfbare cache ook niet",
              mzspotify.cache_schrijven([{"naam": "A"}]), False)
    finally:
        mzspotify.CACHE = oud
        try:
            os.remove(tmp)
        except OSError:
            pass


# --- 7. toestand -----------------------------------------------------------

def verse_state():
    state.zones = []
    state.zone = None
    state.lijsten = []
    state.favorieten = []
    state.wekkers = []
    state.speler = {"staat": "", "titel": "", "artiest": "", "volume": 0}
    state.status = ""
    state.bezig = 0
    state.spotify_klaar = False
    import mpos.config
    mpos.config._STORE.clear()


def test_zone_keuze_wordt_onthouden():
    verse_state()
    net = verse_net()
    net.antwoorden["GetZoneGroupState"] = soap_antwoord(
        "<ZoneGroupState>" + mzsonos.esc(ZONE_STATE) + "</ZoneGroupState>")
    net.antwoorden["GetPositionInfo"] = soap_antwoord(POSITION_INFO)

    run(state.zoek_zones())
    equal("zonder voorkeur de eerste box", state.zone["naam"], "Bathroom")

    kitchen = [z for z in state.zones if z["naam"] == "Kitchen"][0]
    state.kies_zone(kitchen)
    equal("de keuze is bewaard op uid",
          state.prefs_lezen()["uid"], "RINCON_BBB01400")

    # Nieuwe sessie: zones opnieuw ophalen, met een ander IP voor dezelfde box.
    verse_state_zonder_prefs = state.zone
    state.zones = []
    state.zone = None
    run(state.zoek_zones())
    equal("de vorige keuze komt terug", state.zone["naam"], "Kitchen")
    check("en het is een verse dict", state.zone is not verse_state_zonder_prefs)


def test_gegroepeerde_box_stuurt_naar_de_baas():
    verse_state()
    net = verse_net()
    net.antwoorden["GetZoneGroupState"] = soap_antwoord(
        "<ZoneGroupState>" + mzsonos.esc(ZONE_STATE) + "</ZoneGroupState>")
    run(state.zoek_zones())
    bedroom = [z for z in state.zones if z["naam"] == "Bedroom"][0]
    state.kies_zone(bedroom)
    baas = state.zone_baas()
    # Een slaaf weigert Play met UPnP 701. Het commando hoort naar de baas.
    equal("de baas van de groep is de Kitchen", baas["naam"], "Kitchen")
    equal("en dus het IP van de Kitchen", baas["ip"], "192.168.68.129")

    bathroom = [z for z in state.zones if z["naam"] == "Bathroom"][0]
    state.kies_zone(bathroom)
    equal("een box die alleen staat is zijn eigen baas",
          state.zone_baas()["naam"], "Bathroom")


def test_geen_sonos():
    verse_state()
    net = verse_net()

    async def geen(ms=0):
        return {}
    mzsonos.discover = geen
    run(state.zoek_zones())
    equal("geen zones", state.zones, [])
    equal("en het scherm zegt het", state.status, "geen Sonos gevonden")
    equal("zone_baas valt niet om", state.zone_baas(), None)


def test_taak_vangt_fouten():
    verse_state()
    boodschappen = []

    async def stuk():
        raise mzsonos.SonosError("box weg")

    async def draaien():
        t = state.taak(stuk())
        await t
    run(draaien())
    equal("de fout staat in de statusregel", state.status, "box weg")
    equal("en er loopt niets meer", state.bezig, 0)
    check("boodschappen ongebruikt", boodschappen == [])


# --- 8. schermen -----------------------------------------------------------

class Opgevangen:
    """Vervangt state.taak zodat een test ziet welke coroutine gevraagd wordt."""

    def __init__(self):
        self.namen = []
        self.coros = []

    def __call__(self, coro, klaar=None):
        naam = getattr(coro, "__name__", None)
        if naam is None:
            naam = getattr(getattr(coro, "cr_code", None), "co_name", "?")
        self.namen.append(naam)
        self.coros.append(coro)
        try:
            coro.close()
        except Exception:
            pass
        return None


def met_scherm(klasse):
    verse_state()
    opgevangen = Opgevangen()
    echt = state.taak
    state.taak = opgevangen
    scherm = klasse()
    scherm.onCreate()
    scherm.onResume(scherm._view)
    return scherm, opgevangen, echt


def alle_knoppen(obj, uit=None):
    """Alles wat op een tik reageert. Een schakelaar hangt aan VALUE_CHANGED en
    telt hier dus niet mee, anders zou een rij met een schakelaar erbij een knop
    lijken te hebben die er niet is."""
    if uit is None:
        uit = []
    for kind in getattr(obj, "children", []):
        for cb, code in kind.cbs:
            if code == lv.EVENT.CLICKED:
                uit.append(kind)
                break
        alle_knoppen(kind, uit)
    return uit


def test_speler_scherm():
    scherm, taken, echt = met_scherm(Muziek)
    try:
        equal("bij het eerste tonen wordt er opgestart", taken.namen, ["opstarten"])
        knoppen = alle_knoppen(scherm._view)
        equal("acht knoppen: naam, verversen, drie transport, twee volume, "
              "playlists en wekkers", len(knoppen), 9)
        for k in knoppen:
            if k.size:
                check("knop is minstens 38 hoog, anders mis je hem met een vinger",
                      k.size[1] >= 38)

        state.zones = [{"uid": "U1", "ip": "1.2.3.4", "naam": "Keuken",
                        "baas": True, "coordinator": "U1"}]
        state.zone = state.zones[0]
        state.speler = {"staat": "PLAYING", "titel": "FE!N",
                        "artiest": "Travis Scott", "volume": 22}
        state.status = "klaar"
        state._wijzig()
        scherm._teken()
        equal("de boxnaam staat op de knop", scherm.naam_label.text, "Keuken")
        equal("de titel staat er", scherm.titel.text, "FE!N")
        equal("de artiest ook", scherm.artiest.text, "Travis Scott")
        equal("en het volume", scherm.vol_label.text, "vol 22")
        equal("de speelknop toont pauze terwijl het speelt",
              scherm.speel_label.text, ui.SYM_PAUSE)

        state.speler["staat"] = "PAUSED_PLAYBACK"
        state._wijzig()
        scherm._teken()
        equal("en play als het stil is", scherm.speel_label.text, ui.SYM_PLAY)

        state.speler = {"staat": "STOPPED", "titel": "", "artiest": "", "volume": 3}
        state._wijzig()
        scherm._teken()
        equal("zonder titel een nette zin", scherm.titel.text, "niets aan het spelen")
        equal("en de staat waar de artiest stond", scherm.artiest.text, "gestopt")

        taken.namen = []
        knoppen[2].click()          # eerste transportknop is vorige
        equal("vorige start een taak", len(taken.namen), 1)
    finally:
        state.taak = echt
        scherm.onPause(scherm._view)


def test_speler_zonder_zone_opent_niets():
    scherm, taken, echt = met_scherm(Muziek)
    try:
        state.zone = None
        state._wijzig()
        scherm._teken()
        equal("zonder box zegt de knop dat", scherm.naam_label.text, "geen box")
        voor = len(mpos.STARTED)
        scherm._open_lijsten()
        scherm._open_wekkers()
        equal("en de vervolgschermen gaan niet open", len(mpos.STARTED), voor)
        scherm._open_zones()
        equal("de boxenlijst wel", len(mpos.STARTED), voor + 1)
    finally:
        state.taak = echt
        scherm.onPause(scherm._view)


def test_zones_scherm():
    scherm, taken, echt = met_scherm(MuziekZones)
    try:
        equal("een leeg scherm gaat zelf zoeken", taken.namen, ["zoek_zones"])
        state.zones = [
            {"uid": "U1", "ip": "1.1.1.1", "naam": "Keuken", "baas": True,
             "coordinator": "U1"},
            {"uid": "U2", "ip": "2.2.2.2", "naam": "Slaapkamer", "baas": False,
             "coordinator": "U1"},
        ]
        state.zone = state.zones[0]
        state._wijzig()
        scherm._teken()
        knoppen = alle_knoppen(scherm.lijst)
        equal("een rij per box", len(knoppen), 2)
        labels = [k.children[0].text for k in knoppen]
        equal("de gekozen box is gemerkt", labels[0], "> Keuken")
        check("een gegroepeerde box zegt dat erbij",
              "gegroepeerd" in labels[1])

        taken.namen = []
        knoppen[1].click()
        equal("kiezen zet de zone", state.zone["naam"], "Slaapkamer")
        equal("en bewaart hem", state.prefs_lezen()["uid"], "U2")
        equal("en ververst de speler", taken.namen, ["ververs_speler"])
    finally:
        state.taak = echt
        scherm.onPause(scherm._view)


def test_playlists_scherm():
    scherm, taken, echt = met_scherm(MuziekLijsten)
    try:
        equal("met Spotify ingesteld begint hij daar", scherm._bron, "spotify")
        equal("en haalt hij de lijsten op", taken.namen, ["ververs_lijsten"])
        state.zones = [{"uid": "U1", "ip": "1.1.1.1", "naam": "Keuken",
                        "baas": True, "coordinator": "U1"}]
        state.zone = state.zones[0]
        state.lijsten = [{"naam": "Ochtend", "uri": "spotify:playlist:A",
                          "aantal": 20},
                         {"naam": "Feest", "uri": "spotify:playlist:B",
                          "aantal": 41}]
        state._wijzig()
        scherm._teken()
        knoppen = alle_knoppen(scherm.lijst)
        equal("een rij per playlist", len(knoppen), 2)
        equal("naam en aantal", knoppen[0].children[0].text, "Ochtend  (20)")

        # Spotify geeft voor Maartens playlists geen bruikbare tracks.total,
        # dus stond er overal "(0)". Een nul die "onbekend" betekent is erger
        # dan helemaal geen getal.
        state.lijsten = [{"naam": "Zonder telling", "uri": "spotify:playlist:C",
                          "aantal": 0}]
        state._wijzig()
        scherm._teken()
        knoppen = alle_knoppen(scherm.lijst)
        equal("een aantal van nul komt niet op het scherm",
              knoppen[0].children[0].text, "Zonder telling")
        state.lijsten = [{"naam": "Zonder veld", "uri": "spotify:playlist:D"}]
        state._wijzig()
        scherm._teken()
        knoppen = alle_knoppen(scherm.lijst)
        equal("en een ontbrekend veld ook niet",
              knoppen[0].children[0].text, "Zonder veld")

        state.lijsten = [{"naam": "Ochtend", "uri": "spotify:playlist:A",
                          "aantal": 20},
                         {"naam": "Feest", "uri": "spotify:playlist:B",
                          "aantal": 41}]
        state._wijzig()
        scherm._teken()
        knoppen = alle_knoppen(scherm.lijst)

        taken.namen = []
        knoppen[0].click()
        equal("tikken speelt de lijst", taken.namen, ["speel_lijst"])

        scherm._wissel_bron()
        equal("de knop wisselt naar favorieten", scherm._bron, "favorieten")
        equal("en die worden opgehaald", taken.namen[-1], "ververs_favorieten")
        state.favorieten = [{"titel": "VRT Radio 1", "res": "x-sonosapi:1",
                             "resmd": ""}]
        state._wijzig()
        scherm._teken()
        knoppen = alle_knoppen(scherm.lijst)
        equal("een rij per favoriet", len(knoppen), 1)
        taken.namen = []
        knoppen[0].click()
        equal("tikken speelt de favoriet", taken.namen, ["speel_favoriet"])
    finally:
        state.taak = echt
        scherm.onPause(scherm._view)


def test_wekkers_scherm():
    scherm, taken, echt = met_scherm(MuziekWekkers)
    try:
        equal("een leeg scherm haalt de wekkers op", taken.namen, ["ververs_wekkers"])
        state.zones = [{"uid": "U1", "ip": "1.1.1.1", "naam": "Slaapkamer",
                        "baas": True, "coordinator": "U1"}]
        state.zone = state.zones[0]
        state.wekkers = [{"id": "1", "tijd": "06:59", "duur": "00:25:00",
                          "herhaling": "WEEKDAYS", "aan": False,
                          "room": "U1", "volume": 5, "bron": "VRT Radio 1",
                          "_ruw": {"ID": "1"}}]
        state._wijzig()
        scherm._teken()
        check("de kop noemt de box", "Slaapkamer" in scherm.kop_label.text)
        knoppen = alle_knoppen(scherm.lijst)
        equal("min en plus per wekker", len(knoppen), 2)

        taken.namen = []
        knoppen[1].click()
        equal("plus verschuift de tijd", taken.namen, ["zet_wekker"])

        # De schakelaar hangt aan VALUE_CHANGED, niet aan CLICKED.
        schakelaars = []

        def zoek(o):
            for k in getattr(o, "children", []):
                for cb, code in k.cbs:
                    if code == lv.EVENT.VALUE_CHANGED:
                        schakelaars.append((k, cb))
                zoek(k)
        zoek(scherm.lijst)
        equal("een schakelaar per wekker", len(schakelaars), 1)
        sw, cb = schakelaars[0]
        equal("een uitgeschakelde wekker staat uit",
              sw.has_state(lv.STATE.CHECKED), False)
        taken.namen = []
        sw.add_state(lv.STATE.CHECKED)
        cb(None)
        equal("omzetten start een taak", taken.namen, ["zet_wekker"])
    finally:
        state.taak = echt
        scherm.onPause(scherm._view)


# --- 9. wat MicroPython niet heeft -----------------------------------------

ONTBREKENDE_STR = (
    "capitalize", "casefold", "expandtabs", "format_map", "isdecimal",
    "isidentifier", "isprintable", "ljust", "maketrans", "removeprefix",
    "removesuffix", "rjust", "swapcase", "title", "translate", "zfill",
)

# re op deze build heeft alleen search/match/compile/sub. finditer en findall
# bestaan niet, en een test op desktop merkt dat nooit: daar bestaan ze wel.
ONTBREKENDE_RE = ("finditer", "findall", "fullmatch", "escape")


def test_alleen_bestaande_methodes():
    app = os.path.join(ROOT, "be.weyn.muziek")
    for bestand in sorted(os.listdir(app)):
        if not bestand.endswith(".py"):
            continue
        with open(os.path.join(app, bestand)) as f:
            bron = f.read()
        for naam in ONTBREKENDE_STR:
            check("%s gebruikt str.%s, dat MicroPython niet heeft"
                  % (bestand, naam), ("." + naam + "(") not in bron)
        for naam in ONTBREKENDE_RE:
            check("%s gebruikt re.%s, dat MicroPython niet heeft"
                  % (bestand, naam), ("re." + naam + "(") not in bron)
        check("%s gebruikt geen f-strings" % bestand,
              'f"' not in bron and "f'" not in bron)
        # De MicroPython-compiler onderschept een module-level NAAM = const(...)
        # als constantendeclaratie en eist dan een constante uitdrukking. Een
        # eigen functie die const heet laat de hele module omvallen met
        # SyntaxError: not a constant, voor er ook maar iets draait. Op desktop
        # merk je daar niets van, dus staat de wacht hier.
        check("%s definieert geen functie die const heet" % bestand,
              "def const(" not in bron)
        for regel in bron.split("\n"):
            gestript = regel.strip()
            if gestript.startswith("#") or "`" in gestript:
                continue          # commentaar en docstrings mogen het noemen
            if " = const(" not in gestript:
                continue
            check("%s: %s wordt door de compiler als constante gelezen"
                  % (bestand, gestript[:40]), False)


def test_geen_geheimen_in_de_repo():
    """Het sjabloon hoort in git, de ingevulde kopie niet."""
    app = os.path.join(ROOT, "be.weyn.muziek")
    check("het sjabloon bestaat",
          os.path.exists(os.path.join(app, "muziek_config.example.py")))
    with open(os.path.join(ROOT, ".gitignore")) as f:
        genegeerd = f.read()
    check("muziek_config.py staat in .gitignore",
          "be.weyn.muziek/muziek_config.py" in genegeerd)
    with open(os.path.join(app, "muziek_config.example.py")) as f:
        sjabloon = f.read()
    # Een sjabloon met een echte sleutel erin is precies wat we willen vermijden.
    for regel in sjabloon.split("\n"):
        if regel.startswith("SPOTIFY_"):
            check("het sjabloon staat leeg: " + regel,
                  regel.endswith('= ""'))


def test_manifest():
    with open(os.path.join(ROOT, "be.weyn.muziek", "MANIFEST.JSON")) as f:
        m = json.load(f)
    equal("fullname klopt met de map", m["fullname"], "be.weyn.muziek")
    equal("de launcher start muziek.py", m["activities"][0]["entrypoint"],
          "muziek.py")
    equal("met klasse Muziek", m["activities"][0]["classname"], "Muziek")
    check("hij staat in de launcher",
          {"action": "main", "category": "launcher"}
          in m["activities"][0]["intent_filters"])
    equal("het prefs-id is het app-id", state.PREFS_APP_ID, m["fullname"])


# --- uitvoeren -------------------------------------------------------------

def main():
    for naam, fn in sorted(globals().items()):
        if naam.startswith("test_") and callable(fn):
            fn()
            mzsonos.http = ECHTE_HTTP
            mzsonos.discover = ECHTE_DISCOVER
    print("\n%d checks, %d mislukt" % (CHECKS["n"], len(FAILURES)))
    for f in FAILURES:
        print("  -", f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
