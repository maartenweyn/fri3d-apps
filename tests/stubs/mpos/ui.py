class _TaskHandler:
    cbs = []

    def add_event_cb(self, fn, prio):
        self.cbs.append(fn)

    def remove_event_cb(self, fn):
        if fn in self.cbs:
            self.cbs.remove(fn)


task_handler = _TaskHandler()
