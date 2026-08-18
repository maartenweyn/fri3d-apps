"""De brug tussen deze badge en Home Assistant.

Draait als MicroPythonOS-service op `boot_completed` en bezit drie dingen die
niets met een enkele app te maken hebben:

  1. **De MQTT-verbinding.** Een badge hoort er één te hebben. Twee clients van
     hetzelfde toestel naar dezelfde broker is precies de fout die Berichtjes al
     een keer gekost heeft: de broker gooit de oudste van twee clients met
     dezelfde id eruit, ze duwen elkaar om beurten van de lijn, en het lijkt
     sprekend op een haperend netwerk.
  2. **Wie deze badge is.** De naam, het toestel-id uit het MAC, de topics, en
     wat Home Assistant erover te horen krijgt: batterij, spanning, signaal.
  3. **Het scherm.** Uit of een gedimde klok na een tijd niets doen, wakker bij
     aanraking, en 's nachts donkerder dan overdag.

Andere apps praten hier tegen. Ze mogen niet `import badge_service` doen: de
map van deze app staat niet op `sys.path` van een andere app. Alle apps draaien
wel in dezelfde MicroPython-VM met één `sys.modules`, dus opzoeken werkt:

    import sys
    brug = sys.modules.get("badge_service")
    if brug is not None and brug.connected:
        brug.subscribe("msg", mijn_callback)
        brug.publish("ack", "gelezen")

Elke tick opnieuw opzoeken, niet één keer bewaren. De volgorde waarin services
starten ligt niet vast, en een app die de brug één keer mist zou hem nooit meer
vinden.

Abonneren gaat op het **achtervoegsel**, niet op het hele topic. De naam van de
badge zit in het topic, dus wie zich op `home/badges/alice/msg` abonneert hoort
niets meer zodra de badge `bob` heet. Wie zich op `"msg"` abonneert wordt bij
een hernoeming automatisch opnieuw ingeschreven.

Niets hier maakt LVGL-objecten aan: een service heeft geen scherm. Het
klokscherm is de uitzondering die de regel bewaakt: dat staat in `bgclock.py`,
en dat bouwt zijn widgets pas bij de eerste keer tonen.
"""

import json
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
    raise ImportError("badge: geen %s in mpos of %s" % (name, paths))


Service = _mpos("Service", "mpos.app.service")
TaskManager = _mpos("TaskManager", "mpos.task_manager")
SharedPreferences = _mpos("SharedPreferences", "mpos.config")

# Het klokscherm hier importeren en niet pas als het nodig is. Een service draait
# met `sys.path` op ['lib', '', '.frozen', '/lib'] en cwd op '/', en de map van
# deze app staat daar niet in: een `import bgclock` om drie uur 's nachts geeft
# ImportError. Bij het importeren van deze module werkt het wel, want dan laadt
# het OS de app en is zijn map bereikbaar. Op de badge gemeten, niet aangenomen.
#
# Dit importeert LVGL in een service, en dat blijft de uitzondering: bgclock
# maakt pas objecten aan bij de eerste keer tonen, dus een badge die nooit een
# klok laat zien betaalt er geen geheugen voor.
try:
    import bgclock as _bgclock
except Exception as _e:
    _bgclock = None
    print("badge: klokscherm niet te laden:", _e)

APP_FULLNAME = "tech.weyn.badgecontroller"
PREFS_APP_ID = APP_FULLNAME

# --- configuratie -----------------------------------------------------------
# badge_config.py is gitignored en houdt het brokeradres en het wachtwoord. Deze
# standaardwaarden bestaan alleen zodat een badge zonder configbestand opstart;
# ze werken naar verwachting niet.
BADGE_NAME = "badge"
MQTT_BROKER = "homeassistant.local"
MQTT_PORT = 1883
MQTT_USER = None
MQTT_PASS = None
TIMEZONE = "CET-1CEST,M3.5.0,M10.5.0/3"
DISCOVERY_PREFIX = "homeassistant"
SCREEN_OFF_S = 0          # 0 betekent: nooit uit
DEBUG_LED = 0             # helderheid van het debug-lampje op de expander

# Wat er na SCREEN_OFF_S gebeurt: "uit" is donker, "klok" laat een gedimde klok
# staan. 's Nachts gaat de klok eerst nog verder omlaag en daarna alsnog uit.
IDLE_MODE = "uit"
CLOCK_DAY = 30            # helderheid van de klok overdag
CLOCK_NIGHT = 5           # en 's nachts
NIGHT_FROM = 23           # het nachtvenster, in hele uren lokale tijd
NIGHT_TO = 7              # van == tot betekent: geen nacht
WEER_TOPIC = "home/badges/weer"
CONFIG_OK = False

try:
    import badge_config as _cfg
    BADGE_NAME = getattr(_cfg, "BADGE_NAME", BADGE_NAME)
    MQTT_BROKER = getattr(_cfg, "MQTT_BROKER", MQTT_BROKER)
    MQTT_PORT = getattr(_cfg, "MQTT_PORT", MQTT_PORT)
    MQTT_USER = getattr(_cfg, "MQTT_USER", None)
    MQTT_PASS = getattr(_cfg, "MQTT_PASS", None)
    TIMEZONE = getattr(_cfg, "TIMEZONE", TIMEZONE)
    DISCOVERY_PREFIX = getattr(_cfg, "DISCOVERY_PREFIX", DISCOVERY_PREFIX)
    SCREEN_OFF_S = getattr(_cfg, "SCREEN_OFF_S", SCREEN_OFF_S)
    DEBUG_LED = getattr(_cfg, "DEBUG_LED", DEBUG_LED)
    IDLE_MODE = getattr(_cfg, "IDLE_MODE", IDLE_MODE)
    CLOCK_DAY = getattr(_cfg, "CLOCK_DAY", CLOCK_DAY)
    CLOCK_NIGHT = getattr(_cfg, "CLOCK_NIGHT", CLOCK_NIGHT)
    NIGHT_FROM = getattr(_cfg, "NIGHT_FROM", NIGHT_FROM)
    NIGHT_TO = getattr(_cfg, "NIGHT_TO", NIGHT_TO)
    WEER_TOPIC = getattr(_cfg, "WEER_TOPIC", WEER_TOPIC)
    CONFIG_OK = True
except ImportError:
    print("badge: geen badge_config.py, standaardwaarden")

TOPIC_PREFIX = ""
TOPIC_STATE = ""         # retained JSON: battery, voltage, rssi
TOPIC_STATUS = ""        # retained online/offline, en tegelijk de last will
CLIENT_ID = ""

# Wachttijd tussen verbindingspogingen. Een badge aan een lanyard is vaak buiten
# bereik, en daar elke seconde opnieuw proberen kost stroom voor niets.
RETRY_MIN = 2
RETRY_MAX = 60
PING_EVERY = 20          # keepalive is 60 s; ping ruim daarbinnen
SOCKET_TIMEOUT = 5       # laat een dode broker nooit de LVGL-thread ophouden
TICK = 0.5

# De lus draait sneller dan hij pompt, want de S-knop wordt gepolst en niet op
# een interrupt gelezen. Een halve seconde tussen twee metingen laat een korte
# druk wegvallen; een tiende niet. Pompen blijft op TICK: check_msg en ping
# hebben niets aan tien keer per seconde.
LUS_TICK = 0.1

# Hoe lang de klok blijft staan na een druk op S in het donker. Kort genoeg dat
# een blik op het uur geen kamerverlichting wordt.
KIJK_S = 10

# Hoe vaak de badge zijn batterij meldt. Een cel loopt over uren leeg; elke paar
# seconden meten geeft alleen radioverkeer en ruis op een grafiek.
STATE_EVERY = 300

# --- toestand, gelezen door andere apps -------------------------------------
connected = False
last_error = None
battery_pct = None
battery_volt = None
wifi_rssi = None
screen_off = False

# De schermtoestand. NORMAAL is de app zoals hij is, KLOK is de gedimde klok
# over alles heen, UIT is donker, en KIJK is de klok na een druk op S in het
# donker: even kijken hoe laat het is, en vanzelf weer weg.
SCHERM_NORMAAL = "normaal"
SCHERM_KLOK = "klok"
SCHERM_UIT = "uit"
SCHERM_KIJK = "kijk"

screen_state = SCHERM_NORMAAL
weer = {}                # het laatst ontvangen weerbericht, leeg tot er een is

_service = None
_subscribers = {}        # achtervoegsel -> callback(topic:str, payload:bytes)


def titlecase(name):
    """Eerste letter een hoofdletter.

    Zestien stringmethodes van CPython ontbreken op deze firmware, waaronder de
    methode die hier vanzelfsprekend zou zijn. Dus met de hand."""
    return name[:1].upper() + name[1:]


NAME_OK = "abcdefghijklmnopqrstuvwxyz0123456789-_"


def normalize_name(text):
    """Een getypte naam veilig maken voor een MQTT-topic, of "" teruggeven.

    De naam wordt op een aanraakscherm getypt en moet overeenkomen met het topic
    waar Home Assistant naartoe publiceert. Een hoofdletter, een spatie achteraan
    of een schuine streep wijst de badge naar een topic waar niemand publiceert,
    en dan komt er niets aan en klaagt er niets."""
    if not text:
        return ""
    out = []
    for ch in text.strip().lower():
        if ch in NAME_OK:
            out.append(ch)
        elif ch in " \t.":
            out.append("-")
        # De rest, inclusief / + # die iets betekenen voor een broker, valt weg
        # in plaats van vertaald te worden in een verrassing.
    name = "".join(out).strip("-")
    while "--" in name:
        name = name.replace("--", "-")
    return name[:24]


def describe_error(error):
    """Zeggen wat er misging in woorden, niet in een errno.

    Het verbindingsscherm toont dit terwijl iemand een adres intypt, en
    "geen verbinding: -1" zegt niets over welk van de vier velden fout is.
    CONNACK 5 betekent dat de broker weet wie je zegt te zijn en je niet
    accepteert, een ander probleem dan een verkeerd adres."""
    if error is None:
        return None
    code = None
    args = getattr(error, "args", ())
    if args and isinstance(args[0], int):
        code = args[0]
    name = type(error).__name__
    if name == "MQTTException":
        if code == 5:
            return "login geweigerd"
        if code == 4:
            return "gebruiker of wachtwoord fout"
        if code == 3:
            return "broker niet beschikbaar"
        return "broker weigert (code %s)" % code
    if isinstance(error, OSError) or name in ("OSError", "ETIMEDOUT"):
        return "geen antwoord van de broker"
    text = str(error)
    return text or name


def normalize_port(text):
    """Een poortnummer, of 0 als dat niet is wat er staat."""
    try:
        port = int(str(text).strip())
    except (ValueError, TypeError):
        return 0
    return port if 1 <= port <= 65535 else 0


def device_suffix():
    """Zes hexcijfers die deze badge zijn en geen andere.

    De client-id was ooit badge_<naam>, en twee badges die even hetzelfde heten
    is geen hypothese: dat is wat er gebeurt terwijl je de tweede instelt. Een
    broker gooit de oudste van twee clients met dezelfde id eruit, waarna de twee
    elkaar om beurten van de lijn duwen, voor altijd, en het lijkt sprekend op
    een haperend netwerk. Uit het MAC, dus het overleeft een hernoeming en een
    reflash."""
    try:
        import machine
        import ubinascii
        return ubinascii.hexlify(machine.unique_id()).decode()[-6:]
    except Exception:
        try:
            import network
            import ubinascii
            mac = network.WLAN(network.STA_IF).config("mac")
            return ubinascii.hexlify(mac).decode()[-6:]
        except Exception:
            return "unknown"


DEVICE_SUFFIX = device_suffix()


def set_badge_name(name):
    """De badge een naam geven, en alles wat daarvan afhangt opnieuw opbouwen.

    De topics dragen de naam, dus hernoemen moet de verbinding laten vallen: een
    client blijft geabonneerd op wat hij vroeg, en op het nieuwe topic zou nooit
    iets binnenkomen tot hij zich opnieuw inschrijft."""
    global BADGE_NAME, TOPIC_PREFIX, TOPIC_STATE, TOPIC_STATUS, CLIENT_ID
    name = normalize_name(name)
    if not name:
        return False
    changed = name != BADGE_NAME
    BADGE_NAME = name
    TOPIC_PREFIX = "home/badges/%s/" % name
    TOPIC_STATE = TOPIC_PREFIX + "state"
    TOPIC_STATUS = TOPIC_PREFIX + "status"
    # De naam staat erin voor wie de brokerlog leest; het achtervoegsel maakt
    # hem uniek.
    CLIENT_ID = "badge_%s_%s" % (name, DEVICE_SUFFIX)
    if changed and _service is not None:
        _service.resubscribe()
    return changed


# Deze verbinding heeft drie keer een andere naam gehad, en instellingen hangen
# aan de naam van de app. Eerst zat hij in Berichtjes (be.weyn.dinerbadge),
# daarna in be.weyn.badge, en sinds de apps onder weyn.tech staan heet hij
# tech.weyn.badgecontroller. Zonder deze stap vraagt een badge die al maanden hangt na een
# update opnieuw om zijn brokerwachtwoord, op een aanraakscherm.
#
# Nieuwste bron eerst: wie be.weyn.badge heeft gehad heeft daar het meest
# complete stel staan, inclusief het scherm en het debug-lampje.
LEGACY_SOURCES = (
    ("tech.weyn.badge", (("badge_name", "badge_name", "string"),
                         ("mqtt_host", "mqtt_host", "string"),
                         ("mqtt_port", "mqtt_port", "int"),
                         ("mqtt_user", "mqtt_user", "string"),
                         ("mqtt_pass", "mqtt_pass", "string"),
                         ("screen_off_s", "screen_off_s", "int"),
                         ("debug_led", "debug_led", "int"))),
    ("be.weyn.badge", (("badge_name", "badge_name", "string"),
                       ("mqtt_host", "mqtt_host", "string"),
                       ("mqtt_port", "mqtt_port", "int"),
                       ("mqtt_user", "mqtt_user", "string"),
                       ("mqtt_pass", "mqtt_pass", "string"),
                       ("screen_off_s", "screen_off_s", "int"),
                       ("debug_led", "debug_led", "int"))),
    ("be.weyn.dinerbadge", (("badge_name", "child_name", "string"),
                            ("mqtt_host", "mqtt_host", "string"),
                            ("mqtt_port", "mqtt_port", "int"),
                            ("mqtt_user", "mqtt_user", "string"),
                            ("mqtt_pass", "mqtt_pass", "string"))),
)


def migrate_prefs():
    """Overnemen wat er onder een oudere naam van deze app stond, een keer.

    Draait alleen als er hier nog niets staat, dus wie eenmaal iets in de
    Badge-app zet wordt nooit meer overschreven. De eerste bron die iets
    oplevert wint; verder zoeken zou een oudere waarde over een nieuwere heen
    kunnen zetten.

    Een int van nul wordt overgeslagen. Dat kan omdat nul voor allebei de
    int-sleutels ook de standaard is: het scherm gaat nooit uit en het
    debug-lampje staat uit.
    """
    try:
        prefs = SharedPreferences(PREFS_APP_ID)
        if prefs.get_string("badge_name", ""):
            return False
        for oud_id, keys in LEGACY_SOURCES:
            oud = SharedPreferences(oud_id)
            editor = None
            overgenomen = []
            for nieuw_key, oud_key, soort in keys:
                if soort == "int":
                    waarde = oud.get_int(oud_key, 0)
                    if not waarde:
                        continue
                else:
                    waarde = oud.get_string(oud_key, "")
                    if not waarde:
                        continue
                if editor is None:
                    editor = prefs.edit()
                if soort == "int":
                    editor.put_int(nieuw_key, int(waarde))
                else:
                    editor.put_string(nieuw_key, waarde)
                overgenomen.append(nieuw_key)
            if editor is None:
                continue
            editor.commit()
            print("badge: instellingen overgenomen van %s:" % oud_id,
                  ", ".join(overgenomen))
            return True
        return False
    except Exception as e:
        print("badge: kon de oude instellingen niet overnemen:", e)
        return False

def _expander():
    import mpos
    exp = getattr(mpos, "io_expander", None)
    if exp is None:
        import mpos.io_expander as exp
    return exp


def apply_debug_led(niveau):
    """Het kleine lampje op de expander op een helderheid zetten, 0 is uit.

    Staat af fabriek op 50 en brandt dus altijd, ook op een badge die de hele
    nacht ligt te laden. De expander is een eigen microcontroller die zijn
    instelling zelf bijhoudt, dus dit overleeft een herstart van de ESP32. Het
    wordt toch bij elke keer laden opnieuw toegepast, want een reflash van die
    firmware zet hem terug op 50 en dan sta je weer met een lampje in het donker.

    Dit gaat niet over de twee groene lampjes en het rode van de lader. Die
    hangen aan de CHRG- en STDBY-pinnen van de TP4056 en aan VUSB, volgens de
    voedingspagina van het schema. Uitgangen van de laadchip zelf; geen software
    komt daarbij."""
    try:
        _expander().debug_led = max(0, min(100, int(niveau)))
        return True
    except Exception as e:
        print("badge: debug-LED niet te zetten:", e)
        return False


def load_prefs():
    """Lezen wat de instelschermen schrijven, en toepassen.

    Alles waar de verbinding van afhangt moet die verbinding laten vallen: een
    client blijft geabonneerd op wat hij vroeg en blijft praten met de host die
    hij belde, dus het een of het ander wijzigen zonder opnieuw te verbinden
    laat de badge zitten terwijl hij er goed uitziet en niets hoort."""
    global MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS, SCREEN_OFF_S, DEBUG_LED
    global IDLE_MODE, CLOCK_DAY, CLOCK_NIGHT, NIGHT_FROM, NIGHT_TO
    name = BADGE_NAME
    before = (MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS)
    try:
        prefs = SharedPreferences(PREFS_APP_ID)
        name = prefs.get_string("badge_name", BADGE_NAME) or BADGE_NAME
        MQTT_BROKER = prefs.get_string("mqtt_host", MQTT_BROKER) or MQTT_BROKER
        MQTT_PORT = normalize_port(prefs.get_int("mqtt_port", MQTT_PORT)) \
            or MQTT_PORT
        # Een lege string is hoe "anoniem" bewaard wordt; umqtt wil None.
        MQTT_USER = prefs.get_string("mqtt_user", MQTT_USER or "") or None
        MQTT_PASS = prefs.get_string("mqtt_pass", MQTT_PASS or "") or None
        SCREEN_OFF_S = prefs.get_int("screen_off_s", SCREEN_OFF_S)
        DEBUG_LED = prefs.get_int("debug_led", DEBUG_LED)
        IDLE_MODE = prefs.get_string("idle_mode", IDLE_MODE) or IDLE_MODE
        CLOCK_DAY = prefs.get_int("clock_day", CLOCK_DAY)
        CLOCK_NIGHT = prefs.get_int("clock_night", CLOCK_NIGHT)
        NIGHT_FROM = prefs.get_int("night_from", NIGHT_FROM)
        NIGHT_TO = prefs.get_int("night_to", NIGHT_TO)
    except Exception as e:
        print("badge: kon voorkeuren niet lezen:", e)

    apply_debug_led(DEBUG_LED)

    renamed = set_badge_name(name)
    if not renamed and before != (MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS):
        print("badge: broker gewijzigd naar %s:%s" % (MQTT_BROKER, MQTT_PORT))
        if _service is not None:
            _service.resubscribe()
        return True
    return renamed


# Bij het importeren, niet pas in onCreate van de service.
#
# De activity importeert deze module ook, en een activity kan eerder draaien dan
# de service: het instelscherm openen op een badge waarvan de service nog niet
# gestart is, en het dan weer verlaten, schreef de standaard uit het
# configbestand als naam weg. Daarna zag de migratie een ingevulde naam staan en
# sloeg zichzelf over, en de badge heette voorgoed iets anders dan hij heette.
# Wie het eerst importeert doet het nu, en dat is altijd voor er iets geschreven
# kan worden.
migrate_prefs()
load_prefs()


# --- de API waar andere apps op leunen --------------------------------------

def topic(suffix):
    """`home/badges/<naam>/<achtervoegsel>`, of het topic zelf als het er al
    een is. Zo kan een app zowel "msg" als een volledig topic doorgeven."""
    if not suffix:
        return ""
    if "/" in suffix:
        return suffix
    return TOPIC_PREFIX + suffix


def subscribe(suffix, callback):
    """Meeluisteren op een achtervoegsel van deze badge.

    Blijft staan over herverbindingen en hernoemingen heen: het achtervoegsel
    wordt bij elke connect opnieuw op de dan geldende naam ingeschreven. Twee
    keer voor hetzelfde achtervoegsel vervangt de callback in plaats van er een
    tweede bij te zetten."""
    if not suffix or callback is None:
        return False
    nieuw = suffix not in _subscribers
    _subscribers[suffix] = callback
    if nieuw and _service is not None:
        _service.subscribe_now(suffix)
    return True


def unsubscribe(suffix):
    _subscribers.pop(suffix, None)


def publish(suffix, payload, retain=False):
    """Publiceren op een achtervoegsel van deze badge. False als er geen link is."""
    if _service is None:
        return False
    return _service.publish_raw(topic(suffix), payload, retain=retain)


def wake():
    """Het scherm wakker maken, zoals een vinger dat doet.

    Voor een app die iets te melden heeft terwijl het scherm net uit ging: een
    bericht dat binnenkomt op een donkere badge is geen bericht."""
    scherm_zet(SCHERM_NORMAAL)
    try:
        _display().trigger_activity()
        return True
    except Exception:
        return False


def bridge_available():
    return _service is not None


# --- tijd -------------------------------------------------------------------

def posix_zone():
    """De POSIX-tijdzonestring om mee om te rekenen.

    Neem wat de badge zelf is ingesteld, zodat de Instellingen-app de enige plek
    blijft om het te wijzigen, en val terug op de configuratie. De voorkeur is
    op deze firmware een attribuut, op andere een methode."""
    try:
        import mpos.time
        pref = mpos.time.TimeZone.timezone_preference
        if callable(pref):
            pref = pref()
        if pref and pref != "Etc/GMT":
            zone = mpos.time.TimeZone.timezone_to_posix_time_zone(pref)
            if zone:
                return zone
    except Exception:
        pass
    return TIMEZONE


def local_parts(epoch):
    """Een tijdstip uiteengelegd in lokale tijd, of None.

    De badge houdt zijn klok in UTC en `time.localtime()` geeft UTC terug, ook
    met de tijdzone op Europe/Brussels, dus een naïeve uitlezing zit er in de
    zomer twee uur naast. Een verkeerde tijd onder "Eten over 10 minuten" is
    erger dan geen tijd: reken om via de POSIX-zone, en geef op in plaats van te
    gokken. None betekent hier dus echt: ik weet het niet."""
    if not epoch:
        return None
    parts = None
    try:
        import mpos.time
        parts = mpos.time.localPTZtime.tztime(epoch, posix_zone())
    except Exception:
        try:
            import time as _time
            parts = _time.localtime(epoch)
        except Exception:
            return None
    if parts is None or len(parts) < 6:
        return None
    if parts[0] < 2024:          # klok nooit gesynchroniseerd, verzin geen tijd
        return None
    return parts


def nu_epoch():
    """Nu, in de telling die local_parts verwacht.

    Dat is `time.time()` en niet `mpos.time.epoch_seconds()`. Die twee tellen
    niet vanaf hetzelfde punt: MicroPython telt vanaf 2000 en `epoch_seconds()`
    geeft Unix-seconden terug. Het verschil is 946684800, en dat is precies
    10957 hele dagen. Daardoor klopte het uur wel en de datum niet: de badge zei
    donderdag 17 augustus terwijl het dinsdag de 18e was, en de test zag er
    niets van omdat die zijn tijdstippen zelf aanlevert.

    Een eigen functie zodat een test hem kan vervangen; de klok van een badge is
    niet iets waar een test op wil wachten."""
    try:
        return int(time.time())
    except Exception:
        return 0


def clock_text(epoch):
    """De tijd zoals een keukenklok hem toont, of "" als hij niet te vertrouwen is."""
    parts = local_parts(epoch)
    if parts is None:
        return ""
    return "%02d:%02d" % (parts[3], parts[4])


DAGEN = ("ma", "di", "wo", "do", "vr", "za", "zo")
MAANDEN = ("jan", "feb", "mrt", "apr", "mei", "jun",
           "jul", "aug", "sep", "okt", "nov", "dec")


def date_text(epoch):
    """"di 18 aug", of "" als de klok niet gezet is.

    Kort en in kleine letters, want dit staat onder een klok en niet in een
    brief."""
    parts = local_parts(epoch)
    if parts is None:
        return ""
    dag = DAGEN[parts[6] % 7] if len(parts) > 6 else ""
    maand = MAANDEN[(parts[1] - 1) % 12]
    return ("%s %d %s" % (dag, parts[2], maand)).strip()


def is_night(epoch, van=None, tot=None):
    """Valt dit tijdstip in het nachtvenster?

    Het venster loopt bijna altijd over middernacht heen, dus 23 tot 7 betekent
    23, 0, 1 ... 6 en niet niets. Van gelijk aan tot is hoe je zegt dat er geen
    nacht is; een venster van nul uur en een venster van vierentwintig uur zijn
    dezelfde twee getallen, en de eerste lezing is de veilige."""
    van = NIGHT_FROM if van is None else van
    tot = NIGHT_TO if tot is None else tot
    try:
        van = int(van) % 24
        tot = int(tot) % 24
    except (TypeError, ValueError):
        return False
    if van == tot:
        return False
    parts = local_parts(epoch)
    if parts is None:
        return False
    uur = parts[3]
    if van < tot:
        return van <= uur < tot
    return uur >= van or uur < tot


# --- telemetrie -------------------------------------------------------------

def os_release():
    """De MicroPythonOS-versie, voor de apparaatpagina in Home Assistant."""
    try:
        import mpos
        return str(mpos.BuildInfo.version.release)
    except Exception:
        return None


def battery_reading():
    """Batterij, spanning en signaalsterkte, voor zover deze badge het weet.

    Elk veld is optioneel en ontbreken is geen fout: een badge op USB zonder cel,
    of een firmware zonder de ADC aangesloten, hoort nog steeds de signaalsterkte
    te melden die hij wel kent in plaats van helemaal niets."""
    state = {}
    try:
        import mpos
        manager = mpos.BatteryManager
        if manager.has_battery():
            percentage = manager.get_battery_percentage()
            if percentage is not None:
                state["battery"] = int(round(percentage))
            volt = manager.read_battery_voltage()
            if volt:
                state["voltage"] = round(volt, 2)
    except Exception as e:
        print("badge: geen batterijmeting:", e)
    try:
        import network
        state["rssi"] = network.WLAN(network.STA_IF).status("rssi")
    except Exception:
        pass
    return state


# sleutel, naam in Home Assistant, device class, eenheid, decimalen
TELEMETRY = (
    ("battery", "Battery", "battery", "%", 0),
    ("voltage", "Battery voltage", "voltage", "V", 2),
    ("rssi", "WiFi signal", "signal_strength", "dBm", 0),
)


def discovery_payloads():
    """De MQTT-discoveryberichten die Home Assistant de sensoren laten maken.

    Gesleuteld op het MAC van de badge, niet op zijn naam, zodat hernoemen de
    bestaande entiteiten bijwerkt in plaats van er een tweede dode set naast te
    laten staan. Home Assistant houdt zo ook de historiek.

    De korte sleutels zijn geen slordigheid: dit is de afgekorte vorm van het
    discoveryschema, en deze payloads gaan over een radio in een slaapkamer."""
    device = {
        "ids": ["fri3d_badge_%s" % DEVICE_SUFFIX],
        "name": "Badge %s" % titlecase(BADGE_NAME),
        "mf": "Fri3d Camp",
        "mdl": "Fri3d 2026 badge",
    }
    release = os_release()
    if release:
        device["sw"] = release

    out = []
    for key, name, device_class, unit, decimals in TELEMETRY:
        out.append((
            "%s/sensor/badge_%s/%s/config" % (DISCOVERY_PREFIX, DEVICE_SUFFIX,
                                              key),
            {
                "name": name,
                "uniq_id": "fri3d_badge_%s_%s" % (DEVICE_SUFFIX, key),
                "obj_id": "badge_%s_%s" % (BADGE_NAME, key),
                "stat_t": TOPIC_STATE,
                "avty_t": TOPIC_STATUS,
                "val_tpl": "{{ value_json.%s }}" % key,
                "dev_cla": device_class,
                "stat_cla": "measurement",
                "unit_of_meas": unit,
                "sug_dsp_prc": decimals,
                "ent_cat": "diagnostic",
                "dev": device,
            },
        ))
    return out


# --- het weer ---------------------------------------------------------------
# Home Assistant weet wat voor weer het wordt en de badge niet. Eén retained
# bericht op een gedeeld topic is genoeg: de badge hoeft dan niets op te vragen,
# heeft na een herstart meteen weer iets te tonen, en tien badges lezen hetzelfde
# bericht. Het topic staat los van de naam van de badge, want het weer ook.

WEER_VELDEN = (
    ("toestand", ("toestand", "state", "condition", "weer")),
    ("nu", ("nu", "now", "temp", "temperature", "current")),
    ("max", ("max", "high", "temp_max", "temperature_max")),
    ("min", ("min", "low", "templow", "temp_min", "temperature_min")),
)


def parse_weer(payload):
    """Een weerbericht uit MQTT, of {} als er niets bruikbaars in staat.

    Ruim in wat het accepteert: dit komt uit een template in andermans
    configuratie, en een sjabloon dat één keer null oplevert mag geen lege klok
    geven. Elk veld apart: een ontbrekende maximumtemperatuur is geen reden om
    de rest weg te gooien."""
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = payload.decode("utf-8")
        except Exception:
            return {}
    if isinstance(payload, str):
        payload = payload.strip()
        if not payload:
            return {}
        try:
            payload = json.loads(payload)
        except Exception:
            return {}
    if not isinstance(payload, dict):
        return {}
    uit = {}
    for naam, sleutels in WEER_VELDEN:
        for sleutel in sleutels:
            if sleutel not in payload:
                continue
            waarde = payload[sleutel]
            if waarde is None or waarde == "":
                continue
            if naam == "toestand":
                uit[naam] = str(waarde)
            else:
                try:
                    uit[naam] = float(waarde)
                except (TypeError, ValueError):
                    continue
            break
    return uit


def _on_weer(topic_str, payload):
    global weer
    nieuw = parse_weer(payload)
    if nieuw:
        weer = nieuw


# --- scherm -----------------------------------------------------------------
# MicroPythonOS heeft geen schermtimeout en geen helderheidsinstelling; de
# Settings-app is uitgepakt en nagekeken. De onderdelen bestaan wel, alleen niet
# aan elkaar geknoopt. `main_display.get_backlight()` geeft -1: die LVGL-weg is
# op deze firmware niet aangesloten, de helderheid loopt over de I2C-expander.

def _display():
    import mpos.ui
    return mpos.ui.main_display


def _brightness(level):
    try:
        _expander().lcd_brightness = int(level)
        return True
    except Exception as e:
        print("badge: helderheid niet te zetten:", e)
        return False


def _brightness_now():
    try:
        return int(_expander().lcd_brightness)
    except Exception:
        return None


_bright_saved = None     # de helderheid van de app, van voor de klok of het uit


def _onthoud_helderheid():
    """Bewaren waar de gebruiker het scherm op had staan.

    Alleen bij het verlaten van NORMAAL. Zou de klokhelderheid hier ook in
    belanden, dan wordt een badge die 's nachts op 5 stond de volgende ochtend
    op 5 wakker, en dan lijkt hij stuk."""
    global _bright_saved
    huidig = _brightness_now()
    if huidig:
        _bright_saved = huidig


def _screen_set(aan):
    """De achtergrondverlichting aan of uit, zonder verdere toestand.

    Blijft bestaan omdat het scherm op meer dan één manier uit kan gaan, maar
    wie een overgang wil hoort scherm_zet() te gebruiken."""
    global screen_off
    if aan:
        if not screen_off:
            return False
        _brightness(_bright_saved if _bright_saved else 100)
        screen_off = False
        return True
    if screen_off:
        return False
    if not _brightness(0):
        return False
    screen_off = True
    return True


# De trappen waarlangs de klokhelderheid loopt. Ze staan hier en niet in het
# instelscherm, want de knoppen X en B lopen er ook langs en die worden hier
# afgehandeld. Overdag hoeft de klok niet fel: je staat ernaast als je hem leest.
# 's Nachts wel echt laag, want het verschil tussen 1 en 5 procent is in een
# donkere slaapkamer het verschil tussen een klok en een lamp.
KLOK_DAG_NIVEAUS = (10, 20, 30, 50, 75, 100)
KLOK_NACHT_NIVEAUS = (1, 2, 3, 5, 10, 20, 30, 50)


def stap(waarden, huidig, delta):
    """Een stap door een vaste reeks, zonder om te slaan.

    Omslaan van uit naar honderd met een misgetikte plus is precies wat je in
    een donkere kamer niet wil. Staat de huidige waarde niet in de reeks, dan
    wordt eerst de dichtstbijzijnde gezocht: wat in de voorkeuren staat kan uit
    een configbestand komen of van een oudere versie."""
    try:
        index = waarden.index(huidig)
    except ValueError:
        index = 0
        afstand = None
        for i, kandidaat in enumerate(waarden):
            try:
                d = abs(kandidaat - huidig)
            except TypeError:
                continue
            if afstand is None or d < afstand:
                afstand = d
                index = i
    return waarden[min(len(waarden) - 1, max(0, index + delta))]


def klok_niveau_stap(delta):
    """De klok een trapje feller of donkerder, en onthouden.

    De joystick omhoog is feller en omlaag is donkerder, en ze werken alleen
    terwijl de klok op het scherm staat. Welke van de twee waarden je bijstelt
    hangt af van waar je bent: 's nachts de nachtwaarde, overdag de dagwaarde. Zo
    dim je de klok vanuit bed en staat hij morgenavond meteen goed."""
    global CLOCK_DAY, CLOCK_NIGHT, _vorige_stil, _kijk_tot
    nacht = is_night(nu_epoch())
    if nacht:
        CLOCK_NIGHT = stap(KLOK_NACHT_NIVEAUS, CLOCK_NIGHT, delta)
        sleutel, waarde = "clock_night", CLOCK_NIGHT
    else:
        CLOCK_DAY = stap(KLOK_DAG_NIVEAUS, CLOCK_DAY, delta)
        sleutel, waarde = "clock_day", CLOCK_DAY
    _klok_licht(nacht)

    # De joystick reset de inactiviteitsteller net zo goed als een vinger, want
    # het OS leest hem ook. Zonder dit zou de badge klaarwakker worden van de
    # beweging waarmee je hem juist wilde dimmen. Dezelfde truc als bij de
    # S-knop: de daling hier verbruiken, zodat de volgende tik er geen aanraking
    # meer in ziet.
    _vorige_stil = 0
    if screen_state == SCHERM_KIJK:
        # Wie aan de helderheid draait is aan het kijken.
        _kijk_tot = _seconden() + KIJK_S
    try:
        SharedPreferences(PREFS_APP_ID).edit().put_int(sleutel, waarde).commit()
    except Exception as e:
        print("badge: klokhelderheid niet bewaard:", e)
    return waarde


def klok_helderheid(nacht):
    """Hoe fel de klok mag staan. Nooit nul: dat is uit en niet een klok."""
    niveau = CLOCK_NIGHT if nacht else CLOCK_DAY
    try:
        niveau = int(niveau)
    except (TypeError, ValueError):
        niveau = 5
    return max(1, min(100, niveau))


# De overlay wordt pas gemaakt als iemand hem voor het eerst nodig heeft, en
# leeft in bgclock omdat dit bestand geen LVGL aanraakt. Een service hoort geen
# scherm te hebben; de klok is de ene uitzondering, en die staat daarom apart.
_overlay = None
_klok_seconde = None
_klok_bright = None      # wat er als laatste naar de expander geschreven is


def _klok_licht(nacht):
    """De klokhelderheid zetten, en alleen als hij verandert.

    De lus draait tien keer per seconde. Elke keer dezelfde waarde over I2C naar
    de expander schrijven is tien keer per seconde busverkeer voor niets, en het
    houdt de bus bezet voor wie er wel iets te zeggen heeft."""
    global _klok_bright
    niveau = klok_helderheid(nacht)
    if niveau == _klok_bright:
        return False
    _klok_bright = niveau
    return _brightness(niveau)


def _klok_toon(nacht):
    global _overlay
    if _overlay is None:
        if _bgclock is None:
            return False
        try:
            _overlay = _bgclock.ClockOverlay()
        except Exception as e:
            print("badge: klokscherm niet beschikbaar:", e)
            return False
    global screen_off
    try:
        _overlay.toon()
    except Exception as e:
        print("badge: klok niet te tonen:", e)
        return False
    _klok_licht(nacht)
    screen_off = False
    return True


def _klok_weg():
    # De seconde en de helderheid vergeten, anders slaat de eerste update na het
    # opnieuw tonen over en staat er een lege klok tot de minuut verspringt.
    global _klok_seconde, _klok_bright
    _klok_seconde = None
    _klok_bright = None
    if _overlay is None:
        return False
    try:
        return _overlay.weg()
    except Exception as e:
        print("badge: klok niet weg te halen:", e)
        return False


def _klok_bijwerken():
    """De klok bijwerken, hoogstens één keer per seconde.

    De lus draait tien keer per seconde voor de knop. Elke keer de tijdzone
    omrekenen en twee strings opbouwen voor een klok die minuten toont is werk
    dat een ESP32 beter niet doet."""
    global _klok_seconde
    if _overlay is None:
        return False
    epoch = nu_epoch()
    if epoch == _klok_seconde:
        return False
    _klok_seconde = epoch
    try:
        return _overlay.werk_bij(clock_text(epoch), date_text(epoch),
                                 battery_pct, weer, titlecase(BADGE_NAME))
    except Exception as e:
        print("badge: klok niet bij te werken:", e)
        return False


def scherm_zet(nieuw, nacht=False):
    """De enige plek waar de schermtoestand verandert."""
    global screen_state
    if nieuw == screen_state:
        if nieuw in (SCHERM_KLOK, SCHERM_KIJK):
            # De klok blijft staan terwijl het nacht wordt: dan hoort hij mee te
            # dimmen zonder dat er een toestand verandert.
            _klok_licht(nacht)
        return False
    vorig = screen_state
    screen_state = nieuw
    if vorig == SCHERM_NORMAAL:
        _onthoud_helderheid()
    if nieuw == SCHERM_NORMAAL:
        _klok_weg()
        if screen_off:
            _screen_set(True)
        else:
            _brightness(_bright_saved if _bright_saved else 100)
    elif nieuw == SCHERM_UIT:
        _klok_weg()
        _screen_set(False)
    else:
        if not _klok_toon(nacht):
            # Zonder klok is dit gewoon donker; een verlicht leeg scherm is het
            # slechtste van de twee.
            screen_state = SCHERM_UIT
            _screen_set(False)
            return True
        _klok_bijwerken()
    return True


# --- de knoppen -------------------------------------------------------------
# Gepolst en niet op een interrupt: de firmware leest deze pinnen zelf ook uit
# voor het toetsenbord, en er een irq bij hangen is een risico voor iets dat
# elke app gebruikt. Lezen is dat niet.
#
# De S-knop is een gewone GPIO (btn_start, Pin 0, laag als hij ingedrukt is). De
# joystick zit op de I/O-expander. De volgorde van `digital` staat in de driver
# van MicroPythonOS (drivers/indev/fri3d_2026_expander.py) en is:
#
#   0 usb  1 joy_rechts  2 joy_links  3 joy_omlaag  4 joy_omhoog
#   5 menu  6 B  7 A  8 Y  9 X  10 lader_klaar  11 lader_bezig
#
# Waarom de joystick en niet X en B, die daar naast liggen: die twee doen al iets
# in het OS zelf. Die driver roept bij elke druk eerst zijn eigen navigatiehaak
# aan, en X is ESC (een scherm terug) en B is NEXT (focus vooruit). Ze kapen zou
# betekenen dat de app onder de klok intussen achteruit navigeert, en dat is niet
# vanaf hier uit te zetten.
JOY_OMHOOG = 4
JOY_OMLAAG = 3

# Alles wat een vinger kan indrukken: de joystick in vier richtingen, de
# menuknop, en B, A, Y en X. Niet 0, 10 en 11: dat zijn de USB-stekker en de
# twee lampjes van de lader, en die gaan vanzelf aan en uit.
KNOPPEN = (1, 2, 3, 4, 5, 6, 7, 8, 9)

_knop = None
_knop_vorige = 1
_expander_vorige = None


def _knop_pin():
    """Het pinobject van de S-knop, of None op een badge die hem niet aanbiedt."""
    global _knop
    if _knop is not None:
        return _knop or None
    _knop = False
    try:
        import mpos.board as board
        kandidaat = getattr(board, "btn_start", None)
        if kandidaat is None:
            # De bekabeling zit in een submodule die naar het bord heet. Die
            # staat pas in dir() als iemand hem geïmporteerd heeft, dus eerst
            # zelf proberen en pas daarna rondkijken.
            try:
                __import__("mpos.board.fri3d_2026")
            except Exception:
                pass
            for naam in dir(board):
                if naam.startswith("_"):
                    continue
                kandidaat = getattr(getattr(board, naam), "btn_start", None)
                if kandidaat is not None:
                    break
        if kandidaat is not None and hasattr(kandidaat, "value"):
            _knop = kandidaat
        else:
            print("badge: geen S-knop in mpos.board")
    except Exception as e:
        print("badge: S-knop niet gevonden:", e)
    return _knop or None


def knop_flank():
    """True op het moment dat S ingedrukt wordt, niet zolang hij vastgehouden is.

    Wordt elke lus aangeroepen, ook met het scherm aan, want anders is de eerste
    meting in het donker een vergelijking met een stand van minuten geleden."""
    global _knop_vorige
    pin = _knop_pin()
    if pin is None:
        return False
    try:
        stand = int(pin.value())
    except Exception:
        return False
    neer = _knop_vorige == 1 and stand == 0
    _knop_vorige = stand
    return neer


def expander_flank():
    """Wat er aan de knoppen gebeurde sinds de vorige lus.

    Geeft (richting, beweging) terug. `richting` is +1 op het moment dat de
    joystick omhoog gaat en -1 bij omlaag, en alleen op de flank: vasthouden is
    één stap. `beweging` is True zodra er wat dan ook aan de negen knoppen
    verandert of ingedrukt staat.

    Die tweede is nodig omdat elke knop de inactiviteitsteller reset, ook de
    richtingen die hier niets doen. Zonder dat te weten ging de klok weg zodra
    je de joystick aanraakte: links of rechts duwen deed niets, maar wekte de
    badge wel, en dat is precies het tegenovergestelde van wat je bedoelde.

    Wordt elke lus aangeroepen, ook als de klok niet staat, want anders is de
    eerste meting een vergelijking met een stand van minuten geleden."""
    global _expander_vorige
    try:
        digitaal = _expander().digital
        nu = tuple(bool(digitaal[i]) for i in KNOPPEN)
    except Exception:
        return 0, False
    vorig = _expander_vorige
    _expander_vorige = nu
    if vorig is None:
        return 0, any(nu)
    beweging = any(nu) or nu != vorig
    richting = 0
    for plek, index in enumerate(KNOPPEN):
        if not nu[plek] or vorig[plek]:
            continue                      # niet nieuw ingedrukt
        if index == JOY_OMHOOG:
            richting = 1
        elif index == JOY_OMLAAG:
            richting = -1
    return richting, beweging


def idle_ms():
    try:
        return int(_display().get_inactive_time())
    except Exception:
        return 0


_vorige_stil = 0
_kijk_tot = 0
_kijk_negeer = 0         # tot wanneer een aanraking in KIJK genegeerd wordt


def screen_tick():
    """De schermtoestand bijwerken. Draait elke LUS_TICK.

    Drie dingen om te weten.

    Aanraking wordt niet aan de teller zelf afgelezen maar aan het teruglopen
    ervan. Een druk op S reset de inactiviteitsteller net zo goed als een vinger,
    dus "de teller staat laag" betekent niet "er is net iemand op het scherm
    geweest". Dat de teller *daalt* betekent wel dat er iets gebeurd is, en de
    knopafhandeling hieronder verbruikt die daling voor hij iets kan wekken.

    De tik die het scherm wekt komt ook aan bij de knop eronder. Dat is hoe deze
    firmware het aanlevert en het is hier niet te onderscheppen.

    Wekken op een binnenkomend bericht is de taak van de app die het bericht
    krijgt: die roept wake() aan."""
    global _vorige_stil, _kijk_tot, _kijk_negeer
    gedrukt = knop_flank()
    richting, knopbeweging = expander_flank()
    stil = idle_ms()
    activiteit = stil < _vorige_stil
    _vorige_stil = stil

    if knopbeweging and screen_state in (SCHERM_KLOK, SCHERM_KIJK):
        # Een knop is geen vinger. Terwijl de klok staat mag alleen een
        # aanraking hem wegnemen, en de reset die een knop achterlaat wordt hier
        # verbruikt zodat hij dat niet alsnog doet.
        activiteit = False
        _vorige_stil = 0

    if SCREEN_OFF_S <= 0:
        scherm_zet(SCHERM_NORMAAL)
        return
    epoch = nu_epoch()
    nacht = is_night(epoch)
    donker = screen_state in (SCHERM_UIT, SCHERM_KIJK)

    if gedrukt and donker:
        if screen_state == SCHERM_UIT:
            # Even kijken hoe laat het is. De klok en verder niets.
            nu = _seconden()
            _kijk_tot = nu + KIJK_S
            _kijk_negeer = nu + 2
            scherm_zet(SCHERM_KIJK, nacht)
        else:
            # Nog eens: terug naar waar je was.
            scherm_zet(SCHERM_NORMAAL)
            try:
                _display().trigger_activity()
            except Exception:
                pass
        return

    if richting and screen_state in (SCHERM_KLOK, SCHERM_KIJK):
        # Joystick omhoog is feller, omlaag is donkerder. Alleen terwijl de klok
        # staat: anders is de joystick van de app die eronder draait.
        klok_niveau_stap(richting)
        return

    if screen_state == SCHERM_KIJK:
        # De eerste seconden wordt een aanraking genegeerd. De druk op S die
        # deze toestand opriep reset de inactiviteitsteller een fractie later,
        # en dat is niet te onderscheiden van een vinger. Daarna telt een
        # aanraking gewoon: de klok laat een tik door naar de app eronder, en
        # dan hoort die app ook zichtbaar te worden.
        if _seconden() >= _kijk_tot:
            scherm_zet(SCHERM_UIT)
        elif activiteit and _seconden() >= _kijk_negeer:
            scherm_zet(SCHERM_NORMAAL)
        else:
            _klok_bijwerken()
        return

    if stil < SCREEN_OFF_S * 1000:
        if screen_state != SCHERM_NORMAAL and activiteit:
            scherm_zet(SCHERM_NORMAAL)
        return

    if IDLE_MODE != "klok":
        scherm_zet(SCHERM_UIT)
        return
    if nacht and stil >= 2 * SCREEN_OFF_S * 1000:
        # 's Nachts eerst een tijd de gedimde klok, en daarna alsnog donker.
        scherm_zet(SCHERM_UIT)
        return
    scherm_zet(SCHERM_KLOK, nacht)
    _klok_bijwerken()


def _seconden():
    try:
        return time.time()
    except Exception:
        return 0


class BadgeService(Service):

    def __init__(self):
        super().__init__()
        self._mqtt = None
        self._running = False
        self._next_try = 0
        self._backoff = RETRY_MIN
        self._last_ping = 0
        self._next_state = 0
        self._live_name = None    # de naam waaronder we het laatst publiceerden

    def onCreate(self):
        global _service
        # Een tweede instantie draait zijn eigen loop naar dezelfde broker met
        # dezelfde client-id, en de broker gooit de oudste van twee clients met
        # dezelfde id eruit. Die twee duwen elkaar dan om beurten van de lijn,
        # voor altijd. Zet de oude stil.
        previous = _service
        if previous is not None and previous is not self:
            print("badge: vorige service-instantie stopgezet")
            try:
                previous.onDestroy()
            except Exception as e:
                print("badge: kon de vorige service niet stoppen:", e)
        _service = self
        migrate_prefs()
        load_prefs()
        # Het weer hangt aan een gedeeld topic en niet aan de naam van deze
        # badge, dus het volledige topic gaat erin; topic() laat dat staan.
        if WEER_TOPIC:
            subscribe(WEER_TOPIC, _on_weer)
        print("badge: service voor", BADGE_NAME, "prefix", TOPIC_PREFIX)

    def onStart(self, intent=None):
        if self._running:
            # Twee keer gestart worden is geen hypothese: alles wat de app start
            # kan de services uit het manifest opnieuw starten, en de tweede loop
            # deelt de client van deze instantie terwijl hij ermee racet.
            print("badge: draait al, geen tweede loop")
            return
        self._running = True
        TaskManager.create_task(self._run())

    def onDestroy(self):
        self._running = False
        # Een nette afsluiting laat de last will niet afgaan, dus zou de badge
        # in Home Assistant "online" blijven tot de volgende herstart.
        self.publish_raw(TOPIC_STATUS, "offline", retain=True)
        self._close()

    def resubscribe(self):
        """De verbinding laten vallen zodat de loop op de nieuwe naam terugkomt."""
        print("badge: naam gewijzigd, opnieuw abonneren als", BADGE_NAME)
        self._retire_topics()
        self._close()
        self._backoff = RETRY_MIN
        self._next_try = 0

    # --- hoofdlus ----------------------------------------------------------

    async def _run(self):
        volgende_pomp = 0
        while self._running:
            now = time.time()
            if now >= volgende_pomp:
                volgende_pomp = now + TICK
                try:
                    self._pump()
                except Exception as e:        # de loop mag nooit sterven
                    print("badge: lusfout:", e)
                    self._close()
            try:
                screen_tick()
            except Exception as e:
                print("badge: schermfout:", e)
            await TaskManager.sleep(LUS_TICK)

    def _pump(self):
        now = time.time()
        if self._mqtt is None:
            if now >= self._next_try and self._wifi_up():
                self._connect(now)
            return
        try:
            self._mqtt.check_msg()
            if now - self._last_ping >= PING_EVERY:
                self._mqtt.ping()
                self._last_ping = now
            if now >= self._next_state:
                self._publish_state(now)
        except Exception as e:
            print("badge: verbinding verloren:", e)
            self._fail(e, now)

    def _wifi_up(self):
        try:
            import network
            wlan = network.WLAN(network.STA_IF)
            return bool(wlan.active() and wlan.isconnected())
        except Exception:
            return False

    def _connect(self, now):
        global connected, last_error
        try:
            from umqtt.simple import MQTTClient
        except ImportError as e:
            last_error = "umqtt.simple ontbreekt"
            print("badge:", last_error, e)
            self._next_try = now + RETRY_MAX
            return
        try:
            try:
                client = MQTTClient(
                    CLIENT_ID, MQTT_BROKER, port=MQTT_PORT,
                    user=MQTT_USER, password=MQTT_PASS, keepalive=60,
                    socket_timeout=SOCKET_TIMEOUT,
                )
            except TypeError:
                # De umqtt.simple in deze firmware kent geen socket_timeout.
                client = MQTTClient(
                    CLIENT_ID, MQTT_BROKER, port=MQTT_PORT,
                    user=MQTT_USER, password=MQTT_PASS, keepalive=60,
                )
            client.set_callback(self._on_message)
            # Vóór het verbinden bij de broker geregistreerd, zodat een badge die
            # buiten bereik loopt of leegraakt door de broker offline gezet wordt
            # in plaats van eeuwig zijn laatste batterijstand te blijven tonen.
            try:
                client.set_last_will(TOPIC_STATUS, "offline", retain=True)
            except Exception as e:
                print("badge: geen last will:", e)
            client.connect()
            self._mqtt = client
            self._backoff = RETRY_MIN
            self._last_ping = now
            connected = True
            last_error = None
            for suffix in _subscribers:
                self.subscribe_now(suffix)
            print("badge: verbonden als", CLIENT_ID)
            self._announce(now)
        except Exception as e:
            self._fail(e, now)

    def subscribe_now(self, suffix):
        if self._mqtt is None:
            return False
        vol = topic(suffix)
        try:
            self._mqtt.subscribe(vol)
            print("badge: geabonneerd op", vol)
            return True
        except Exception as e:
            print("badge: abonneren op %s mislukt:" % vol, e)
            self._fail(e, time.time())
            return False

    def _fail(self, error, now):
        global connected, last_error
        self._close()
        last_error = describe_error(error)
        self._next_try = now + self._backoff
        self._backoff = min(self._backoff * 2, RETRY_MAX)

    def _close(self):
        global connected
        connected = False
        if self._mqtt is not None:
            try:
                self._mqtt.disconnect()
            except Exception:
                pass
            self._mqtt = None

    # --- binnenkomend ------------------------------------------------------

    def _on_message(self, topic_bytes, msg):
        """Doorgeven aan wie zich op dit achtervoegsel abonneerde.

        Een callback die gooit mag de andere abonnees niet meenemen, en al
        helemaal niet de verbinding."""
        try:
            volledig = topic_bytes.decode("utf-8")
        except Exception:
            volledig = str(topic_bytes)
        for suffix, callback in _subscribers.items():
            if topic(suffix) == volledig:
                try:
                    callback(volledig, msg)
                except Exception as e:
                    print("badge: abonnee op %s gooide:" % suffix, e)

    # --- uitgaand ----------------------------------------------------------

    def publish_raw(self, topic_str, payload, retain=False):
        """Eén publish, met een dict onderweg omgezet naar JSON."""
        if self._mqtt is None or not topic_str:
            return False
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        try:
            self._mqtt.publish(topic_str, payload, retain=retain)
            return True
        except Exception as e:
            print("badge: publish naar %s mislukt:" % topic_str, e)
            self._fail(e, time.time())
            return False

    def _announce(self, now):
        """Zeggen wat deze badge is, en dat hij er is.

        Alles retained, zodat een Home Assistant die morgenochtend herstart de
        sensoren en hun laatste waarden van de broker krijgt zonder dat de badge
        er wakker voor hoeft te zijn. Bij elke herverbinding opnieuw, en zo wijst
        een hernoemde badge zijn bestaande entiteiten ook naar het nieuwe topic."""
        self._live_name = BADGE_NAME
        if not self.publish_raw(TOPIC_STATUS, "online", retain=True):
            return
        for topic_str, config in discovery_payloads():
            if not self.publish_raw(topic_str, config, retain=True):
                return
        self._publish_state(now)

    def _publish_state(self, now):
        global battery_pct, battery_volt, wifi_rssi
        self._next_state = now + STATE_EVERY
        state = battery_reading()
        battery_pct = state.get("battery")
        battery_volt = state.get("voltage")
        wifi_rssi = state.get("rssi")
        if not state:
            return False           # niets meetbaar; publiceer geen {}
        state["name"] = BADGE_NAME
        return self.publish_raw(TOPIC_STATE, state, retain=True)

    def _retire_topics(self):
        """Opruimen wat we publiceerden onder de naam die we achterlaten.

        Retained berichten overleven de client die ze stuurde. Zonder dit laat
        een badge die van alice naar bob hernoemd wordt een retained batterijstand
        op alice's topic achter die niets ooit nog bijwerkt en niets ooit nog
        opruimt. Een lege payload is hoe MQTT er een verwijdert."""
        old = self._live_name
        self._live_name = None
        if not old or old == BADGE_NAME or self._mqtt is None:
            return
        print("badge: retained toestand van", old, "gewist")
        for suffix in ("state", "status"):
            try:
                self._mqtt.publish("home/badges/%s/%s" % (old, suffix), "",
                                   retain=True)
            except Exception as e:
                print("badge: kon %s niet wissen:" % suffix, e)
                return
