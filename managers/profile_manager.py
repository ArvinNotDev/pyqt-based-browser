"""Lightweight browser profile bookkeeping.

Profile names are local application data and do not need a hardware-derived
machine identifier. ``machine_id`` and ``get_machine_id`` remain as legacy API
shims for older callers, but now return a fixed local marker.
"""


class Profile:
    def __init__(self):
        self.machine_id = "local"
        self.profile_list = ["guest"]

    @classmethod
    def get_machine_id(cls):
        """Deprecated compatibility shim; no hardware identifier is collected."""
        return "local"

    def as_guest(self):
        return self.machine_id

    def add_profile(self, name):
        self.profile_list.append(name)
