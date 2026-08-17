_STORE = {}


class _Editor:
    def __init__(self, ns):
        self.ns = ns
        self.pending = {}

    def put_int(self, k, v):
        assert isinstance(v, int), (k, v)
        self.pending[k] = v
        return self

    def put_string(self, k, v):
        assert isinstance(v, str), (k, v)
        self.pending[k] = v
        return self

    def commit(self):
        _STORE.setdefault(self.ns, {}).update(self.pending)

    apply = commit


class SharedPreferences:
    def __init__(self, ns):
        self.ns = ns

    def edit(self):
        return _Editor(self.ns)

    def get_int(self, k, default=0):
        return _STORE.get(self.ns, {}).get(k, default)

    def get_string(self, k, default=""):
        return _STORE.get(self.ns, {}).get(k, default)
