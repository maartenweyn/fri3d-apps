// ============================================================================
//  Fri3d Camp 2026 badge - behuizing + magnetische bureaudock
//  ------------------------------------------------------------------------
//  Geometrie gemeten uit Fri3D_Badge_2026_02.step (revisie 02),
//  github.com/Fri3dCamp/badge_2026_hw
//
//  Assenstelsel: oorsprong = midden PCB, Z = 0 op het bovenvlak van de PCB.
//  Onderdelen met positieve Z zitten aan de gebruikerskant.
//
//  Onderdelen:
//    part = "backshell"   achterschaal met magneetnesten
//    part = "frontplate"  frontplaat met schermrand
//    part = "dock"        bureaudock, badge onder 65 graden
//    part = "assembly"    alles samen met de badge erin (alleen om te kijken)
//
//  De rug en de voorkant zijn volledig gesloten. Geen schroeven: de frontplaat
//  klikt vast op zes losse punten in de lange randen. Op de twee kopse kanten
//  zit een wrikgleufje om hem er met een spudger weer af te halen.
//
//  Print: Prusa MK4S, PLA, 0.4 mm nozzle, 0.2 mm laaghoogte, geen supports.
//  Magneten: 8 x neodymium schijf 6 x 3 mm (4 in de schaal, 4 in de dock).
// ============================================================================

part = "assembly";
$fn = 64;

// ---------------------------------------------------------------- parameters
FIT      = 0.30;   // speling rondom de PCB (FDM, 0.4 mm nozzle)
WALL     = 2.40;   // wanddikte achterschaal
FWALL    = 2.00;   // wanddikte frontplaat
SKIN     = 0.80;   // materiaal tussen magneet en buitenvlak
MAG_D    = 6.00;   // magneetdiameter
MAG_H    = 3.00;   // magneetdikte
MAG_FIT  = 0.20;   // speling magneetnest (lijmen met secondelijm)
DOCK_ANG = 65;     // hoek van de badge t.o.v. het tafelblad
BACK_SCREWS = false; // true = extra M2 vanaf de rug; false = alleen de snap-fit
PORT_LABELS = false; // true = AUDIO en LoRa als opschrift in de frontplaat
BACK_TEXT   = true;  // false = ook FRI3D 2026 uit de rug halen
LORA_PORT   = false; // true = opening voor de SMA-antenne P3 van de LoRa-kit.
                     // Let op: als P3 gemonteerd is steekt hij 9,5 mm voorbij de
                     // printrand en gaat de behuizing niet dicht zonder die opening.

// ---- snap-fit tussen frontplaat en achterschaal ----------------------------
Z_JOINT  = -5.20;  // onderkant van de tong, diep genoeg om te kunnen veren
TONGUE   =  1.05;  // dikte van de tong
GROOVE   =  1.10;  // breedte van de gleuf in de schaal (0.05 speling = lichte pers)
BEAD     =  0.40;  // hoogte van de weerhaak
Z_BEAD   = -3.00;  // bovenkant van de weerhaak, dit vlak houdt de plaat vast
RAMP     =  1.60;  // aanlooplengte onder de weerhaak

// Zes losse klikpunten in plaats van een doorlopende rand, zodat je de plaat
// met iets plats weer los kan wrikken. [x, y, lengte, breedte van de zone]
bead_spots = [[-25, 29.7, 14, 9], [  0, 29.7, 14, 9], [ 38, 29.7, 11, 9],
              [-50,-29.7, 12, 9], [  0,-29.7, 14, 9], [ 38,-29.7, 11, 9]];
// Wrikgleufjes op de twee kopse kanten, over de naad heen.
pry = [[-63.9, 0], [63.9, 0]];

// hoogtes uit de STEP
PCB_T     = 1.59;  // PCB dikte
Z_BAT     = -12.59; // onderkant batterij

// ---- diepte van de badge onder de print -----------------------------------
// Dit is het enige getal dat je moet aanpassen na het opmeten. Het is het laagste
// punt van alles wat aan de print hangt: batterij, standoffs, cover-PCB, schroeven.
// -19.19 komt uit de STEP en is de onderkant van de standoffs M1..M4.
// Zit de cover-PCB er niet op, dan is -12.59 (onderkant batterij) genoeg en wordt
// de behuizing 6,6 mm dunner.
BADGE_BOTTOM = -19.19;

// Wat er aan de bovenkant uit de montagegaten steekt. Uit de STEP: 3,31 mm, diameter
// 6,2 mm. De frontplaat maakt daar plaatselijk ruimte voor.
STUD_TOP = 3.31;
STUD_D   = 6.20;
Z_DISP    = 4.50;  // bovenkant displayglas
Z_BTN     = 5.00;  // bovenkant drukknoppen
Z_JOY     = 7.00;  // bovenkant joystickknop

FLOOR_Z   = BADGE_BOTTOM - 1.00;   // binnenvloer achterschaal
BACK_Z    = FLOOR_Z - WALL;        // buitenvlak rug          = -15.99
RIM_Z     = 0.90;                  // bovenkant rand achterschaal
DECK_Z0   = 1.80;                  // onderkant hoofddek frontplaat
DECK_Z1   = DECK_Z0 + FWALL;       // bovenkant hoofddek      = 3.80
BEZ_Z0    = Z_DISP + 0.40;         // onderkant schermrand    = 4.90
BEZ_Z1    = BEZ_Z0 + 1.60;         // bovenkant schermrand    = 6.50

// ------------------------------------------------------- PCB omtrek uit STEP
outline = [[-55.5,27],[55.5,27],[56.2803,26.9229],[57.0305,26.6951],[57.7219,26.3254],
[58.328,25.828],[58.8254,25.2219],[59.1951,24.5305],[59.4229,23.7803],[59.5,23],
[59.5,-25],[59.4317,-25.5176],[59.2318,-25.9998],[58.914,-26.414],[58.4998,-26.7318],
[58.0176,-26.9317],[57.5,-27],[-57.5,-27],[-58.0176,-26.9317],[-58.4998,-26.7318],
[-58.914,-26.414],[-59.2318,-25.9998],[-59.4317,-25.5176],[-59.5,-25],[-59.5,23],
[-59.4229,23.7803],[-59.1951,24.5305],[-58.8254,25.2219],[-58.328,25.828],
[-57.7219,26.3254],[-57.0305,26.6951],[-56.2803,26.9229]];

module pcb_2d(off=0) offset(delta=off) polygon(outline);
module cavity_2d() pcb_2d(FIT);                 // binnenkant: PCB + speling
module outer_2d() offset(r=1.6) pcb_2d(FIT + WALL - 1.6);

// ------------------------------------------------------------- posities
// montagegaten diameter 2.5 mm, al aanwezig in de PCB
mounts = [[-37.5,-17.5],[-32.5,23.5],[37.5,18.5],[37.5,-17.5]];
// drukknoppen 6 mm
btns   = [[-13.5,-22.5],[13.5,-22.5],[45.75,-11.25],[54.75,-1],[45.75,9.25],[36.25,-1]];
// magneten
mags   = [[-47,18],[47,18],[-47,-18],[47,-18]];
// 5 x WS2812B, body 5.4 x 5.0 mm, hart op y = -16.2
leds   = [-20, -10, 0, 10, 20];
LED_D  = 4.40;   // diameter van het gaatje per LED

// Rond de montagegaten van de PCB steekt hardware uit: aan de onderkant een spacer,
// aan de bovenkant eventueel een schroefkop. De draagkolommen zijn daarom ringen.
COL_D    = 8.00;   // buitendiameter van de kolommen
SPACER_D = 5.20;   // vrije ruimte voor de spacer / moer / schroefkop
SPACER_H = 4.00;   // hoe diep die uitsparing gaat aan de onderkant

// ============================================================== ACHTERSCHAAL
module magnet_pocket() {
    translate([0,0,BACK_Z + SKIN])
        cylinder(h = MAG_H + MAG_FIT, d = MAG_D + MAG_FIT);
}

module backshell() {
    difference() {
        union() {
            // schaal met de holte er al uit, anders halen de volgende
            // aftrekkingen de kolommen en de magneetverdikkingen mee weg
            difference() {
                translate([0,0,BACK_Z]) linear_extrude(RIM_Z - BACK_Z) outer_2d();
                // binnenholte
                translate([0,0,FLOOR_Z]) linear_extrude(RIM_Z - FLOOR_Z + 1) cavity_2d();
                // gleuf voor de tong van de frontplaat
                translate([0,0,Z_JOINT]) linear_extrude(RIM_Z - Z_JOINT + 1)
                    offset(delta = GROOVE) cavity_2d();
                // groeven waar de zes weerhaken in terugveren
                translate([0,0,Z_BEAD - RAMP - 0.10]) linear_extrude(RAMP + 0.20)
                    intersection() {
                        offset(delta = GROOVE + BEAD + 0.15) cavity_2d();
                        bead_zone(3.0);
                    }
            }
            // Geen draagkolommen: de cover-PCB op de standoffs draagt de print al.
            // Alleen de verdikking rond de magneetnesten, binnen de holte gesneden.
            intersection() {
                for (p = mags) translate([p[0],p[1],FLOOR_Z])
                    cylinder(h = 2.0, d = 11.0);
                translate([0,0,FLOOR_Z - 1]) linear_extrude(30) cavity_2d();
            }
        }
        // magneetnesten, blind vanaf de binnenkant
        for (p = mags) translate([p[0],p[1],0]) magnet_pocket();
        // schroeven, alleen als BACK_SCREWS aan staat
        if (BACK_SCREWS) for (p = mounts) {
            translate([p[0],p[1],BACK_Z - 1]) cylinder(h = 40, d = 2.45);
            translate([p[0],p[1],BACK_Z - 0.01]) cylinder(h = 2.80, d = 4.20);
        }
        edge_ports();
        floor_ports();
        pry_notches();
    }
}

// openingen in de randen (maten uit de STEP + 0.6 mm speling)
module edge_ports() {
    // bovenrand
    translate([22.20, 20.0, -5.70]) cube([10.60, 14.0, 6.10]);   // USB-C
    translate([-44.35, 13.5, -7.40]) cube([8.10, 20.0, 6.90]);   // TRRS jack
    if (LORA_PORT)
        translate([43.90, 21.5, -6.10]) cube([9.40, 18.0, 8.20]);  // LoRa antenne
    // onderrand
    translate([14.90, -34.0, -4.30]) cube([13.30, 14.0, 4.10]);  // microSD
    // aan/uit schuifschakelaar SW4 (WS-SLSU 1P2T). De schuif steekt maar 0,88 mm
    // voorbij de printrand, dus hij blijft 1,8 mm verzonken liggen.
    translate([-34.50, -34.0, -4.20]) cube([10.50, 14.0, 3.70]);
    // trechter in de buitenwand zodat je er met een nagel bij kan
    translate([-37.00, -30.40, -5.40]) cube([15.50, 2.00, 6.10]);
}

// de rug is volledig dicht; alleen een opschrift, 0.6 mm diep
module floor_ports() {
    if (BACK_TEXT)
    translate([0, -21.5, BACK_Z - 0.01]) mirror([1,0,0]) linear_extrude(0.62)
        text("FRI3D 2026", size=5.4, halign="center", valign="center",
             font="Liberation Sans:style=Bold", spacing=1.1);
}

// ---- tong met weerhaak -----------------------------------------------------
module tongue_ring(extra = 0)
    difference() { offset(delta = TONGUE + extra) cavity_2d(); cavity_2d(); }

module bead_zone(margin = 0)
    for (s = bead_spots)
        translate([s[0], s[1]]) square([s[2] + 2*margin, s[3] + 2*margin], center = true);

// wrikgleufjes, over de naad heen, uit beide delen gehaald
module pry_notches()
    for (p = pry) translate([p[0], p[1], RIM_Z]) cube([4.6, 16.0, 3.2], center = true);

module tongue() {
    // rechte tong, rondom
    translate([0,0,Z_JOINT]) linear_extrude(DECK_Z0 - Z_JOINT) tongue_ring();
    // zes weerhaken, opgebouwd in laagjes van 0.2 mm: dun onderaan als aanloop,
    // vol bovenaan. Het vlakke bovenvlak is wat de plaat vasthoudt.
    steps = round(RAMP / 0.20);
    for (i = [1 : steps])
        translate([0, 0, Z_BEAD - RAMP + (i-1)*0.20])
            linear_extrude(0.21) intersection() {
                tongue_ring(BEAD * i / steps);
                bead_zone();
            }
}

// ================================================================ FRONTPLAAT
module frontplate() {
    difference() {
        union() {
            // hoofddek
            translate([0,0,DECK_Z0]) linear_extrude(FWALL) outer_2d();
            // buitenwand tot op de achterschaal
            translate([0,0,RIM_Z]) linear_extrude(DECK_Z0 - RIM_Z + 0.10)
                difference() { outer_2d(); offset(delta = 1.10) cavity_2d(); }
            // tong met weerhaak die in de achterschaal klikt
            tongue();
            // verhoogde schermrand
            translate([0,0,DECK_Z1 - 0.10])
                linear_extrude(BEZ_Z1 - DECK_Z1 + 0.10) bezel_2d();
            // Plaatselijke verdikking boven elk montagegat. De standoff steekt daar
            // 3,31 mm uit; het dek is maar 1,8 mm hoog, dus het dek gaat er lokaal
            // 0,9 mm omhoog zodat er nog 1,1 mm materiaal boven de uitsparing zit.
            for (p = mounts) translate([p[0],p[1],DECK_Z1 - 0.10])
                cylinder(h = 1.00, d1 = 10.0, d2 = 8.6);
        }
        // uitsparing voor het displaymodule zelf
        translate([-28.90, -13.90, DECK_Z0 - 0.10])
            cube([57.80, 44.00, BEZ_Z0 - DECK_Z0 + 0.10]);
        // schermvenster
        translate([-26.9, -11.8, -1]) linear_extrude(40)
            offset(r=1.5) offset(delta=-1.5) square([53.8, 37.2]);
        // joystick
        translate([-42.78, -0.15, -1]) linear_extrude(40)
            offset(r=2.5) square([16.0, 16.0], center=true);
        // drukknoppen
        for (p = btns) translate([p[0],p[1],-1]) cylinder(h=40, d=7.4);
        // een gaatje per LED in plaats van een doorlopende sleuf
        for (x = leds) translate([x, -16.2, -1]) cylinder(h = 40, d = LED_D);
        // status-LED D15
        translate([-33.27, 17.1, -1]) cylinder(h=40, d=7.4);
        // uitsparing voor de standoff die boven de print uitsteekt
        for (p = mounts) translate([p[0],p[1],-0.10])
            cylinder(h = STUD_TOP + 0.30 + 0.10, d = STUD_D + 0.80);
        // blinde voorboring, alleen als je toch schroeven wil
        if (BACK_SCREWS) for (p = mounts) translate([p[0],p[1],-0.10])
            cylinder(h = DECK_Z1 - 0.20 + 0.10, d = 1.60);
        // wrikgleufjes op de kopse kanten om de plaat er weer af te krijgen
        pry_notches();
        // opschriften in de plaat, 0.5 mm diep, standaard uit
        if (PORT_LABELS) {
            translate([-44.0, 23.5, DECK_Z1 - 0.50]) linear_extrude(0.61)
                text("AUDIO", size=2.9, halign="center", valign="center",
                     font="Liberation Sans:style=Bold", spacing=1.15);
            if (LORA_PORT)
                translate([46.0, 23.5, DECK_Z1 - 0.50]) linear_extrude(0.61)
                    text("LoRa", size=2.9, halign="center", valign="center",
                         font="Liberation Sans:style=Bold", spacing=1.15);
        }
        // randopeningen ook in de frontplaat
        edge_ports();
    }
}

// vlak van de verhoogde schermrand: rond het display, doorlopend tot de bovenrand
module bezel_2d() {
    intersection() {
        outer_2d();
        offset(r=2.0) offset(delta=-2.0)
            translate([-31.0, -13.8]) square([62.0, 44.0]);
    }
}

// ====================================================================== DOCK
// De badge klikt magnetisch in een ondiepe bak die 41 graden achterover staat.
module dock() {
    FOOT_Y0 = -44; FOOT_W = 134;
    TRAY   = 4.0;   // dikte achterplaat van de bak
    RIM    = 5.0;   // hoogte opstaande rand
    difference() {
        union() {
            // wig: romp tussen de voet en de achterplaat van de bak
            hull() {
                translate([-FOOT_W/2, FOOT_Y0, 0]) cube([FOOT_W, 9, 3]);
                dock_place() translate([0,0,BACK_Z-TRAY])
                    linear_extrude(TRAY) offset(delta=3.2) outer_2d();
            }
            // opstaande rand rond de badge, bovenrand blijft vrij
            dock_place() translate([0,0,BACK_Z]) linear_extrude(RIM)
                intersection() {
                    difference() { offset(delta=3.2) outer_2d(); offset(delta=0.45) outer_2d(); }
                    translate([-70,-40]) square([140, 58]);
                }
        }
        // holte voor de badge
        dock_place() translate([0,0,BACK_Z-0.01]) linear_extrude(80)
            offset(delta=0.45) outer_2d();
        // magneetnesten in de bak, open naar de badge toe
        dock_place() for (p = mags) translate([p[0],p[1],BACK_Z-MAG_H-MAG_FIT-0.10])
            cylinder(h = MAG_H + MAG_FIT + 0.20, d = MAG_D + MAG_FIT);
        // uitsparing in de onderrand voor de microSD
        dock_place() translate([13.4,-40,BACK_Z-1]) cube([16.4, 16, RIM+2]);
        // materiaal besparen aan de onderkant
        translate([-FOOT_W/2+6, FOOT_Y0+6, -1]) hull() {
            cube([FOOT_W-12, 6, 1]);
            dock_place() translate([0,0,BACK_Z-TRAY-6]) linear_extrude(1)
                offset(delta=-4) outer_2d();
        }
        // vlakke onderkant
        translate([-200,-200,-40]) cube([400,400,40]);
    }
}

module dock_place() translate([0, -14, 36]) rotate([DOCK_ANG, 0, 0]) children();

// =========================================================== badge (referentie)
module badge() {
    color("#3b1f6e") translate([0,0,-PCB_T]) linear_extrude(PCB_T) pcb_2d();
    color("#101018") translate([-28.1,-13,3]) cube([56.2,39.6,1.5]);
    color("#1b6ea8") translate([-26.9,-11.8,4.5]) cube([53.8,37.2,0.2]);
    color("#222") translate([-42.78,-0.15,0]) { cube([18,18,3.5],center=true);
        cylinder(h=7,r=4.2); }
    for (p = btns) color("#c8412f") translate([p[0],p[1],0]) cylinder(h=5,r=3);
    for (x = leds) color("#eee") translate([x-2.7,-18.7,0]) cube([5.4,5.0,1.6]);
    color("#8d8d94") translate([-26.1,-15.8,-12.59]) cube([60,40,7]);
    color("#c9c9c9") translate([-9,1,-4.79]) cube([18,25.5,3.2]);
    color("#9a9aa0") translate([23,20.45,-4.85]) cube([8.94,7.9,4.21]);
    color("#2b2b2b") translate([-43.55,14.5,-6.59]) cube([6.5,14,5]);
    color("#9a9aa0") translate([44.84,23.17,-5.27]) cube([7.32,13.33,6.35]);
    color("#9a9aa0") translate([15.69,-29.65,-3.53]) cube([11.42,15,1.06]);
    color("#1a1a1a") translate([-7.62,-25.1,-5.29]) cube([15.24,7.2,3.7]);
    color("#d0a000") translate([44.99,-8.46,-5.39]) cube([5.1,4.5,3.8]);
    color("#8d8d94") translate([-6,-16.2,-4.64]) cube([12,12,3.05]);
}

module magnets(inshell=true) {
    for (p = mags) color("#5a5a60")
        translate([p[0],p[1], BACK_Z + SKIN]) cylinder(h=MAG_H, d=MAG_D);
}

// ================================================================= uitvoeren
if (part == "backshell")  backshell();
if (part == "frontplate") frontplate();
if (part == "dock")       dock();
if (part == "assembly") {
    color("#4a5bd0", 0.92) backshell();
    color("#8f9bef", 0.55) frontplate();
    magnets();
    badge();
}
if (part == "docked") {
    color("#b96ad9", 0.95) dock();
    dock_place() { color("#4a5bd0",0.92) backshell(); color("#8f9bef",0.6) frontplate(); badge(); }
}

// ---------------------------------------------- botsingscontrole (verificatie)
if (part == "check")
    intersection() { union() { backshell(); frontplate(); } badge_solids(); }

module badge_solids() {
    translate([0,0,-PCB_T]) linear_extrude(PCB_T) pcb_2d();          // PCB
    translate([-28.1,-13,3]) cube([56.2,39.6,1.5]);                  // display
    translate([-42.78,-0.15,0]) { cube([18,18,3.5],center=true); cylinder(h=7,r=4.2); }
    for (p = btns) translate([p[0],p[1],0]) cylinder(h=5,r=3);
    for (x = leds) translate([x-2.7,-18.7,0]) cube([5.4,5.0,1.6]);
    translate([-26.1,-15.8,-12.59]) cube([60,40,7]);                 // batterij
    translate([-9,1,-4.79]) cube([18,25.5,3.2]);                     // ESP32
    translate([23,20.45,-4.85]) cube([8.94,7.9,4.21]);               // USB-C
    translate([-43.55,14.5,-6.59]) cube([6.5,14,5]);                 // TRRS
    // De SMA-connector P3 steekt 9,5 mm voorbij de printrand. Alleen meenemen als
    // de opening open staat; anders is de aanname dat P3 niet gemonteerd is.
    if (LORA_PORT) translate([44.84,23.17,-5.27]) cube([7.32,13.33,6.35]);
    translate([12.43,-24.35,-3.54]) cube([16,15.25,2.45]);           // microSD
    translate([15.69,-29.65,-3.53]) cube([11.42,15,1.06]);           // SD kaart
    translate([-7.62,-25.1,-5.29]) cube([15.24,7.2,3.7]);            // P10
    translate([44.99,-8.46,-5.39]) cube([5.1,4.5,3.8]);              // SW11 reset
    translate([-33.35,-26.35,-3.01]) cube([6.70,2.70,1.90]);        // SW4 aan/uit
    translate([-32.71,-27.88,-2.81]) cube([6.92,3.85,1.10]);        // SW4 schuif + 1.5 mm slag
    translate([-58.60,9.00,-4.54]) cube([4.25,6.00,2.90]);          // P2
    // standoffs M1..M4 met de cover-PCB eronder, uit de STEP: diameter 6,2 mm
    // van z = -19,19 tot +3,31
    for (p = mounts) translate([p[0],p[1],BADGE_BOTTOM])
        cylinder(h = STUD_TOP - BADGE_BOTTOM, d = STUD_D);
    translate([-6,-16.2,-4.64]) cube([12,12,3.05]);                  // buzzer
    translate([44.94,3.05,-4.54]) cube([11.6,11,2.95]);              // LoRa module
    translate([-30.98,-5.65,-5.29]) cube([6,6.5,3.76]);              // batterijconnector
    translate([-35.77,15,0]) cube([5,4.2,4.4]);                      // D15
    translate([20.89,-0.06,-2.48]) cube([4.2,7.9,0.9]);              // FPC connector
}

if (part == "check2") intersection() { backshell(); frontplate(); }
if (part == "check3") intersection() { dock(); dock_place() union(){ backshell(); frontplate(); badge_solids(); } }

if (part == "exploded") {
    translate([0,0,30]) { color("#8f9bef") frontplate(); }
    translate([0,0,15]) badge();
    color("#4a5bd0") backshell();
    magnets();
}
if (part == "plated") {
    // zoals ze op de printplaat liggen
    translate([0,70,0]) rotate([180,0,0]) color("#8f9bef") frontplate();
    color("#4a5bd0") backshell();
    translate([0,-95,0]) rotate([-DOCK_ANG,0,0]) color("#b96ad9") dock();
}

// dwarsdoorsnede door de snap-fit, om te controleren
if (part == "section")
    difference() {
        union() { color("#4a5bd0") backshell(); color("#8f9bef") frontplate(); }
        translate([-70, -40, -20]) cube([140, 40, 40]);
        translate([-70, -40, -20]) cube([56, 80, 40]);
    }
