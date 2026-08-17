"""Stub of MicroPython's network module.

Only what the Berichtjes service asks: is the station interface up and
associated. Flip STATE to test what the badge does out of range.
"""

STA_IF = 0
AP_IF = 1

STATE = {"active": True, "connected": True}


class WLAN:
    def __init__(self, interface=STA_IF):
        self.interface = interface

    def active(self, *args):
        if args:
            STATE["active"] = bool(args[0])
        return STATE["active"]

    def isconnected(self):
        return STATE["connected"]
