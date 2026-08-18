"""Houdt de apps op deze badge gelijk aan een index die jij zelf publiceert.

Elk uur haalt deze service een `app_index.json` op, vergelijkt elke versie
daarin met wat er geinstalleerd staat, en installeert wat nieuwer is. Dat is
dezelfde index en hetzelfde `.mpk`-formaat als de ingebouwde AppStore gebruikt,
dus wie liever met de hand tikt kan die store op dezelfde URL zetten.

Waarom een eigen service naast de AppStore
------------------------------------------
De AppStore heeft al een `AppUpdateManager` die op `boot_completed` start, na
120 s en daarna elke 24 uur kijkt, en een notificatie geeft. Hij installeert
niets: dat is een tik op "Update All". Deze service doet die tik zelf, kijkt
elk uur, en heeft geen toestand waarin hij kan blijven hangen.

**Geen `WAITING_WIFI`.** OSUpdate viel op deze badges stil doordat een enkele
koude DNS-misser hem in een wachttoestand zette die afhing van
`ConnectivityManager.is_wifi_connected()`, en die vlag komt niet meer terug.
Hier bestaat die toestand niet. Een mislukte controle is een mislukte controle:
na een minuut opnieuw, en dat wachten verdubbelt tot het gewone uur. Er is niets
dat een netwerk dat het weer doet kan missen.

**Wat een update wel en niet raakt.** `AppManager.execute_script()` zet de
module van een activity na afloop weer uit `sys.modules`, dus een bijgewerkte
activity draait de volgende keer dat je hem opent. Een service niet: die blijft
in het geheugen tot de badge herstart. Daarom meldt deze service het als een
bijgewerkte app een service heeft, in plaats van te doen alsof het al werkt.

**Hernoemen rolt zichzelf uit.** Noemt een regel in de index een veld
`replaces`, dan wordt die oude app-id na afloop verwijderd. Zonder dat blijft
een hernoemde app dubbel staan, met twee services die allebei starten.

De app die op dat moment op het scherm staat wordt overgeslagen. Zijn bestanden
onder hem vandaan schrijven terwijl hij draait is te vragen om een halve app,
en over een uur is hij toch aan de beurt.
"""

import json
import os
import sys
import time


# --- mpos-imports, defensief ------------------------------------------------
# Deze firmware exporteert niet alles wat de docs beloven, en de vorm van een
# import is het eerste dat breekt.

def _mpos(name, *paths):
    import mpos
    if hasattr(mpos, name):
        return getattr(mpos, name)
    for path in paths:
        try:
            mod = __import__(path, None, None, (name,))
            if hasattr(mod, name):
                return getattr(mod, name)
        except Exception:
            pass
    raise ImportError("autoupdate: geen %s in mpos of %s" % (name, paths))


Service = _mpos("Service", "mpos.app.service")
TaskManager = _mpos("TaskManager", "mpos.task_manager")
AppManager = _mpos("AppManager", "mpos.content.app_manager")
DownloadManager = _mpos("DownloadManager", "mpos.net.download_manager")
SharedPreferences = _mpos("SharedPreferences", "mpos.config")

APP_FULLNAME = "tech.weyn.updates"
PREFS_APP_ID = APP_FULLNAME
NOTIFICATION_ID = "autoupdate.installed"
ICON_PATH = "M:apps/tech.weyn.updates/icon_64x64.png"

# --- instellingen -----------------------------------------------------------
# De index is geen geheim, dus hij staat gewoon hier en is op de badge zelf te
# wijzigen. /local/ van Home Assistant is de map config/www en wordt zonder
# login geserveerd, wat precies genoeg is voor een index en een paar .mpk's op
# je eigen netwerk.
DEFAULT_INDEX_URL = "http://192.168.68.100:8123/local/appstore/app_index.json"

BOOT_DELAY_S = 90         # wifi, de MQTT-brug en de andere services voorgaan
POLL_INTERVAL_S = 3600
RETRY_MIN_S = 60          # na een fout: snel nog eens, dan verdubbelen
SLICE_S = 5               # in stukjes slapen, zodat stoppen meteen aankomt
SPACE_MARGIN = 96 * 1024  # ruimte die vrij blijft na een installatie

index_url = DEFAULT_INDEX_URL
auto_install = True
poll_interval_s = POLL_INTERVAL_S

# --- toestand, leesbaar voor het scherm -------------------------------------
state = "idle"            # idle | checking | ok | error
last_check = 0            # time.time() van de laatste geslaagde controle
last_error = ""
last_run = []             # lijst van dicts: fullname, van, naar, uitkomst
catalog = {}              # fullname -> versie zoals de index hem noemt
reboot_advised = False    # een bijgewerkte service draait pas na een herstart

_busy = False
_running = False
_service = None


# --- kleine hulpjes ---------------------------------------------------------

def describe_error(exc):
    text = str(exc)
    if not text:
        text = type(exc).__name__
    return text[:80]


def parse_version(value):
    """`"0.4.1"` -> `(0, 4, 1)`. Wat geen getal is telt als 0.

    `AppManager.compare_versions` doet hetzelfde en die gebruiken we ook, maar
    niet elke firmware heeft hem, en een versie zonder cijfers mag hier geen
    uitzondering geven.
    """
    parts = []
    for chunk in str(value).split("."):
        digits = ""
        for char in chunk:
            if char < "0" or char > "9":
                break
            digits += char
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer(candidate, installed):
    """Is `candidate` een hogere versie dan `installed`?"""
    try:
        compare = getattr(AppManager, "compare_versions", None)
        if compare is not None:
            return bool(compare(candidate, installed))
    except Exception:
        pass
    return parse_version(candidate) > parse_version(installed)


def absolute_url(url, base):
    """Een index mag naar `mpks/foo.mpk` naast zichzelf wijzen.

    Dat maakt de map verplaatsbaar: dezelfde bestanden werken op de HA-server,
    op een NAS en in een testmap, zonder de index te herschrijven.
    """
    if not url:
        return url
    if url.find("://") >= 0:
        return url
    cut = base.rfind("/")
    root = base[:cut] if cut > 0 else base
    if url[0] == "/":
        # absoluut pad: alles na de host vervangen
        scheme = base.find("://")
        host_end = base.find("/", scheme + 3) if scheme >= 0 else -1
        return (base[:host_end] if host_end > 0 else base) + url
    return root + "/" + url


def installed_version(fullname):
    """De versie zoals AppManager hem kent, of None als de app er niet is."""
    try:
        app = AppManager.get(fullname)
    except Exception:
        app = None
    if app is None:
        return None
    return getattr(app, "version", None) or "0"


def temp_dir():
    """Een map waar een .mpk even mag staan.

    `/cache` bestaat niet op deze badge, ook al noemt de mapindeling hem, en
    `/tmp` is er niet altijd. Maak wat er ontbreekt, en val terug op `/data`.
    """
    for path in ("/tmp", "/data"):
        try:
            os.stat(path)
            return path
        except OSError:
            try:
                os.mkdir(path)
                return path
            except OSError:
                pass
    return ""


def free_bytes():
    try:
        stats = os.statvfs("/")
        return stats[0] * stats[3]
    except Exception:
        return -1          # onbekend telt als genoeg: liever proberen


def enough_space(size):
    """Een .mpk wordt onverpakt bewaard, dus uitgepakt is hij ongeveer even
    groot. Het pakket en de uitgepakte app staan even samen op de flash."""
    free = free_bytes()
    if free < 0 or not size:
        return True
    return free > (size * 2) + SPACE_MARGIN


def remove_quietly(path):
    try:
        os.remove(path)
    except Exception:
        pass


def bridge():
    """De MQTT-brug van tech.weyn.badgecontroller, als die draait.

    Alle apps delen een MicroPython-VM en dus een `sys.modules`, maar de map
    van een andere app staat niet op `sys.path`; opzoeken is de enige manier.
    Elke keer opnieuw opzoeken, want de volgorde waarin services starten ligt
    niet vast.
    """
    return sys.modules.get("badge_service")


def has_service(entry):
    services = entry.get("services")
    return bool(services)


def foreground_fullname():
    """Welke app staat er nu op het scherm? Leeg als het niet te zien is."""
    try:
        current = getattr(AppManager, "get_foreground_app", None)
        if current is not None:
            app = current()
            return getattr(app, "fullname", "") or ""
    except Exception:
        pass
    for attr in ("foreground_app", "_foreground_app"):
        app = getattr(AppManager, attr, None)
        if app is not None:
            return getattr(app, "fullname", "") or str(app)
    return ""


# --- instellingen -----------------------------------------------------------

def load_prefs():
    global index_url, auto_install, poll_interval_s
    try:
        prefs = SharedPreferences(PREFS_APP_ID)
    except Exception as exc:
        print("autoupdate: geen instellingen:", describe_error(exc))
        return
    url = prefs.get_string("index_url", "") or DEFAULT_INDEX_URL
    index_url = url.strip()
    auto_install = prefs.get_string("auto", "true") != "false"
    minutes = prefs.get_int("interval_min", POLL_INTERVAL_S // 60)
    if minutes < 5:
        minutes = 5
    poll_interval_s = minutes * 60


def save_prefs():
    try:
        editor = SharedPreferences(PREFS_APP_ID).edit()
        editor.put_string("index_url", index_url)
        editor.put_string("auto", "true" if auto_install else "false")
        editor.put_int("interval_min", poll_interval_s // 60)
        editor.commit()
    except Exception as exc:
        print("autoupdate: kon instellingen niet bewaren:", describe_error(exc))


def set_index_url(url):
    global index_url
    cleaned = (url or "").strip()
    if not cleaned:
        return False
    if cleaned.find("://") < 0:
        cleaned = "http://" + cleaned
    index_url = cleaned
    save_prefs()
    return True


def set_auto_install(enabled):
    global auto_install
    auto_install = bool(enabled)
    save_prefs()


def is_builtin(fullname):
    """Ingebouwde apps staan in het alleen-lezen /builtin en gaan nergens heen."""
    try:
        checker = getattr(AppManager, "is_builtin_app", None)
        if checker is not None:
            return bool(checker(fullname))
    except Exception:
        pass
    return False


def remove_replaced(entry, fullname):
    """De vorige naam van een app opruimen, als de index er een noemt.

    Een hernoemde app is voor AppManager een nieuwe app. De oude blijft staan:
    eigen map, eigen tegel in de launcher, en een eigen service die bij de
    volgende start gewoon meestart. Bij deze apps zou dat twee MQTT-clients van
    dezelfde badge geven, en dat is precies de fout die hier al een keer
    maanden gekost heeft, want een broker gooit de oudste van twee clients met
    dezelfde id eruit en ze duwen elkaar om beurten van de lijn.

    De app die dit uitvoert kan zichzelf in de lijst tegenkomen. Dat mag: zijn
    code draait uit het geheugen, dus hij loopt door tot de volgende start, en
    daarna bestaat alleen de nieuwe naam nog.
    """
    verwijderd = []
    for old in entry.get("replaces") or []:
        if not old or old == fullname:
            continue
        if installed_version(old) is None or is_builtin(old):
            continue
        try:
            AppManager.uninstall_app(old)
        except Exception as exc:
            print("autoupdate: %s bleef staan: %s" % (old, describe_error(exc)))
            continue
        if installed_version(old) is not None:
            print("autoupdate: %s is niet verdwenen" % old)
            continue
        verwijderd.append(old)
        print("autoupdate: oude naam %s verwijderd" % old)
    return verwijderd


# --- de eigenlijke controle -------------------------------------------------

async def fetch_index():
    data = await DownloadManager.download_url(index_url)
    if isinstance(data, bytes):
        data = data.decode()
    return json.loads(data)


async def install_entry(entry):
    """Een enkele app ophalen en installeren. Geeft een dict terug voor het log."""
    fullname = entry.get("fullname") or ""
    version = str(entry.get("version") or "")
    have = installed_version(fullname)
    note = {"fullname": fullname, "van": have, "naar": version, "uitkomst": ""}

    url = absolute_url(entry.get("download_url") or "", index_url)
    if not url:
        note["uitkomst"] = "geen download-URL"
        return note

    size = 0
    try:
        size = int(entry.get("download_url_size") or 0)
    except Exception:
        size = 0
    if not enough_space(size):
        note["uitkomst"] = "te weinig ruimte"
        return note

    folder = temp_dir()
    if not folder:
        note["uitkomst"] = "geen plek voor het pakket"
        return note
    package = folder + "/" + fullname + ".mpk"

    try:
        await DownloadManager.download_url(url, outfile=package)
        AppManager.install_mpk(package, "apps/" + fullname)
    except Exception as exc:
        remove_quietly(package)
        note["uitkomst"] = "mislukt: " + describe_error(exc)
        return note
    remove_quietly(package)

    # install_mpk ververst de app-lijst zelf, maar niet elke firmware doet dat,
    # en zonder verse lijst lijkt de installatie mislukt.
    try:
        AppManager.refresh_apps()
    except Exception:
        pass

    now = installed_version(fullname)
    if now is None:
        note["uitkomst"] = "geinstalleerd, maar AppManager ziet hem niet"
        return note
    note["naar"] = now
    note["uitkomst"] = "bijgewerkt" if have else "nieuw"
    return note


async def check_now():
    """Index halen, verschillen installeren. True als de controle zelf lukte."""
    global state, last_check, last_error, last_run, catalog, _busy
    global reboot_advised

    if _busy:
        return False
    _busy = True
    state = "checking"
    changed = []
    try:
        try:
            entries = await fetch_index()
        except Exception as exc:
            state = "error"
            last_error = describe_error(exc)
            print("autoupdate: index niet gelezen:", last_error)
            return False

        if not isinstance(entries, list):
            state = "error"
            last_error = "index is geen lijst"
            return False

        fresh = {}
        results = []
        skipped_fg = foreground_fullname()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            fullname = entry.get("fullname") or ""
            version = str(entry.get("version") or "")
            if not fullname or not version:
                continue
            fresh[fullname] = version
            have = installed_version(fullname)
            if have is None or is_newer(version, have):
                if fullname == skipped_fg:
                    results.append({"fullname": fullname, "van": have,
                                    "naar": version,
                                    "uitkomst": "overgeslagen, staat op het scherm"})
                elif not auto_install:
                    results.append({"fullname": fullname, "van": have,
                                    "naar": version,
                                    "uitkomst": "klaar om te installeren"})
                else:
                    note = await install_entry(entry)
                    results.append(note)
                    if note["uitkomst"] in ("bijgewerkt", "nieuw"):
                        changed.append(note)
                        if has_service(entry):
                            reboot_advised = True

            # Opruimen hoort niet aan een installatie te hangen. Een app die je
            # met de hand onder zijn nieuwe naam zette laat zijn oude naam net
            # zo goed staan, en die hoort er de volgende ronde alsnog af.
            if installed_version(fullname) is not None:
                for old in remove_replaced(entry, fullname):
                    results.append({"fullname": old, "van": None, "naar": None,
                                    "uitkomst": "oude naam verwijderd"})
                    # De service van die oude app draait tot de badge herstart.
                    reboot_advised = True

        catalog = fresh
        last_run = results
        last_error = ""
        last_check = int(time.time())
        state = "ok"
    finally:
        _busy = False

    if changed:
        announce(changed)
    publish_versions()
    return True


def announce(changed):
    names = []
    for note in changed:
        names.append("%s %s" % (short_name(note["fullname"]), note["naar"]))
    text = ", ".join(names)
    if reboot_advised:
        text += " (herstart voor de achtergronddelen)"
    print("autoupdate:", text)
    try:
        import mpos
        Notification = getattr(mpos, "Notification", None)
        NotificationManager = getattr(mpos, "NotificationManager", None)
        if Notification is None or NotificationManager is None:
            return
        NotificationManager.notify(Notification(
            notification_id=NOTIFICATION_ID,
            icon=ICON_PATH,
            title="%d app%s bijgewerkt" % (len(changed),
                                           "" if len(changed) == 1 else "s"),
            text=text,
            priority=Notification.PRIORITY_DEFAULT,
            app_fullname=APP_FULLNAME,
        ))
    except Exception as exc:
        print("autoupdate: notificatie mislukt:", describe_error(exc))


def short_name(fullname):
    cut = fullname.rfind(".")
    return fullname[cut + 1:] if cut >= 0 else fullname


def installed_map():
    """Wat er nu staat: fullname -> versie. Voor het scherm en voor MQTT."""
    found = {}
    try:
        for app in AppManager.get_app_list():
            name = getattr(app, "fullname", "")
            if name:
                found[name] = getattr(app, "version", "") or ""
    except Exception:
        pass
    return found


def publish_versions():
    """Retained op `home/badges/<naam>/apps`, als de brug er is.

    Zonder dit weet je pas dat een badge achterloopt als je hem in je hand hebt.
    Het is geen aansturing: de badge vertelt alleen wat hij heeft.
    """
    link = bridge()
    if link is None or not getattr(link, "connected", False):
        return False
    try:
        payload = json.dumps({
            "apps": installed_map(),
            "checked": last_check,
            "state": state,
            "reboot_advised": reboot_advised,
        })
        return bool(link.publish("apps", payload, retain=True))
    except Exception as exc:
        print("autoupdate: kon versies niet publiceren:", describe_error(exc))
        return False


def request_check():
    """Nu controleren, vanaf het scherm. Doet niets als hij al bezig is."""
    if _busy:
        return False
    try:
        TaskManager.create_task(check_now())
        return True
    except Exception as exc:
        print("autoupdate: kon controle niet starten:", describe_error(exc))
        return False


# --- de lus -----------------------------------------------------------------

async def _run_loop():
    """Wachten, controleren, opnieuw. Geen toestand die kan blijven hangen.

    Na een fout gaat de wachttijd naar een minuut en verdubbelt hij tot het
    gewone uur. Een koude DNS-misser kost je dus een minuut, en niet je hele
    update, wat precies is wat OSUpdate hier verkeerd doet.
    """
    delay = BOOT_DELAY_S
    retry = RETRY_MIN_S
    while _running:
        if not await _sleep_in_slices(delay):
            return
        if await check_now():
            retry = RETRY_MIN_S
            delay = poll_interval_s
        else:
            delay = retry
            retry = min(retry * 2, poll_interval_s)


async def _sleep_in_slices(seconds):
    """Slapen in stukjes, zodat onDestroy niet een uur hoeft te wachten."""
    waited = 0
    while waited < seconds:
        if not _running:
            return False
        slice_s = seconds - waited
        if slice_s > SLICE_S:
            slice_s = SLICE_S
        await TaskManager.sleep(slice_s)
        waited += slice_s
    return _running


class AutoUpdateService(Service):
    """Start de lus op `boot_completed` en stopt hem netjes."""

    def onCreate(self):
        global _service
        _service = self
        load_prefs()

    def onStart(self, intent=None):
        global _running
        if _running:
            return
        _running = True
        try:
            TaskManager.create_task(_run_loop())
        except Exception as exc:
            _running = False
            print("autoupdate: lus start niet:", describe_error(exc))

    def onDestroy(self):
        global _running
        _running = False
