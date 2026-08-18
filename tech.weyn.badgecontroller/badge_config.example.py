"""Configuratie voor de Badge-app.

Kopieer dit bestand naar `badge_config.py` en vul het in. Die kopie is
gitignored, want het brokeradres en het MQTT-wachtwoord horen niet in een
repository.

    cp tech.weyn.badgecontroller/badge_config.example.py tech.weyn.badgecontroller/badge_config.py

Alles hieronder is ook op de badge zelf in te stellen, achter de Badge-app in de
launcher, en wat daar staat wint. Dit bestand leeg laten is dus een prima keuze:
dan wordt elke badge op de badge ingesteld en staat er nergens een wachtwoord in
een bestand.
"""

# Hoe deze badge heet voor er iemand een naam intypt. De naam staat in de
# MQTT-topics (home/badges/<naam>/...) en in de sensornamen in Home Assistant.
# Kleine letters, geen spaties; wat je hier zet gaat toch door normalize_name.
BADGE_NAME = "badge"

# Startwaarden voor de broker, voor een badge die nog niemand heeft ingesteld.
# Alle vier zijn ook op de badge te wijzigen, achter Verbinding.
#
# Gebruik het IP van Home Assistant en geen .local naam: mDNS is onbetrouwbaar
# op een ESP32. De Mosquitto add-on laat anonieme clients standaard niet toe,
# dus geef de badges hun eigen login: een `logins:` regel in de configuratie van
# de add-on, of een Home Assistant-gebruiker voor ze.
MQTT_BROKER = ""
MQTT_PORT = 1883
MQTT_USER = None
MQTT_PASS = None

# Waar Home Assistant naar MQTT-discovery luistert. Zo verschijnen de batterij-
# en signaalsensoren vanzelf, zonder dat er YAML voor geschreven wordt.
# "homeassistant" is de standaard en bijna niemand wijzigt hem; wie het wel deed
# weet dat hij het deed.
DISCOVERY_PREFIX = "homeassistant"

# Na hoeveel seconden zonder aanraking de badge met rust gelaten wordt. 0
# betekent nooit. Ook in te stellen op de badge. Let op: de tik die het scherm
# wakker maakt komt ook aan bij de knop eronder; dat is hoe deze firmware het
# aanlevert.
SCREEN_OFF_S = 0

# Wat er dan gebeurt: "uit" is donker, "klok" laat een gedimde klok staan met de
# datum, de batterij en het weer. De klok is een overlay boven de app die op dat
# moment draait, dus terugkeren is niets meer dan hem weghalen.
IDLE_MODE = "uit"

# Hoe fel die klok mag staan, overdag en 's nachts, 1..100. Nul zou uit zijn en
# dat is geen klok. Terwijl de klok op het scherm staat regelt de joystick het
# ook: omhoog is feller, omlaag donkerder. Dat past de waarde aan die op dat
# moment geldt, dus dim je hem vanuit bed, dan staat de nachtwaarde morgenavond
# meteen goed.
CLOCK_DAY = 30
CLOCK_NIGHT = 5

# Het nachtvenster in hele uren lokale tijd. Het loopt over middernacht heen, dus
# 23 tot 7 is 23, 0, 1 tot en met 6. Gelijke waarden betekenen: geen nacht.
#
# Binnen het venster gaat de klok naar CLOCK_NIGHT, en na nog eens SCREEN_OFF_S
# gaat hij alsnog helemaal uit. Een druk op de S-knop laat hem dan tien seconden
# zien; nog een druk brengt je terug naar de app die eronder stond.
NIGHT_FROM = 23
NIGHT_TO = 7

# Waar het weerbericht vandaan komt. Eén retained bericht van Home Assistant op
# een topic dat los staat van de naam van de badge, want het weer staat daar ook
# los van: tien badges lezen hetzelfde bericht. De YAML voor de HA-kant staat in
# de README. Leeg maken zet het uit; de klok toont dan alleen tijd, datum en
# batterij.
WEER_TOPIC = "home/badges/weer"

# Het kleine debug-lampje op de I2C-expander, 0..100. Nul is uit, en dat is de
# standaard: af fabriek staat hij op 50 en brandt hij dus altijd, ook 's nachts
# op een badge die ligt te laden. Ook in te stellen op de badge, achter
# "Scherm en lichtjes".
#
# Dit gaat niet over de drie lampjes van de lader. C (rood) brandt tijdens het
# laden, + (groen) als er USB in zit, en S (groen) als de batterij vol is. Die
# hangen aan de CHRG- en STDBY-pinnen van de TP4056 en aan VUSB, volgens de
# voedingspagina van het schema. Uitgangen van de laadchip zelf: geen software
# komt daarbij, alleen tape of een soldeerbout.
DEBUG_LED = 0

# POSIX-tijdzone, als terugval voor het omrekenen van tijdstippen. De badge houdt
# zijn klok in UTC en time.localtime() geeft UTC terug, ook met de tijdzone goed
# ingesteld. Wat in Instellingen op de badge staat wint hierover. De string draagt
# de zomertijdregels, dus hij klopt ook na de wissel in oktober.
TIMEZONE = "CET-1CEST,M3.5.0,M10.5.0/3"
