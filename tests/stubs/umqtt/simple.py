"""Fake umqtt.simple, close enough to catch the mistakes that matter.

Deliberate quirks copied from the real thing:

- connect(), subscribe(), publish() and ping() all raise OSError once the
  broker is marked down, which is how a dropped WiFi link actually shows up.
- payloads are bytes, not str. The service must decode.
- check_msg() delivers at most one queued message per call.
"""


class MQTTException(Exception):
    pass


class BROKER:
    """Test-controlled broker state."""

    up = True
    accept_auth = True
    inbox = []          # messages waiting to be delivered to the client
    published = []      # (topic, payload) the client sent
    subscriptions = []
    attempts = 0        # every connect() call, successful or not
    connects = 0        # only the ones that got through
    pings = 0
    supports_socket_timeout = True

    @classmethod
    def reset(cls):
        cls.up = True
        cls.accept_auth = True
        cls.inbox = []
        cls.published = []
        cls.subscriptions = []
        cls.attempts = 0
        cls.connects = 0
        cls.pings = 0
        cls.supports_socket_timeout = True

    @classmethod
    def deliver(cls, topic, text):
        payload = text.encode("utf-8") if isinstance(text, str) else text
        cls.inbox.append((topic.encode("utf-8"), payload))


class MQTTClient:
    def __init__(self, client_id, server, port=0, user=None, password=None,
                 keepalive=0, ssl=None, **kwargs):
        if "socket_timeout" in kwargs and not BROKER.supports_socket_timeout:
            raise TypeError("unexpected keyword argument 'socket_timeout'")
        self.client_id = client_id
        self.server = server
        self.port = port
        self.user = user
        self.password = password
        self.keepalive = keepalive
        self.cb = None
        self.connected = False

    def set_callback(self, cb):
        self.cb = cb

    def _require_link(self):
        if not BROKER.up:
            raise OSError(113, "ECONNABORTED")

    def connect(self, clean_session=True):
        BROKER.attempts += 1
        self._require_link()
        if not BROKER.accept_auth:
            raise MQTTException(5)          # 5 = not authorised
        BROKER.connects += 1
        self.connected = True
        return 0

    def disconnect(self):
        self.connected = False

    def subscribe(self, topic, qos=0):
        self._require_link()
        BROKER.subscriptions.append(topic)

    def publish(self, topic, msg, retain=False, qos=0):
        self._require_link()
        BROKER.published.append((topic, msg))

    def ping(self):
        self._require_link()
        BROKER.pings += 1

    def check_msg(self):
        self._require_link()
        if not BROKER.inbox:
            return None
        topic, payload = BROKER.inbox.pop(0)
        if self.cb is not None:
            self.cb(topic, payload)
        return payload
