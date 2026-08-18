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
  3. **Het scherm.** Uit na een tijd niets doen, en wakker bij aanraking.

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

Niets hier maakt LVGL-objecten aan: een service heeft geen scherm.
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

APP_FULLNAME = "be.weyn.badge"
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


LEGACY_PREFS_APP_ID = "be.weyn.dinerbadge"
LEGACY_KEYS = (("badge_name", "child_name", "string"),
               ("mqtt_host", "mqtt_host", "string"),
               ("mqtt_port", "mqtt_port", "int"),
               ("mqtt_user", "mqtt_user", "string"),
               ("mqtt_pass", "mqtt_pass", "string"))


def migrate_prefs():
    """Overnemen wat er onder Berichtjes stond, één keer.

    Deze instellingen zijn ooit op de badge getypt toen Berichtjes de verbinding
    nog bezat. Ze staan in de SharedPreferences van die app. Zonder deze stap
    valt een badge die al maanden werkt na een update terug op de standaard uit
    het configbestand, en moet iemand naam, broker, gebruiker en wachtwoord
    opnieuw intypen op een aanraakscherm. Draait alleen als er hier nog niets
    staat, dus wie eenmaal iets in de Badge-app zet wordt nooit meer overschreven.
    """
    try:
        prefs = SharedPreferences(PREFS_APP_ID)
        if prefs.get_string("badge_name", ""):
            return False
        oud = SharedPreferences(LEGACY_PREFS_APP_ID)
        editor = None
        overgenomen = []
        for nieuw_key, oud_key, soort in LEGACY_KEYS:
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
            return False
        editor.commit()
        print("badge: instellingen overgenomen van Berichtjes:",
              ", ".join(overgenomen))
        return True
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
    _screen_set(True)
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


def clock_text(epoch):
    """De tijd zoals een keukenklok hem toont, of "" als hij niet te vertrouwen is.

    De badge houdt zijn klok in UTC en `time.localtime()` geeft UTC terug, ook
    met de tijdzone op Europe/Brussels, dus een naïeve uitlezing zit er in de
    zomer twee uur naast. Een verkeerde tijd onder "Eten over 10 minuten" is
    erger dan geen tijd: reken om via de POSIX-zone, en geef op in plaats van te
    gokken."""
    if not epoch:
        return ""
    parts = None
    try:
        import mpos.time
        parts = mpos.time.localPTZtime.tztime(epoch, posix_zone())
    except Exception:
        try:
            import time as _time
            parts = _time.localtime(epoch)
        except Exception:
            return ""
    if parts is None or len(parts) < 5:
        return ""
    if parts[0] < 2024:          # klok nooit gesynchroniseerd, verzin geen tijd
        return ""
    return "%02d:%02d" % (parts[3], parts[4])


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


_bright_saved = None


def _screen_set(aan):
    """Scherm aan of uit. Onthoudt de helderheid van voor het uitgaan, zodat een
    badge die op 40 stond niet op 100 wakker wordt."""
    global screen_off, _bright_saved
    if aan:
        if not screen_off:
            return False
        _brightness(_bright_saved if _bright_saved else 100)
        screen_off = False
        return True
    if screen_off:
        return False
    huidig = _brightness_now()
    if huidig:
        _bright_saved = huidig
    if not _brightness(0):
        return False
    screen_off = True
    return True


def idle_ms():
    try:
        return int(_display().get_inactive_time())
    except Exception:
        return 0


def screen_tick():
    """Uit na SCREEN_OFF_S seconden niets doen, aan bij de eerste aanraking.

    Twee dingen om te weten. De tik die het scherm wekt komt ook aan bij de knop
    eronder, dus de eerste aanraking na het uitgaan kan iets indrukken; dat is
    hoe deze firmware het aanlevert en niet vanaf hier te onderscheppen. En het
    scherm wekken op een binnenkomend bericht is de taak van de app die het
    bericht krijgt: die roept wake() aan."""
    if SCREEN_OFF_S <= 0:
        if screen_off:
            _screen_set(True)
        return
    stil = idle_ms()
    if stil >= SCREEN_OFF_S * 1000:
        _screen_set(False)
    elif screen_off:
        _screen_set(True)


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
        while self._running:
            try:
                self._pump()
            except Exception as e:            # de loop mag nooit sterven
                print("badge: lusfout:", e)
                self._close()
            try:
                screen_tick()
            except Exception:
                pass
            await TaskManager.sleep(TICK)

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
