"""Offline tests voor de Updates-app (tech.weyn.updates).

Draait op gewone Python tegen de stubs in tests/stubs/, zodat de hele keten van
index tot geinstalleerde versie na te kijken is zonder badge, zonder server en
zonder een uur te wachten.

    python3 tests/test_autoupdate.py

Wat hier bewaakt wordt en waarom:

- **Er is geen toestand waarin de service kan blijven hangen.** Dat is de fout
  die OSUpdate op deze badges maakte, met een `WAITING_WIFI` die na een enkele
  koude DNS-misser nooit meer terugkwam. Een mislukte controle hoort na een
  minuut een nieuwe te krijgen, niet het einde te zijn.
- **Een pakket dat niet aankomt mag de andere niet meenemen.**
- **De app die op het scherm staat wordt niet onder de vinger vandaan
  vervangen.**
"""

import asyncio
import json
import os
import sys
import types

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP_DIR = os.path.join(ROOT, "tech.weyn.updates")
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, APP_DIR)

import lvgl as lv                                     # noqa: E402
import mpos                                           # noqa: E402
import mpos.config                                    # noqa: E402
import mpos.ui                                        # noqa: E402

import autoupdate_service as service                  # noqa: E402
import autoupdate as screen                           # noqa: E402
from autoupdate_service import AutoUpdateService      # noqa: E402

FAILURES = []
CHECKS = {"n": 0}


def check(label, condition):
    CHECKS["n"] += 1
    if not condition:
        FAILURES.append(label)
        print("FAIL:", label)


def equal(label, got, want):
    check("%s (got %r, want %r)" % (label, got, want), got == want)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


INDEX = "http://ha.example:8123/local/appstore/app_index.json"
BASE = "http://ha.example:8123/local/appstore/"


def entry(fullname, version, url=None, size=0, services=False,
          replaces=None):
    item = {
        "fullname": fullname,
        "name": fullname.split(".")[-1],
        "version": version,
        "download_url": url if url is not None
        else "mpks/%s_%s.mpk" % (fullname, version),
    }
    if size:
        item["download_url_size"] = size
    if services:
        item["services"] = [{"entrypoint": "svc.py", "classname": "Svc"}]
    if replaces:
        item["replaces"] = replaces
    return item


def publish(entries):
    """Zet een index klaar, plus een pakket per regel."""
    mpos.DownloadManager.responses[INDEX] = json.dumps(entries).encode()
    for item in entries:
        url = item["download_url"]
        if url.find("://") < 0:
            url = BASE + url
        mpos.DownloadManager.responses[url] = ("mpk:" + item["version"]).encode()


def fresh(auto=True):
    """Een schone badge: niets geinstalleerd, niets gedownload, geen log."""
    mpos.AppManager.reset()
    mpos.DownloadManager.reset()
    mpos.NotificationManager.reset()
    mpos.TaskManager.reset()
    mpos.config._STORE.clear()
    sys.modules.pop("badge_service", None)
    service.index_url = INDEX
    service.auto_install = auto
    service.poll_interval_s = service.POLL_INTERVAL_S
    service.state = "idle"
    service.last_check = 0
    service.last_error = ""
    service.last_run = []
    service.catalog = {}
    service.reboot_advised = False
    service._busy = False
    service._running = False


# ===========================================================================
# Versies vergelijken
# ===========================================================================

equal("een gewone versie wordt een tupel", service.parse_version("0.4.1"),
      (0, 4, 1))
equal("twee delen worden er drie", service.parse_version("1.2"), (1, 2, 0))
# Een release-kandidaat is geen versie die AppManager kan vergelijken. Beter
# dat 0.4.0-rc1 als 0.4.0 telt dan dat de hele controle op een ValueError valt.
equal("een achtervoegsel telt niet mee", service.parse_version("0.4.0-rc1"),
      (0, 4, 0))
equal("onzin telt als nul", service.parse_version("later"), (0, 0, 0))

check("hoger is nieuwer", service.is_newer("0.5.0", "0.4.9"))
check("gelijk is niet nieuwer", not service.is_newer("0.4.0", "0.4.0"))
check("lager is niet nieuwer", not service.is_newer("0.3.0", "0.4.0"))
check("tien komt na negen", service.is_newer("0.10.0", "0.9.0"))


# ===========================================================================
# URL's
# ===========================================================================

equal("een relatieve download hangt aan de index",
      service.absolute_url("mpks/a.mpk", INDEX), BASE + "mpks/a.mpk")
equal("een absoluut pad vervangt alles na de host",
      service.absolute_url("/media/a.mpk", INDEX),
      "http://ha.example:8123/media/a.mpk")
equal("een volledige URL blijft staan",
      service.absolute_url("https://elders/a.mpk", INDEX),
      "https://elders/a.mpk")
equal("een lege URL blijft leeg", service.absolute_url("", INDEX), "")

equal("de host van een URL past op een knop",
      screen.host_of(INDEX), "ha.example:8123")
equal("een URL zonder pad ook", screen.host_of("http://192.168.68.100:8123"),
      "192.168.68.100:8123")


# ===========================================================================
# De ruimte op de flash
# ===========================================================================

_echte_vrije_ruimte = service.free_bytes
service.free_bytes = lambda: 200 * 1024
check("een pakket van 40 KB past in 200 KB", service.enough_space(40 * 1024))
check("een pakket van 90 KB niet, want het staat er even dubbel op",
      not service.enough_space(90 * 1024))
service.free_bytes = lambda: -1
check("onbekende ruimte telt als genoeg, liever proberen dan weigeren",
      service.enough_space(9_000_000))
service.free_bytes = _echte_vrije_ruimte
check("een maat van nul weigert nooit", service.enough_space(0))


# ===========================================================================
# De controle zelf
# ===========================================================================

fresh()
mpos.AppManager.preinstall("tech.weyn.muziek", "0.1.0")
mpos.AppManager.preinstall("tech.weyn.pomodoro", "0.3.1")
publish([
    entry("tech.weyn.muziek", "0.2.0"),
    entry("tech.weyn.pomodoro", "0.3.1"),
    entry("tech.weyn.nieuw", "1.0.0"),
])

equal("de controle lukt", run(service.check_now()), True)
equal("muziek is bijgewerkt",
      mpos.AppManager.get("tech.weyn.muziek").version, "0.2.0")
equal("pomodoro stond al goed en is niet aangeraakt",
      mpos.AppManager.get("tech.weyn.pomodoro").version, "0.3.1")
equal("een app die er nog niet was komt erbij",
      mpos.AppManager.get("tech.weyn.nieuw").version, "1.0.0")
equal("er zijn precies twee pakketten geinstalleerd",
      len(mpos.AppManager.installs), 2)
equal("de index is gelezen", mpos.DownloadManager.requested[0], INDEX)
equal("de toestand is goed", service.state, "ok")
equal("de catalogus kent alle drie", len(service.catalog), 3)
check("er staat een tijdstip op de controle", service.last_check > 0)

# De bestemming is apps/<fullname>: install_mpk pakt het pakket daarin uit, en
# een pakket waarvan de bovenste map anders heet hoort daar niet.
paden = [dest for _, dest in mpos.AppManager.installs]
check("alles gaat naar apps/<fullname>",
      sorted(paden) == ["apps/tech.weyn.muziek", "apps/tech.weyn.nieuw"])

# Het pakket mag niet blijven staan: 2 MiB vrij is niet veel.
equal("er blijft geen .mpk achter", len(mpos.DownloadManager.files), 0)

melding = mpos.NotificationManager.posted[-1]
equal("er is een melding", melding.notification_id, service.NOTIFICATION_ID)
check("met de namen erin",
      "muziek" in melding.text and "nieuw" in melding.text)
check("geen herstart nodig, dit waren activities",
      not service.reboot_advised)


# --- een bijgewerkte service draait pas na een herstart --------------------

fresh()
mpos.AppManager.preinstall("tech.weyn.badgecontroller", "0.1.0")
publish([entry("tech.weyn.badgecontroller", "0.2.0", services=True)])
run(service.check_now())
check("een app met een service vraagt om een herstart", service.reboot_advised)
check("en dat staat in de melding",
      "herstart" in mpos.NotificationManager.posted[-1].text)


# --- de app die op het scherm staat blijft met rust ------------------------

fresh()
mpos.AppManager.preinstall("tech.weyn.muziek", "0.1.0")
mpos.AppManager.foreground = "tech.weyn.muziek"
publish([entry("tech.weyn.muziek", "0.2.0")])
run(service.check_now())
equal("de app op het scherm wordt niet vervangen",
      mpos.AppManager.get("tech.weyn.muziek").version, "0.1.0")
equal("er is niets geinstalleerd", len(mpos.AppManager.installs), 0)
equal("maar hij staat wel in het log",
      service.last_run[0]["uitkomst"], "overgeslagen, staat op het scherm")
equal("en de controle telt als geslaagd", service.state, "ok")


# --- automatisch uit: melden, niet installeren -----------------------------

fresh(auto=False)
mpos.AppManager.preinstall("tech.weyn.muziek", "0.1.0")
publish([entry("tech.weyn.muziek", "0.2.0")])
run(service.check_now())
equal("met automatisch uit gebeurt er niets",
      mpos.AppManager.get("tech.weyn.muziek").version, "0.1.0")
equal("maar je ziet wel wat er klaarstaat",
      service.last_run[0]["uitkomst"], "klaar om te installeren")
equal("en er wordt niets gemeld", len(mpos.NotificationManager.posted), 0)


# ===========================================================================
# Hernoemen: de oude naam gaat eraf
# ===========================================================================
# Een hernoemde app is voor AppManager een nieuwe app. Zonder opruimen staat de
# oude er nog, met zijn eigen tegel en zijn eigen service die bij de volgende
# start gewoon meestart. Bij deze apps zijn dat twee MQTT-clients van dezelfde
# badge, en dat is de fout die hier al een keer maanden gekost heeft.

fresh()
mpos.AppManager.preinstall("be.weyn.muziek", "0.1.0")
publish([entry("tech.weyn.muziek", "0.2.0", replaces=["be.weyn.muziek"])])
run(service.check_now())
equal("de nieuwe naam staat erop",
      mpos.AppManager.get("tech.weyn.muziek").version, "0.2.0")
equal("de oude is weg", mpos.AppManager.get("be.weyn.muziek"), None)
uitkomsten = [n["uitkomst"] for n in service.last_run]
check("en dat staat in het log", "oude naam verwijderd" in uitkomsten)
check("een herstart is nodig, de oude service draait nog", service.reboot_advised)

# Opruimen hangt niet aan een installatie. Zet je de nieuwe app met de hand
# neer, dan blijft de oude staan tot iemand hem weghaalt.
fresh()
mpos.AppManager.preinstall("be.weyn.muziek", "0.1.0")
mpos.AppManager.preinstall("tech.weyn.muziek", "0.2.0")
publish([entry("tech.weyn.muziek", "0.2.0", replaces=["be.weyn.muziek"])])
run(service.check_now())
equal("er valt niets te installeren", len(mpos.AppManager.installs), 0)
equal("en toch is de oude weg", mpos.AppManager.get("be.weyn.muziek"), None)

# Een oude naam die er niet is, of die naar de app zelf wijst, doet niets.
fresh()
mpos.AppManager.preinstall("tech.weyn.muziek", "0.2.0")
publish([entry("tech.weyn.muziek", "0.2.0",
               replaces=["be.weyn.muziek", "tech.weyn.muziek"])])
run(service.check_now())
equal("de app blijft staan",
      mpos.AppManager.get("tech.weyn.muziek").version, "0.2.0")
equal("en er wordt niets gemeld", len(service.last_run), 0)

# Een ingebouwde app hoort nooit weg te gaan, ook niet als de index dat vraagt.
# Die staat in het alleen-lezen /builtin en uninstall_app faalt er stil op.
fresh()
mpos.AppManager.preinstall("com.micropythonos.appstore", "1.3.1")
mpos.AppManager.builtins.add("com.micropythonos.appstore")
publish([entry("tech.weyn.updates", "0.1.0",
               replaces=["com.micropythonos.appstore"])])
run(service.check_now())
check("de ingebouwde AppStore staat er nog",
      mpos.AppManager.get("com.micropythonos.appstore") is not None)


# ===========================================================================
# Wat er mis kan gaan
# ===========================================================================

# De index is er niet. Dit is de koude DNS-misser uit de OSUpdate-diagnose.
fresh()
mpos.AppManager.preinstall("tech.weyn.muziek", "0.1.0")
equal("een onbereikbare index laat de controle mislukken",
      run(service.check_now()), False)
equal("en zet de toestand op error", service.state, "error")
check("met een reden erbij", bool(service.last_error))
equal("er is niets geinstalleerd", len(mpos.AppManager.installs), 0)
# En nu doet het netwerk het weer. Geen herstart, geen vlag om te resetten.
publish([entry("tech.weyn.muziek", "0.2.0")])
equal("de volgende poging lukt gewoon", run(service.check_now()), True)
equal("en installeert alsnog",
      mpos.AppManager.get("tech.weyn.muziek").version, "0.2.0")
equal("de fout is opgeruimd", service.last_error, "")

# Een index die geen lijst is.
fresh()
mpos.DownloadManager.responses[INDEX] = b'{"apps": []}'
equal("een index die geen lijst is telt als fout",
      run(service.check_now()), False)
equal("met een leesbare reden", service.last_error, "index is geen lijst")

# Kapotte JSON.
fresh()
mpos.DownloadManager.responses[INDEX] = b"<html>404</html>"
equal("kapotte JSON telt als fout", run(service.check_now()), False)
equal("de toestand is error", service.state, "error")

# Een regel zonder versie of zonder fullname wordt overgeslagen, de rest niet.
fresh()
publish([entry("tech.weyn.muziek", "0.2.0")])
mpos.DownloadManager.responses[INDEX] = json.dumps([
    {"name": "zonder fullname", "version": "1.0.0"},
    {"fullname": "tech.weyn.zonderversie"},
    "een string tussen de dicts",
    entry("tech.weyn.muziek", "0.2.0"),
]).encode()
equal("rommel in de index stopt de controle niet",
      run(service.check_now()), True)
equal("alleen de bruikbare regel telt", len(service.catalog), 1)
equal("en die is geinstalleerd",
      mpos.AppManager.get("tech.weyn.muziek").version, "0.2.0")

# Een pakket dat niet aankomt mag de rest niet meenemen.
fresh()
publish([entry("tech.weyn.een", "1.0.0"), entry("tech.weyn.twee", "1.0.0")])
del mpos.DownloadManager.responses[BASE + "mpks/tech.weyn.een_1.0.0.mpk"]
equal("de controle lukt nog steeds", run(service.check_now()), True)
check("de eerste is mislukt",
      service.last_run[0]["uitkomst"].startswith("mislukt"))
equal("de tweede staat er wel op",
      mpos.AppManager.get("tech.weyn.twee").version, "1.0.0")

# Te weinig ruimte: overslaan met een reden, niet proberen en halverwege breken.
fresh()
service.free_bytes = lambda: 50 * 1024
publish([entry("tech.weyn.groot", "1.0.0", size=400 * 1024)])
run(service.check_now())
equal("een pakket dat niet past wordt overgeslagen",
      service.last_run[0]["uitkomst"], "te weinig ruimte")
equal("en niet half gedownload", len(mpos.AppManager.installs), 0)
service.free_bytes = _echte_vrije_ruimte

# install_mpk zelf die gooit.
fresh()
publish([entry("tech.weyn.stuk", "1.0.0")])
mpos.AppManager.install_error = OSError("ENOSPC")
equal("een mislukte installatie is geen mislukte controle",
      run(service.check_now()), True)
check("maar staat wel in het log",
      service.last_run[0]["uitkomst"].startswith("mislukt"))
mpos.AppManager.install_error = None

# Twee controles tegelijk: de tweede hoort af te haken.
fresh()
publish([entry("tech.weyn.muziek", "1.0.0")])
service._busy = True
equal("een tweede controle wacht netjes", run(service.check_now()), False)
service._busy = False


# ===========================================================================
# De lus: nooit vast, en na een fout snel opnieuw
# ===========================================================================

fresh()
GESLAPEN = []
LUKT = {"waarde": True}


async def _nep_slaap(seconds):
    GESLAPEN.append(seconds)
    if len(GESLAPEN) >= 5:
        service._running = False        # stop de lus, anders draait hij door
    return True


async def _nep_controle():
    return LUKT["waarde"]


_echt_slapen = service._sleep_in_slices
_echte_controle = service.check_now
service._sleep_in_slices = _nep_slaap
service.check_now = _nep_controle

service._running = True
LUKT["waarde"] = True
run(service._run_loop())
equal("de eerste controle wacht op wifi en de andere services",
      GESLAPEN[0], service.BOOT_DELAY_S)
equal("daarna elk uur", GESLAPEN[1], service.POLL_INTERVAL_S)

GESLAPEN.clear()
service._running = True
LUKT["waarde"] = False
run(service._run_loop())
equal("na een fout een minuut, niet een uur", GESLAPEN[1],
      service.RETRY_MIN_S)
equal("dan twee minuten", GESLAPEN[2], service.RETRY_MIN_S * 2)
equal("dan vier", GESLAPEN[3], service.RETRY_MIN_S * 4)
check("en het wachten loopt nooit boven het gewone uur uit",
      max(GESLAPEN[1:]) <= service.POLL_INTERVAL_S)
check("de lus stopt nooit uit zichzelf", len(GESLAPEN) >= 5)

service._sleep_in_slices = _echt_slapen
service.check_now = _echte_controle

# Slapen in stukjes, zodat een service die stopt niet een uur blijft hangen.
fresh()
service._running = True
equal("een korte slaap loopt af", run(service._sleep_in_slices(8)), True)
service._running = False
equal("en een lange breekt af zodra de service stopt",
      run(service._sleep_in_slices(3600)), False)


# ===========================================================================
# Instellingen
# ===========================================================================

fresh()
service.set_index_url("192.168.68.100:8123/local/appstore/app_index.json")
equal("een URL zonder schema krijgt er een", service.index_url,
      "http://192.168.68.100:8123/local/appstore/app_index.json")
check("een lege URL wordt geweigerd", not service.set_index_url("   "))
service.set_auto_install(False)
service.index_url = "kwijt"
service.auto_install = True
service.load_prefs()
equal("de URL komt terug uit de instellingen", service.index_url,
      "http://192.168.68.100:8123/local/appstore/app_index.json")
equal("en de keuze om niets te installeren ook", service.auto_install, False)

mpos.config._STORE.clear()
service.load_prefs()
equal("zonder instellingen staat de standaard-URL er", service.index_url,
      service.DEFAULT_INDEX_URL)
equal("en installeert hij vanzelf", service.auto_install, True)

mpos.config.SharedPreferences(service.PREFS_APP_ID).edit().put_int(
    "interval_min", 1).commit()
service.load_prefs()
equal("elke minuut pollen mag niet, dat is vijf minuten",
      service.poll_interval_s, 300)


# ===========================================================================
# Naar Home Assistant, als de brug er is
# ===========================================================================

class NepBrug:
    connected = True
    verstuurd = []

    @classmethod
    def publish(cls, suffix, payload, retain=False):
        cls.verstuurd.append((suffix, payload, retain))
        return True


fresh()
mpos.AppManager.preinstall("tech.weyn.muziek", "0.2.0")
equal("zonder brug wordt er niets gepubliceerd", service.publish_versions(),
      False)

sys.modules["badge_service"] = NepBrug
equal("met brug wel", service.publish_versions(), True)
suffix, payload, retain = NepBrug.verstuurd[-1]
equal("op het achtervoegsel apps, niet op een heel topic", suffix, "apps")
check("retained, zodat HA het na een herstart meteen weer weet", retain)
data = json.loads(payload)
equal("met de versie erin", data["apps"]["tech.weyn.muziek"], "0.2.0")

NepBrug.connected = False
equal("een brug zonder verbinding publiceert niet",
      service.publish_versions(), False)
sys.modules.pop("badge_service", None)


# ===========================================================================
# De service-levenscyclus
# ===========================================================================

fresh()
svc = AutoUpdateService()
svc.onCreate()
svc.onStart(None)
equal("er draait een lus", len(mpos.TaskManager.tasks), 1)
svc.onStart(None)
equal("twee keer starten geeft geen tweede lus",
      len(mpos.TaskManager.tasks), 1)
svc.onDestroy()
check("en stoppen zet de lus uit", not service._running)
mpos.TaskManager.reset()


# ===========================================================================
# Het scherm
# ===========================================================================

fresh()
mpos.AppManager.preinstall("tech.weyn.muziek", "0.1.0")
publish([entry("tech.weyn.muziek", "0.2.0")])

ui = screen.AutoUpdate()
ui.onCreate()
rijen = [kind for kind in ui._view.children if kind.size is not None]
equal("drie knoppen, want een vierde past niet in 240", len(rijen), 3)
for knop in rijen:
    equal("een knop is schermbreed", knop.size[0], 100)
    equal("en vingergroot", knop.size[1], screen.ROW_HEIGHT)

equal("de knop zegt of het automatisch gaat", ui._auto_text(),
      "Automatisch: aan")
equal("en de index toont alleen de host", ui._index_text(),
      "Index: ha.example:8123")
equal("nog niets gecontroleerd", ui.status_text(), "nog niet gecontroleerd")

run(service.check_now())
ui._paint()
tekst = ui.status_text()
check("na een controle staat er wat er gebeurd is",
      "bijgewerkt: muziek 0.2.0" in tekst)
check("en wanneer", "gecontroleerd" in tekst)

service.state = "error"
service.last_error = "geen route naar de server"
check("een fout is te lezen op het scherm",
      "geen route" in ui.status_text())
service.state = "ok"

# De knop moet ook echt iets doen. Op hardware bleek eerder dat een callback
# die afgaat nog niets zegt over een vinger, maar een callback die niet afgaat
# zegt alles.
mpos.TaskManager.reset()
knop_nu = ui._view.children[1]
knop_nu.click()
equal("Nu controleren start een controle", len(mpos.TaskManager.tasks), 1)
mpos.TaskManager.reset()

knop_auto = ui._view.children[2]
knop_auto.click()
equal("de tweede knop zet automatisch uit", service.auto_install, False)
equal("en zegt dat ook", ui._auto_text(), "Automatisch: uit")
knop_auto.click()
equal("en weer aan", service.auto_install, True)

# Het invoerscherm van het OS geeft de getypte URL terug.
mpos.STARTED.clear()
knop_index = ui._view.children[3]
knop_index.click()
equal("de derde knop opent het invoerscherm", len(mpos.STARTED), 1)
intent, callback = mpos.RESULTS_PENDING[-1]
equal("met de huidige URL erin", intent.extras["value"], INDEX)
callback({"result_code": True, "data": {"value": "http://nas:8080/i.json"}})
equal("wat je typt wordt bewaard", service.index_url, "http://nas:8080/i.json")
callback({"result_code": False, "data": {"value": "weg"}})
equal("annuleren verandert niets", service.index_url, "http://nas:8080/i.json")
callback({"result_code": True, "data": {"value": "   "}})
equal("een lege URL ook niet", service.index_url, "http://nas:8080/i.json")
mpos.RESULTS_PENDING.clear()
mpos.STARTED.clear()


# --- verstreken tijd in woorden --------------------------------------------

class Klok:
    now = 1_800_000

    @classmethod
    def time(cls):
        return cls.now


_echte_tijd = screen.time
screen.time = Klok
equal("net gebeurd", screen.ago(Klok.now - 10), "zojuist")
equal("minuten", screen.ago(Klok.now - 600), "10 min geleden")
equal("een uur", screen.ago(Klok.now - 3700), "een uur geleden")
equal("uren", screen.ago(Klok.now - 7300), "2 uur geleden")
equal("gisteren", screen.ago(Klok.now - 90000), "gisteren")
equal("dagen", screen.ago(Klok.now - 300000), "3 dagen geleden")
screen.time = _echte_tijd


# ===========================================================================
# Bron: wat op de badge niet bestaat
# ===========================================================================

with open(os.path.join(APP_DIR, "autoupdate_service.py")) as fh:
    SOURCE = fh.read()
check("de service bouwt geen widgets",
      "lv.obj(" not in SOURCE and "lv.label(" not in SOURCE)
check("de service importeert lvgl niet", "import lvgl" not in SOURCE)

# CPython heeft deze; MicroPython 1.27 op deze badge niet. Gemeten met dir(str)
# op het toestel. Een desktoptest kan een aanroep hiervan niet vangen, want
# desktop Python antwoordt gewoon en de badge gooit AttributeError.
MISSING_ON_BADGE = (
    "capitalize", "casefold", "expandtabs", "format_map", "isdecimal",
    "isidentifier", "isprintable", "ljust", "maketrans", "removeprefix",
    "removesuffix", "rjust", "swapcase", "title", "translate", "zfill",
)
for name in sorted(os.listdir(APP_DIR)):
    if not name.endswith(".py"):
        continue
    with open(os.path.join(APP_DIR, name)) as fh:
        text = fh.read()
    for method in MISSING_ON_BADGE:
        check("%s roept str.%s() niet aan, die bestaat niet op deze firmware"
              % (name, method), ".%s(" % method not in text)
    # Een module-level NAAM = const(...) wordt door de compiler onderschept als
    # constantendeclaratie en laat de hele module vallen met
    # SyntaxError: not a constant.
    check("%s definieert geen functie die const heet" % name,
          "def const(" not in text)
    # re.findall en re.finditer bestaan niet, en de engine backtrackt recursief.
    check("%s parseert niet met re.findall" % name, "findall" not in text)
    for regel in text.split("\n"):
        gestript = regel.strip()
        if gestript.startswith("#") or "`" in gestript:
            continue
        check("%s: %s wordt als constante gelezen" % (name, gestript[:32]),
              " = const(" not in gestript)


# ===========================================================================

print("\n%d checks, %d mislukt" % (CHECKS["n"], len(FAILURES)))
for f in FAILURES:
    print("  -", f)
sys.exit(1 if FAILURES else 0)
