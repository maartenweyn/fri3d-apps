// ============================================================================
//  Fri3d Camp 2026 badge - case + magnetic desk dock
//  ------------------------------------------------------------------------
//  Geometry measured from Fri3D_Badge_2026_02.step (revision 02),
//  github.com/Fri3dCamp/badge_2026_hw
//
//  Frame: origin = centre of the PCB, Z = 0 on the top face of the PCB.
//  Anything with positive Z is on the user side.
//
//  Parts:
//    part = "backshell"   back shell with the magnet pockets
//    part = "frontplate"  front plate with the screen bezel
//    part = "dock"        desk dock, badge at 65 degrees
//    part = "assembly"    everything with the badge in it, to look at only
//
//  Back and front are fully closed. No screws: the front plate clips on at six
//  separate points along the long edges. Each short end has a pry slot so a
//  spudger gets it off again.
//
//  Print: Prusa MK4S, PLA, 0.4 mm nozzle, 0.2 mm layers, no supports.
//  Magnets: 8 x neodymium disc 6 x 3 mm (4 in the shell, 4 in the dock).
// ============================================================================

part = "assembly";
$fn = 64;

// ---------------------------------------------------------------- parameters
FIT      = 0.30;   // clearance around the PCB (FDM, 0.4 mm nozzle)
WALL     = 2.40;   // wall thickness, back shell
FWALL    = 2.00;   // wall thickness, front plate
SKIN     = 0.80;   // material between magnet and outer face
MAG_D    = 6.00;   // magnet diameter
MAG_H    = 3.00;   // magnet thickness
MAG_FIT  = 0.20;   // magnet pocket clearance (glue them in)
MAG_BOSS_D = 11.00; // boss around the magnet pocket, inside the shell
MAG_BOSS_H = 2.00;  // height of that boss above the inner floor
DOCK_ANG = 65;     // angle of the badge relative to the desk
BACK_SCREWS = false; // true = add four M2 from the back; false = snap fit only
PORT_LABELS = false; // true = emboss AUDIO and LoRa into the front plate
BACK_TEXT   = false; // true = emboss FRI3D 2026 into the back, 0.6 mm deep
LORA_PORT   = false; // true = opening for the SMA antenna P3 of the LoRa kit.
                     // Careful: with P3 fitted it sticks out 9.5 mm past the board
                     // edge and the case will not close without that opening.

// ---- snap fit between front plate and back shell ---------------------------
Z_JOINT  = -5.20;  // bottom of the tongue, deep enough to flex
TONGUE   =  1.05;  // tongue thickness
GROOVE   =  1.10;  // groove width in the shell (0.05 clearance = light press)
BEAD     =  0.40;  // height of the barb
Z_BEAD   = -3.00;  // top of the barb; this face is what holds the plate
RAMP     =  1.60;  // lead-in length below the barb

// Six separate clip points instead of a continuous rim, so the plate can be
// pried off with something flat. [x, y, length, width of the zone]
bead_spots = [[-25, 29.7, 14, 9], [  0, 29.7, 14, 9], [ 38, 29.7, 11, 9],
              [-50,-29.7, 12, 9], [  0,-29.7, 14, 9], [ 38,-29.7, 11, 9]];
// Pry slots on the two short ends, across the seam.
pry = [[-63.9, 0], [63.9, 0]];

// heights from the STEP
PCB_T     = 1.59;  // PCB thickness
Z_BAT     = -12.59; // bottom of the battery

// ---- how deep the badge reaches below the board ----------------------------
// The badge's own cover PCB and standoffs come off; the case carries the board
// itself. What is left underneath is the battery and the components, and the
// lowest of those is the battery at -12.59 from the top face of the board. The
// floor sits 1 mm below that, so there is 12.0 mm of clear space under the board.
// Measured a different stack? Change this one number and the inner floor, the
// wall and the dock all follow.
BADGE_BOTTOM = -12.59;

// ---- the four support columns ----------------------------------------------
// They stand where the badge's own spacers used to sit, on the four mounting
// holes. 5.0 mm is the most they can be: any wider and they touch components.
// Each carries a pin that drops into the 2.5 mm hole and locates the board.
COL_D  = 5.00;   // column diameter, do not go above this
PIN_D  = 2.30;   // pin into the 2.5 mm mounting hole
PIN_UP = 0.60;   // how far the pin stands above the top face of the board
Z_DISP    = 4.50;  // top of the display glass
Z_BTN     = 5.00;  // top of the push buttons
Z_JOY     = 7.00;  // top of the joystick cap

FLOOR_Z   = BADGE_BOTTOM - 1.00;   // inner floor of the back shell
BACK_Z    = FLOOR_Z - WALL;        // outer face of the back
RIM_Z     = 0.90;                  // top of the back shell rim
DECK_Z0   = 1.80;                  // underside of the main deck
DECK_Z1   = DECK_Z0 + FWALL;       // top of the main deck
BEZ_Z0    = Z_DISP + 0.40;         // underside of the screen bezel
BEZ_Z1    = BEZ_Z0 + 1.60;         // top of the screen bezel

// -------------------------------------------------------- PCB outline, STEP
outline = [[-55.5,27],[55.5,27],[56.2803,26.9229],[57.0305,26.6951],[57.7219,26.3254],
[58.328,25.828],[58.8254,25.2219],[59.1951,24.5305],[59.4229,23.7803],[59.5,23],
[59.5,-25],[59.4317,-25.5176],[59.2318,-25.9998],[58.914,-26.414],[58.4998,-26.7318],
[58.0176,-26.9317],[57.5,-27],[-57.5,-27],[-58.0176,-26.9317],[-58.4998,-26.7318],
[-58.914,-26.414],[-59.2318,-25.9998],[-59.4317,-25.5176],[-59.5,-25],[-59.5,23],
[-59.4229,23.7803],[-59.1951,24.5305],[-58.8254,25.2219],[-58.328,25.828],
[-57.7219,26.3254],[-57.0305,26.6951],[-56.2803,26.9229]];

module pcb_2d(off=0) offset(delta=off) polygon(outline);
module cavity_2d() pcb_2d(FIT);                 // inside: PCB + clearance
module outer_2d() offset(r=1.6) pcb_2d(FIT + WALL - 1.6);

// ------------------------------------------------------------- positions
// mounting holes, 2.5 mm diameter, already in the PCB
mounts = [[-37.5,-17.5],[-32.5,23.5],[37.5,18.5],[37.5,-17.5]];
// 6 mm push buttons, Alps SKPMAM. Measured from the STEP by slicing the solid:
// the body is 5.94 x 5.90 mm and runs up to z = 3.50, then a cap of 4.97 x 4.87
// tapers to 4.50 at z = 5.00. The cap fits through the round hole, the body does
// not: its corners reach 4.19 mm from the centre against a hole radius of 3.70.
// So the deck needs a rectangular relief cut up from underneath.
btns   = [[-13.5,-22.5],[13.5,-22.5],[45.75,-11.25],[54.75,-1],[45.75,9.25],[36.25,-1]];
BTN_D        = 7.40;   // round hole, the only thing visible from outside
BTN_BODY     = 7.00;   // rectangular relief for the switch body
BTN_BODY_R   = 1.00;   // corner radius of that relief
BTN_BODY_TOP = 3.60;   // top of the relief, 0.10 above the body
// What is left above the relief is DECK_Z1 - BTN_BODY_TOP = 0.20 mm, and only in
// the four corners: everything else there is inside the round hole anyway. If
// that single layer tears, either raise FWALL or set BTN_BODY_TOP = DECK_Z1 and
// let the relief break through.
// magnets
mags   = [[-47,18],[47,18],[-47,-18],[47,-18]];
// 5 x WS2812B, body 5.4 x 5.0 mm, centred on y = -16.2
leds   = [-20, -10, 0, 10, 20];
LED_D  = 4.40;   // diameter of the hole per LED

// A column that ends flush with the underside of the board, with a pin on top
// that goes through the mounting hole and sticks out PIN_UP. The tip is
// chamfered so the board drops onto it without fishing for the hole.
module support_column() {
    h = -PCB_T - FLOOR_Z;                 // up to the underside of the board
    cylinder(h = h, d = COL_D);
    translate([0,0,h]) {
        cylinder(h = PCB_T + PIN_UP - 0.40, d = PIN_D);
        translate([0,0,PCB_T + PIN_UP - 0.40])
            cylinder(h = 0.40, d1 = PIN_D, d2 = PIN_D - 0.80);
    }
}

// ================================================================ BACK SHELL
// The pocket has to break through the top of the boss, otherwise it is a sealed
// void and the magnet can never go in. Boss top is MAG_BOSS_H above the floor;
// the pocket is cut 0.2 mm past it.
module magnet_pocket() {
    top = FLOOR_Z + MAG_BOSS_H + 0.20;
    translate([0,0,BACK_Z + SKIN])
        cylinder(h = max(MAG_H + MAG_FIT, top - (BACK_Z + SKIN)), d = MAG_D + MAG_FIT);
}

module backshell() {
    difference() {
        union() {
            // shell with the cavity already carved out, otherwise the later
            // subtractions take the columns and magnet bosses with them
            difference() {
                translate([0,0,BACK_Z]) linear_extrude(RIM_Z - BACK_Z) outer_2d();
                // inner cavity
                translate([0,0,FLOOR_Z]) linear_extrude(RIM_Z - FLOOR_Z + 1) cavity_2d();
                // groove for the tongue of the front plate
                translate([0,0,Z_JOINT]) linear_extrude(RIM_Z - Z_JOINT + 1)
                    offset(delta = GROOVE) cavity_2d();
                // grooves the six barbs spring back into
                translate([0,0,Z_BEAD - RAMP - 0.10]) linear_extrude(RAMP + 0.20)
                    intersection() {
                        offset(delta = GROOVE + BEAD + 0.15) cavity_2d();
                        bead_zone(3.0);
                    }
            }
            // Support columns and magnet bosses, clipped to the cavity so they
            // stay out of the groove that takes the tongue.
            intersection() {
                union() {
                    for (p = mounts) translate([p[0],p[1],FLOOR_Z]) support_column();
                    for (p = mags) translate([p[0],p[1],FLOOR_Z])
                        cylinder(h = MAG_BOSS_H, d = MAG_BOSS_D);
                }
                translate([0,0,FLOOR_Z - 1]) linear_extrude(30) cavity_2d();
            }
        }
        // magnet pockets, blind from the inside
        for (p = mags) translate([p[0],p[1],0]) magnet_pocket();
        // screws, only when BACK_SCREWS is on
        if (BACK_SCREWS) for (p = mounts) {
            translate([p[0],p[1],BACK_Z - 1]) cylinder(h = 40, d = 2.45);
            translate([p[0],p[1],BACK_Z - 0.01]) cylinder(h = 2.80, d = 4.20);
        }
        edge_ports();
        floor_ports();
        pry_notches();
    }
}

// openings in the edges (sizes from the STEP + 0.6 mm clearance)
module edge_ports() {
    // top edge
    translate([22.20, 20.0, -5.70]) cube([10.60, 14.0, 6.10]);   // USB-C
    translate([-44.35, 13.5, -7.40]) cube([8.10, 20.0, 6.90]);   // TRRS jack
    if (LORA_PORT)
        translate([43.90, 21.5, -6.10]) cube([9.40, 18.0, 8.20]);  // LoRa antenna
    // bottom edge
    translate([14.90, -34.0, -4.30]) cube([13.30, 14.0, 4.10]);  // microSD
    // power slide switch SW4 (WS-SLSU 1P2T). The slider only reaches 0.88 mm
    // past the board edge, so it sits 1.8 mm recessed.
    translate([-34.50, -34.0, -4.20]) cube([10.50, 14.0, 3.70]);
    // funnel in the outer wall so a fingernail can reach the slider
    translate([-37.00, -30.40, -5.40]) cube([15.50, 2.00, 6.10]);
}

// the back is fully closed; only a marking, 0.6 mm deep
module floor_ports() {
    if (BACK_TEXT)
    translate([0, -21.5, BACK_Z - 0.01]) mirror([1,0,0]) linear_extrude(0.62)
        text("FRI3D 2026", size=5.4, halign="center", valign="center",
             font="Liberation Sans:style=Bold", spacing=1.1);
}

// ---- tongue with barbs -----------------------------------------------------
module tongue_ring(extra = 0)
    difference() { offset(delta = TONGUE + extra) cavity_2d(); cavity_2d(); }

module bead_zone(margin = 0)
    for (s = bead_spots)
        translate([s[0], s[1]]) square([s[2] + 2*margin, s[3] + 2*margin], center = true);

// pry slots, across the seam, subtracted from both parts
module pry_notches()
    for (p = pry) translate([p[0], p[1], RIM_Z]) cube([4.6, 16.0, 3.2], center = true);

module tongue() {
    // plain tongue, all the way round
    translate([0,0,Z_JOINT]) linear_extrude(DECK_Z0 - Z_JOINT) tongue_ring();
    // six barbs, built in 0.2 mm slices: thin at the bottom as a lead-in, full
    // at the top. That flat top face is what holds the plate.
    steps = round(RAMP / 0.20);
    for (i = [1 : steps])
        translate([0, 0, Z_BEAD - RAMP + (i-1)*0.20])
            linear_extrude(0.21) intersection() {
                tongue_ring(BEAD * i / steps);
                bead_zone();
            }
}

// ================================================================ FRONT PLATE
module frontplate() {
    difference() {
        union() {
            // main deck
            translate([0,0,DECK_Z0]) linear_extrude(FWALL) outer_2d();
            // outer wall down onto the back shell
            translate([0,0,RIM_Z]) linear_extrude(DECK_Z0 - RIM_Z + 0.10)
                difference() { outer_2d(); offset(delta = 1.10) cavity_2d(); }
            // tongue with barbs that clips into the back shell
            tongue();
            // raised screen bezel
            translate([0,0,DECK_Z1 - 0.10])
                linear_extrude(BEZ_Z1 - DECK_Z1 + 0.10) bezel_2d();
            // Columns that press the board down onto the ones in the shell.
            // Nothing sticks out above the board any more, so the deck stays flat.
            for (p = mounts) translate([p[0],p[1],0])
                cylinder(h = DECK_Z0, d = COL_D);
        }
        // Clearance for the display module itself. STEP: 56.20 x 39.60, from
        // x -28.10 to 28.10 and y -13.00 to 26.60, z 3.00 to 4.50. Kept tight to
        // the glass, 0.60 mm all round, so the top edge of the plate stays shut.
        // It used to run to y = 30.10, straight through the top wall, which left
        // a 57.80 mm slot along the back edge with only the bezel over it.
        translate([-28.70, -13.60, DECK_Z0 - 0.10])
            cube([57.40, 41.00, BEZ_Z0 - DECK_Z0 + 0.10]);
        // screen window
        translate([-26.9, -11.8, -1]) linear_extrude(40)
            offset(r=1.5) offset(delta=-1.5) square([53.8, 37.2]);
        // Joystick P7. The block is 18.0 x 18.0 and runs up to z = 5.60, with a
        // 2 mm stick above it. The opening was 21.0 x 21.0 with 2.5 mm corners,
        // which is 1.5 mm of air per side; 19.0 x 19.0 leaves 0.50. The corner
        // radius has to come down with it: at r = 2.5 the arc cuts across the
        // square corners of the block, which the interference check now catches.
        translate([-42.78, -0.15, -1]) linear_extrude(40)
            offset(r=0.8) square([17.4, 17.4], center=true);
        // push buttons: round hole for the cap...
        for (p = btns) translate([p[0],p[1],-1]) cylinder(h=40, d=BTN_D);
        // ...and a blind rectangular relief for the square body underneath it
        for (p = btns) translate([p[0],p[1],DECK_Z0 - 1.0])
            linear_extrude(BTN_BODY_TOP - DECK_Z0 + 1.0)
                offset(r=BTN_BODY_R)
                    square([BTN_BODY - 2*BTN_BODY_R, BTN_BODY - 2*BTN_BODY_R],
                           center=true);
        // one hole per LED instead of a continuous slot
        for (x = leds) translate([x, -16.2, -1]) cylinder(h = 40, d = LED_D);
        // status LED D15
        translate([-33.27, 17.1, -1]) cylinder(h=40, d=7.4);
        // blind hole in each column for the pin that pokes through the board
        for (p = mounts) translate([p[0],p[1],-0.10])
            cylinder(h = PIN_UP + 0.50, d = PIN_D + 0.40);
        // blind pilot hole, only if you do want screws
        if (BACK_SCREWS) for (p = mounts) translate([p[0],p[1],-0.10])
            cylinder(h = DECK_Z1 - 0.20 + 0.10, d = 1.60);
        // pry slots on the short ends to get the plate off again
        pry_notches();
        // markings in the plate, 0.5 mm deep, off by default
        if (PORT_LABELS) {
            translate([-44.0, 23.5, DECK_Z1 - 0.50]) linear_extrude(0.61)
                text("AUDIO", size=2.9, halign="center", valign="center",
                     font="Liberation Sans:style=Bold", spacing=1.15);
            if (LORA_PORT)
                translate([46.0, 23.5, DECK_Z1 - 0.50]) linear_extrude(0.61)
                    text("LoRa", size=2.9, halign="center", valign="center",
                         font="Liberation Sans:style=Bold", spacing=1.15);
        }
        // edge openings in the front plate too
        edge_ports();
    }
}

// footprint of the raised bezel: around the display, running to the top edge
module bezel_2d() {
    intersection() {
        outer_2d();
        offset(r=2.0) offset(delta=-2.0)
            translate([-31.0, -13.8]) square([62.0, 44.0]);
    }
}

// ====================================================================== DOCK
// The badge clips magnetically into a shallow tray leaning back.
module dock() {
    FOOT_Y0 = -44; FOOT_W = 134;
    TRAY   = 4.0;   // thickness of the tray back plate
    RIM    = 5.0;   // height of the standing rim
    difference() {
        union() {
            // wedge: body between the foot and the tray back plate
            hull() {
                translate([-FOOT_W/2, FOOT_Y0, 0]) cube([FOOT_W, 9, 3]);
                dock_place() translate([0,0,BACK_Z-TRAY])
                    linear_extrude(TRAY) offset(delta=3.2) outer_2d();
            }
            // rim around the badge; the top edge stays open
            dock_place() translate([0,0,BACK_Z]) linear_extrude(RIM)
                intersection() {
                    difference() { offset(delta=3.2) outer_2d(); offset(delta=0.45) outer_2d(); }
                    translate([-70,-40]) square([140, 58]);
                }
        }
        // pocket for the badge
        dock_place() translate([0,0,BACK_Z-0.01]) linear_extrude(80)
            offset(delta=0.45) outer_2d();
        // magnet pockets in the tray, open towards the badge
        dock_place() for (p = mags) translate([p[0],p[1],BACK_Z-MAG_H-MAG_FIT-0.10])
            cylinder(h = MAG_H + MAG_FIT + 0.20, d = MAG_D + MAG_FIT);
        // notch in the bottom rim for the microSD
        dock_place() translate([13.4,-40,BACK_Z-1]) cube([16.4, 16, RIM+2]);
        // save material underneath
        translate([-FOOT_W/2+6, FOOT_Y0+6, -1]) hull() {
            cube([FOOT_W-12, 6, 1]);
            dock_place() translate([0,0,BACK_Z-TRAY-6]) linear_extrude(1)
                offset(delta=-4) outer_2d();
        }
        // flat bottom
        translate([-200,-200,-40]) cube([400,400,40]);
    }
}

module dock_place() translate([0, -14, 36]) rotate([DOCK_ANG, 0, 0]) children();

// ============================================================ badge (reference)
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

// =================================================================== render
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

// ------------------------------------------------ interference check (verify)
if (part == "check")
    intersection() { union() { backshell(); frontplate(); } badge_solids(); }

module badge_solids() {
    // PCB, with its four 2.5 mm mounting holes, because the pins pass through them
    difference() {
        translate([0,0,-PCB_T]) linear_extrude(PCB_T) pcb_2d();
        for (p = mounts) translate([p[0],p[1],-PCB_T-1]) cylinder(h = PCB_T+2, d = 2.50);
    }
    translate([-28.1,-13,3]) cube([56.2,39.6,1.5]);                  // display
    // Joystick P7 as it really is: a block of 18 x 18 from z = 0.10 to 5.60 with
    // a 2 mm stick on top. It used to be modelled as an 18 x 18 slab that stopped
    // at z = 1.75 with a 8.4 mm cylinder above it, which is why the check never
    // noticed that the deck was cutting into the block.
    translate([-51.78,-9.15,0.10]) cube([18.00, 18.00, 5.50]);
    translate([-43.78,-1.15,5.60]) cube([ 2.00,  2.00, 1.40]);
    // Push buttons as they really are: a square body, not a 6 mm cylinder. The
    // cylinder is what hid the collision that broke a switch on the first print.
    for (p = btns) translate([p[0],p[1],0]) {
        translate([0,0,1.75]) cube([5.94, 5.94, 3.50], center=true);  // body
        translate([0,0,4.25]) cube([4.97, 4.97, 1.50], center=true);  // cap
    }
    for (x = leds) translate([x-2.7,-18.7,0]) cube([5.4,5.0,1.6]);
    translate([-26.1,-15.8,-12.59]) cube([60,40,7]);                 // battery
    translate([-9,1,-4.79]) cube([18,25.5,3.2]);                     // ESP32
    translate([23,20.45,-4.85]) cube([8.94,7.9,4.21]);               // USB-C
    translate([-43.55,14.5,-6.59]) cube([6.5,14,5]);                 // TRRS
    // The SMA connector P3 sticks out 9.5 mm past the board edge. Only include it
    // when the opening is open; otherwise the assumption is P3 is not fitted.
    if (LORA_PORT) translate([44.84,23.17,-5.27]) cube([7.32,13.33,6.35]);
    translate([12.43,-24.35,-3.54]) cube([16,15.25,2.45]);           // microSD
    translate([15.69,-29.65,-3.53]) cube([11.42,15,1.06]);           // SD card
    translate([-7.62,-25.1,-5.29]) cube([15.24,7.2,3.7]);            // P10
    translate([44.99,-8.46,-5.39]) cube([5.1,4.5,3.8]);              // SW11, reset
    translate([-33.35,-26.35,-3.01]) cube([6.70,2.70,1.90]);        // SW4, power
    translate([-32.71,-27.88,-2.81]) cube([6.92,3.85,1.10]);        // SW4 slider + 1.5 mm travel
    translate([-58.60,9.00,-4.54]) cube([4.25,6.00,2.90]);          // P2
    // The badge's own standoffs and cover PCB are off; the case carries the board.
    // What has to stay clear is the 2.5 mm hole the pin goes through.
    translate([-6,-16.2,-4.64]) cube([12,12,3.05]);                  // buzzer
    translate([44.94,3.05,-4.54]) cube([11.6,11,2.95]);              // LoRa module
    translate([-30.98,-5.65,-5.29]) cube([6,6.5,3.76]);              // battery connector
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
    // laid out as they sit on the bed
    translate([0,70,0]) rotate([180,0,0]) color("#8f9bef") frontplate();
    color("#4a5bd0") backshell();
    translate([0,-95,0]) rotate([-DOCK_ANG,0,0]) color("#b96ad9") dock();
}

// cross section through the snap fit, to check it
if (part == "section")
    difference() {
        union() { color("#4a5bd0") backshell(); color("#8f9bef") frontplate(); }
        translate([-70, -40, -20]) cube([140, 40, 40]);
        translate([-70, -40, -20]) cube([56, 80, 40]);
    }
