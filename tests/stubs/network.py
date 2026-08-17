"""Stub of MicroPython's network module.

Only what the Berichtjes service asks: is the station interface up and
associated. Flip STATE to test what the badge does out of range.
"""

STA_IF = 0
AP_IF = 1

STATE = {"active": True, "connected": True, "rssi": -54, "mac": None}


class WLAN:
    def __init__(self, interface=STA_IF):
        self.interface = interface

    def active(self, *args):
        if args:
            STATE["active"] = bool(args[0])
        return STATE["active"]

    def isconnected(self):
        return STATE["connected"]

    def status(self, field=None):
        """Signal strength, or a raise for a field this stub does not know.

        The real one raises for an unsupported field rather than returning
        None, and the service has to survive that.
        """
        if field == "rssi":
            if STATE["rssi"] is None:
                raise OSError("wifi not started")
            return STATE["rssi"]
        raise ValueError("unknown status field: %s" % field)

    def config(self, field):
        if field == "mac":
            if STATE["mac"] is None:
                raise OSError("no mac")
            return STATE["mac"]
        raise ValueError("unknown config field: %s" % field)
